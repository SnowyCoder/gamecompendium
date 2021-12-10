import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import TextIO, Optional

import aiohttp
import gzip
from tqdm import tqdm

from whoosh import fields
from whoosh.fields import Schema
from whoosh.filedb.filestore import Storage
from whoosh.index import Index
from whoosh.qparser import MultifieldParser
import datetime
from analyzers import keep_numbers_analyzer
from async_utils import soft_log_exceptions
from rate_limiter import RateLimiter, RateLimitExceedException

STORAGE_NAME = 'steam'

# Steam says 100'000 a day, but it seems to use much lower limits
REQUESTS_PER_MINUTE = 40
DUMP_LIST_PATH = 'dumps/steam_list.json'
DUMP_PATH = 'dumps/steam.dump'
DUMP_KEEP_KEYS = {'type', 'name', 'steam_appid', 'required_age', 'is_free', 'detailed_description', 'about_the_game',
                  'short_description', 'supported_languages', 'website', 'developers', 'price_overview',
                  'platforms', 'metacritic', 'categories', 'genres', 'recommendations', 'release_date',
                  'content_descriptors'}


schema = Schema(
    id=fields.ID(stored=True, unique=True),
    name=fields.TEXT(stored=True, analyzer=keep_numbers_analyzer()),
    storyline=fields.TEXT(stored=True),
    summary=fields.TEXT(stored=True),
    genres=fields.KEYWORD(stored=True),
    platforms=fields.KEYWORD(stored=True),
    dev_companies=fields.KEYWORD(stored=True),
    release_date=fields.DATETIME(stored=True),
)


async def load_json(session: aiohttp.ClientSession, url: str, params: dict = None) -> dict:
    async with session.get(url=url, params=params) as response:
        if not 200 <= response.status < 300:
            # Steam has... weird things, seems like even if you respect their limits you'll still be temporarly banned
            if response.status in [429, 403]:
                raise RateLimitExceedException()
            raise Exception(f"Error {url} {params}, returned {response.status}: {await response.read()}")
        return json.loads(await response.read())


async def dump_steam():
    """
    Dumps the steam API into a gzipped file, this is required since Steam has strict API limits and we don't
    want to hit them,
    """

    async def load_list() -> list[int]:
        path = Path(DUMP_LIST_PATH)
        if path.is_file():
            with path.open('rt') as fd:
                return json.load(fd)
        else:
            data = await limiter.execute(
                lambda: load_json(session, 'https://api.steampowered.com/ISteamApps/GetAppList/v0002'))
            games = data['applist']['apps']
            # Format: list[{"appid": str, "name": str}]
            games = [g['appid'] for g in games]
            with path.open('wt') as fd:
                json.dump(games, fd)
            return games

    async def load_game(appid: int):
        try:
            details = await limiter.execute(lambda: load_json(session, 'https://store.steampowered.com/api/appdetails', {'appids': appid}))
            data = details[str(appid)]
            if not data['success']:
                # We don't have permission probably
                fd.write(json.dumps({'steam_appid': appid, 'failed': True}) + '\n')
                return
            unfiltered = data['data']  # Unwrap
            # Filter unwanted keys
            filtered = {k: v for k, v in unfiltered.items() if k in DUMP_KEEP_KEYS}

            fd.write(json.dumps(filtered, check_circular=False) + '\n')
        finally:
            progress.update(1)

    print("Dumping all steam data (only required once)")
    dump_path = Path(DUMP_PATH)

    async with aiohttp.ClientSession() as session, \
            RateLimiter(REQUESTS_PER_MINUTE / 60, 2) as limiter:
        all_games = set(await load_list())
        # Get completed games
        completed_games = set()
        try:
            with gzip.open(dump_path, 'rt') as fd:
                completed_games = set([json.loads(line.strip())['steam_appid'] for line in fd])
        except FileNotFoundError:
            pass
        except Exception:
            traceback.print_exc()

        games = list(all_games - completed_games)

        dump_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(dump_path, 'at') as fd, \
                tqdm(total=len(all_games), initial=len(completed_games), dynamic_ncols=True) as progress:
            BATCH_SIZE = 1000
            # Make requests in batches so that we don't fill RAM with futures
            for i in range(0, len(games), BATCH_SIZE):
                batch = games[i:i + BATCH_SIZE]
                await asyncio.gather(*[
                    soft_log_exceptions(load_game(g)) for g in batch
                ])


async def require_dump() -> TextIO:
    # Comment the next line to skip the dump check/completion
    await dump_steam()

    return gzip.open(DUMP_PATH, 'rt')


def parse_date(date: dict) -> Optional[datetime.datetime]:
    if date['coming_soon'] or date['date'] == '':
        return None
    raw_date = date['date']
    # Format example: '10 Oct, 2007' (but also 'Aug 12, 2015'!)
    POSSIBLE_FORMATS = ['%d %b, %Y', '%b %d, %Y']
    for fs in POSSIBLE_FORMATS:
        try:
            return datetime.datetime.strptime(raw_date, fs)
        except ValueError:
            pass
    # No format matched
    print(f"Cannot parse date {json.dumps(date)}", file=sys.stderr)
    return None


async def init_index(storage: Storage) -> Index:
    if not storage.index_exists(STORAGE_NAME):
        print("STEAM index not found, creating!")

        index = storage.create_index(schema, indexname=STORAGE_NAME)
        with index.writer() as writer, await require_dump() as fd:
            for line in fd:
                line = line.strip()
                if line == "":
                    continue

                game = json.loads(line)

                if game.get('failed', False):
                    continue

                game_date = parse_date(game['release_date'])
                genres_list = [g['description'] for g in game.get('genres', [])]

                dev_list = game['developers']
                # dev_list.extend(data['publishers'])

                writer.add_document(
                    id=str(game['steam_appid']),
                    name=game['name'],
                    genres=','.join(genres_list),
                    platforms=','.join(game['platforms']),
                    dev_companies=','.join(dev_list),
                    release_date=game_date,
                    storyline=game['detailed_description'],
                    summary=game['about_the_game']
                )
    else:
        index = storage.open_index(STORAGE_NAME, schema)

    return index


async def test(index: Index):
    qp = MultifieldParser(('name', 'storyline', 'summary'), schema)
    with index.searcher() as searcher:
        while True:
            try:
                query_txt = input(">")
            except KeyboardInterrupt:
                return
            except EOFError:
                return

            query = qp.parse(query_txt)
            res = searcher.search(query, limit=5)
            print(f'Found {len(res)} results:')
            for (i, x) in enumerate(res):
                print(f"{i + 1}. {x['name']} - {x['dev_companies']} {x.get('release_date')}")

