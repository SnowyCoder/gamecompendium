import asyncio
import datetime
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable

import aiohttp
import requests
from whoosh import fields
from whoosh.fields import Schema
from whoosh.filedb.filestore import Storage
from whoosh.index import Index
from whoosh.qparser import MultifieldParser

from async_utils import soft_log_exceptions
from config import config
from analyzers import keep_numbers_analyzer
from rate_limiter import RateLimiter

STORAGE_NAME = 'igdb'
# Downloads less games (faster to index but has only 10% of the games, used for testing)
ONLY_KNOWN_GAMES = not config['download_full']

# https://api-docs.igdb.com/#rate-limits
REQUESTS_PER_SECOND = 4
MAX_OPEN_QUERIES = 6
MAX_LIMIT = 500


@dataclass
class IgdmGameExtract:
    id: int
    name: str
    storyline: str
    summary: str
    genres: List[str]
    platforms: List[str]
    dev_companies: List[str]
    release_date: Optional[datetime.datetime]


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


class Access:
    def __init__(self, client, secret):
        self.client = client
        self.secret = secret

        self.token = None
        self.expires_at = datetime.datetime.now()

    def download_token(self):
        params = {
            'client_id': self.client,
            'client_secret': self.secret,
            'grant_type': 'client_credentials'
        }
        self.token = requests.post('https://id.twitch.tv/oauth2/token', params=params).json()
        # print(self.token)
        self.expires_at = datetime.datetime.now() + datetime.timedelta(seconds=self.token['expires_in'] - 10)

    def headers(self):
        if datetime.datetime.now() > self.expires_at:
            self.download_token()

        return {
            'Client-ID': self.client,
            'Authorization': 'Bearer ' + self.token['access_token'],
        }


twitch_config = config['twitch']
access = Access(twitch_config['client_id'], twitch_config['client_secret'])


async def load_json(session: aiohttp.ClientSession, url: str, data: str):
    async with session.post(url='https://api.igdb.com/v4/' + url, headers=access.headers(), data=data) as response:
        if not 200 <= response.status < 300:
            raise Exception(await response.read())
        return json.loads(await response.read())


async def extract_games(queue: asyncio.Queue[IgdmGameExtract], count: Callable[[int], None]):
    add_filter = 'where total_rating_count > 5;' if ONLY_KNOWN_GAMES else ''

    async def load_games(offset: int):
        QUERY = f'fields name, storyline, summary, genres.name, platforms.name, involved_companies.company.name, '\
                f'involved_companies.developer, release_dates.date; limit {MAX_LIMIT};'
        real_query = QUERY + f'offset {offset};' + add_filter
        games = await limiter.execute(load_json(session, 'games', real_query))  # type: List[Dict]

        for game in games:

            release_date = None
            for rdate in game.get('release_dates', []):
                date = rdate.get('date')
                if date is None:
                    continue
                if release_date is None:
                    release_date = date
                elif date < release_date:
                    release_date = date

            data = IgdmGameExtract(
                id=game['id'],
                name=game.get('name'),
                genres=[g['name'] for g in game.get('genres', [])],
                platforms=[p['name'] for p in game.get('platforms', [])],
                dev_companies=[c['company']['name'] for c in game.get('involved_companies', []) if c['developer']],
                release_date=datetime.datetime.fromtimestamp(release_date) if release_date is not None else None,
                storyline=game.get('storyline'),
                summary=game.get('summary'),
            )
            await queue.put(data)

    async with aiohttp.ClientSession() as session, RateLimiter(REQUESTS_PER_SECOND, MAX_OPEN_QUERIES) as limiter:
        games_count = (await limiter.execute(load_json(session, 'games/count', 'fields *;' + add_filter)))['count']
        count(games_count)

        await asyncio.gather(*[
            soft_log_exceptions(load_games(offset)) for offset in range(0, games_count, MAX_LIMIT)
        ])


async def populate(ix: Index):
    queue = asyncio.Queue()  # type: asyncio.Queue[IgdmGameExtract]

    total = 0
    done = 0

    def set_total(x: int):
        nonlocal total
        total = x

    async def consumer():
        nonlocal done
        while True:
            x = await queue.get()
            writer.add_document(
                id=str(x.id),
                name=x.name,
                genres=','.join(x.genres),
                platforms=','.join(x.platforms),
                dev_companies=','.join(x.dev_companies),
                release_date=x.release_date,
                storyline=x.storyline,
                summary=x.summary,
            )
            queue.task_done()
            done += 1
            print(f"\r{done}/{total}", end="")

    with ix.writer() as writer:
        task = asyncio.create_task(soft_log_exceptions(consumer()))
        await extract_games(queue, set_total)
        await queue.join()
        task.cancel()
        print("\nIndexing...")
        # writer.commit() is already called by writer.__exit__()


async def init_index(storage: Storage) -> Index:
    if not storage.index_exists(STORAGE_NAME):
        print("IGDB index not found, creating!")
        index = storage.create_index(schema, indexname=STORAGE_NAME)
        await populate(index)
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



