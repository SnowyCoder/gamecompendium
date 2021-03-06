import asyncio
import dataclasses
import datetime
import gzip
import json
import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable

import aiohttp
import requests
from tqdm import tqdm
from whoosh import fields
from whoosh.fields import Schema
from whoosh.index import Index, FileIndex

from async_utils import soft_log_exceptions
from config import config
from analyzers import keep_numbers_analyzer
from rate_limiter import RateLimiter
from resolver import EntityResolver
from source import Source

STORAGE_NAME = 'igdb'
# Downloads less games (faster to index but has only 10% of the games, used for testing)
ONLY_KNOWN_GAMES = not config['download_full']
DUMP_PATH = 'dumps/igdb.dump'
DUMP_COUNT_PATH = 'dumps/igdb.count'

# https://api-docs.igdb.com/#rate-limits
REQUESTS_PER_SECOND = 4
MAX_OPEN_QUERIES = 6
MAX_LIMIT = 500
ONLY_KNOWN_GAMES_CUTOFF = 5


@dataclass
class IgdmGameExtract:
    id: int
    name: str
    storyline: str
    summary: str
    genres: List[str]
    platforms: List[str]
    dev_companies: List[str]
    release_date: Optional[int]
    total_rating_count: int


schema = Schema(
    id=fields.ID(stored=True, unique=True),
    uuid=fields.ID(stored=True, unique=True),
    name=fields.TEXT(stored=True, analyzer=keep_numbers_analyzer()),
    storyline=fields.TEXT(stored=True),
    summary=fields.TEXT(stored=True),
    genres=fields.KEYWORD(stored=True),
    platforms=fields.KEYWORD(stored=True),
    devs=fields.KEYWORD(stored=True),
    date=fields.DATETIME(stored=True),
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


def parse_timestamp_opt(ts: Optional[int]) -> Optional[datetime.datetime]:
    if ts is None:
        return None
    if ts >= 0:
        return datetime.datetime.fromtimestamp(ts)
    else:
        return datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(ts))


async def load_json(session: aiohttp.ClientSession, url: str, data: str):
    async with session.post(url='https://api.igdb.com/v4/' + url, headers=access.headers(), data=data) as response:
        if not 200 <= response.status < 300:
            raise Exception(await response.read())
        return json.loads(await response.read())


async def download_games(queue: asyncio.Queue[IgdmGameExtract], count: Callable[[int], None]):

    async def load_games(offset: int):
        QUERY = f'fields name, storyline, summary, genres.name, platforms.name, involved_companies.company.name, '\
                f'involved_companies.developer, release_dates.date, total_rating_count; limit {MAX_LIMIT};'
        real_query = QUERY + f'offset {offset};'
        games = await limiter.execute(lambda: load_json(session, 'games', real_query))  # type: List[Dict]

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
                release_date=release_date,
                storyline=game.get('storyline'),
                summary=game.get('summary'),
                total_rating_count=int(game.get('total_rating_count', 0)),
            )
            await queue.put(data)

    async with aiohttp.ClientSession() as session, RateLimiter(REQUESTS_PER_SECOND, MAX_OPEN_QUERIES) as limiter:
        games_count = (await limiter.execute(lambda: load_json(session, 'games/count', 'fields *;')))['count']
        count(games_count)

        await asyncio.gather(*[
            soft_log_exceptions(load_games(offset)) for offset in range(0, games_count, MAX_LIMIT)
        ])


async def download_to_dump(update: bool = False):
    if not update and os.path.isfile(DUMP_PATH):
        return

    queue = asyncio.Queue()  # type: asyncio.Queue[IgdmGameExtract]

    def set_total(c: int):
        progress.total = c
        with open(DUMP_COUNT_PATH, 'wt') as cfd:
            cfd.write(str(c))

    async def consumer():
        while True:
            x = await queue.get()
            fd.write(json.dumps(dataclasses.asdict(x)) + '\n')
            queue.task_done()
            progress.update(1)

    with gzip.open(DUMP_PATH, 'wt') as fd, \
            tqdm(dynamic_ncols=True) as progress:
        task = asyncio.create_task(soft_log_exceptions(consumer()))
        await download_games(queue, set_total)
        await queue.join()
        task.cancel()


async def populate(ix: Index, resolver: EntityResolver):
    await download_to_dump()
    queue = asyncio.Queue()  # type: asyncio.Queue[IgdmGameExtract]

    with open(DUMP_COUNT_PATH, 'rt') as fd:
        total = int(fd.readline())

    async def producer():
        with gzip.open(DUMP_PATH, 'rt') as fd:
            for line in fd:
                line = line.strip()
                if line == '':
                    continue
                await queue.put(IgdmGameExtract(**json.loads(line)))

    async def consumer():
        while True:
            x = await queue.get()
            if not ONLY_KNOWN_GAMES or x.total_rating_count >= ONLY_KNOWN_GAMES_CUTOFF:
                release_date = parse_timestamp_opt(x.release_date)
                if previsit:
                    resolver.compute(x.id, x.name, x.dev_companies, release_date)
                    return
                uuid = resolver.get_id(x.id)
                
                writer.add_document(
                    id=str(x.id),
                    uuid=uuid,
                    name=x.name,
                    genres=','.join(x.genres),
                    platforms=','.join(x.platforms),
                    devs=','.join(x.dev_companies),
                    date=release_date,
                    storyline=x.storyline,
                    summary=x.summary,
                )
            queue.task_done()
            progress.update(1)

    if resolver.needs_previsit():
        print("Resolving entities...")
        previsit = True
        with tqdm(total=total, dynamic_ncols=True) as progress:
            task = asyncio.create_task(soft_log_exceptions(consumer()))
            await producer()
            await queue.join()
            task.cancel()

    previsit = False
    with ix.writer() as writer:
        print("Writing to segments...")
        with tqdm(total=total, dynamic_ncols=True) as progress:
            task = asyncio.create_task(soft_log_exceptions(consumer()))
            await producer()
            await queue.join()
            task.cancel()

        print("\nIndexing...")
        # writer.commit() is already called by writer.__exit__()


class IgdbSource(Source):
    def __init__(self):
        self.name = STORAGE_NAME
        self.schema = schema

    async def scrape(self, update: bool) -> None:
        await download_to_dump(update)

    async def reindex(self, index: FileIndex, resolver: EntityResolver) -> None:
        await populate(index, resolver)
