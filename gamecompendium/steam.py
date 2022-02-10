import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import TextIO, Optional

import aiohttp
import dateparser
import gzip
from tqdm import tqdm

from whoosh import fields
from whoosh.fields import Schema
from whoosh.filedb.filestore import Storage
from whoosh.index import Index
from whoosh.qparser import MultifieldParser
import datetime
import re

from whoosh.writing import IndexWriter

from analyzers import keep_numbers_analyzer
from async_utils import soft_log_exceptions
from config import config
from rate_limiter import RateLimiter, RateLimitExceedException
from resolver import EntityResolver

STORAGE_NAME = 'steam'

# Steam says 100'000 a day, but it seems to use much lower limits
REQUESTS_PER_MINUTE = 40
DUMP_LIST_PATH = 'dumps/steam_list.json'
DUMP_PATH = 'dumps/steam.dump'
DUMP_KEEP_KEYS = {'type', 'name', 'steam_appid', 'required_age', 'is_free', 'detailed_description', 'about_the_game',
                  'short_description', 'supported_languages', 'website', 'developers', 'price_overview',
                  'platforms', 'metacritic', 'categories', 'genres', 'recommendations', 'release_date',
                  'content_descriptors'}

ONLY_KNOWN_GAMES = not config['download_full']
# Number of reccomendations required to be a 'known game'
ONLY_KNOWN_GAMES_CUTOFF = 1000

schema = Schema(
    id=fields.ID(stored=True, unique=True),
    uuid=fields.ID(stored=True, unique=True),
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

    def file_add(data: dict):
        fd.write(json.dumps(data) + '\n')

    async def load_game(appid: int):
        try:
            try:
                details = await limiter.execute(lambda: load_json(session, 'https://store.steampowered.com/api/appdetails', {'appids': appid}))
            except json.decoder.JSONDecodeError:
                # Invalid json file returned
                file_add({'steam_appid': appid, 'failed': True})
                return
            data = details[str(appid)]
            if not data['success']:
                # We don't have permission probably
                file_add({'steam_appid': appid, 'failed': True})
                return
            unfiltered = data['data']  # Unwrap
            if appid != unfiltered['steam_appid']:
                # Redirected entry
                file_add({'steam_appid': appid, 'failed': True, 'redirect': unfiltered['steam_appid']})
                # Only save the redirected game if it's not in games
                if appid in games:
                    return

            # Filter unwanted keys
            filtered = {k: v for k, v in unfiltered.items() if k in DUMP_KEEP_KEYS}
            file_add(filtered)
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
    return len(all_games)


async def require_dump() -> (int, TextIO):
    # Replace the next line with some game count estimate
    # to skip the dump check/completion
    count = await dump_steam()

    return count, gzip.open(DUMP_PATH, 'rt')


def parse_date(date: dict) -> Optional[datetime.datetime]:
    if date['coming_soon'] or date['date'] == '':
        return None
    raw_date = date['date']
    try:
        date = dateparser.parse(raw_date)
    except:
        date = None
    if date is None:
        print(f"Cannot parse date {json.dumps(date)}", file=sys.stderr)
    return date


def index_games(gamedb: TextIO, gamecount: int, writer: IndexWriter, resolver: EntityResolver):
    with tqdm(total=gamecount) as progress:
        games = set()
        for line in gamedb:
            progress.update(1)
            line = line.strip()
            if line == "":
                continue

            game = json.loads(line)

            if game.get('failed', False) or game.get('type', 'unknown') not in ['game', 'dlc']:
                continue
            if game['steam_appid'] in games:
                continue
            if ONLY_KNOWN_GAMES and game.get('recommendations', {}).get('total', 0) < ONLY_KNOWN_GAMES_CUTOFF:
                continue
            games.add(game['steam_appid'])

            game_date = parse_date(game['release_date'])
            genres_list = [g['description'] for g in game.get('genres', [])]

            dev_list = game.get('developers', [])
            # dev_list.extend(data['publishers'])
            uuid = resolver.compute_id(game['steam_appid'], game['name'], dev_list, game_date)

            summary_text = game['about_the_game']
            summary_text = re.sub(r"<(.*?)>", "", summary_text)  # Remove HTML tags
            
            writer.add_document(
                id=str(game['steam_appid']),
                uuid=uuid,
                name=game['name'],
                genres=','.join(genres_list),
                platforms=','.join(game['platforms']),
                dev_companies=','.join(dev_list),
                release_date=game_date,
                storyline=game['detailed_description'],
                summary=summary_text
            )


async def init_index(storage: Storage, resolver: EntityResolver) -> Index:
    if not storage.index_exists(STORAGE_NAME):
        print("STEAM index not found, creating!")

        index = storage.create_index(schema, indexname=STORAGE_NAME)
        count, fd = await require_dump()
        with fd, index.writer() as writer:
            index_games(fd, count, writer, resolver)
            print("Indexing...")
        print("Ready!")
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

