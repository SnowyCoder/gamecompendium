import os
from typing import Dict, IO

from whoosh.filedb.filestore import Storage, FileStorage
from whoosh.index import Index
from whoosh.qparser import MultifieldParser
import re

from benchmark import BenchmarkSuite, BenchmarkResult
from resolver import EntityResolver, general_schema

from igdb import IgdbSource
from source import Source
from steam import SteamSource

import aggregator

INDEX_DIR = 'indexes'

DEFAULT_SOURCES = [
    IgdbSource(),
    SteamSource()
]


class App:
    sources: Dict[str, Source]
    indexes: Dict[str, Index]
    storage: Storage

    def __init__(self):
        self.sources = {}
        self.indexes = {}
        if not os.path.exists(INDEX_DIR):
            os.mkdir(INDEX_DIR)
        self.storage = FileStorage(INDEX_DIR)

    def add_source(self, source: Source):
        self.sources[source.name] = source

    def add_default_sources(self):
        for source in DEFAULT_SOURCES:
            self.add_source(source)

    async def _init_index(self, source: Source, force_reindex: bool = False, only_if_present: bool = False):
        if not force_reindex and self.storage.index_exists(source.name):
            index = self.storage.open_index(indexname=source.name, schema=source.schema)
        else:
            if only_if_present:
                return
            resolver = EntityResolver(*self.indexes.values())
            print(f"Initializing {source.name} (with {len(self.indexes)} resolvers)")
            index = self.storage.create_index(indexname=source.name, schema=source.schema)
            await source.reindex(index, resolver)
            print(f"Done, stats: {resolver.reused} reused / {resolver.generated} generated / {resolver.conflicts} conflicts")

        self.indexes[source.name] = index

    async def scrape(self):
        for source in self.sources.values():
            await source.scrape()

    async def init(self, force_reindex: bool = False):
        # Open sources that are already indexed
        for source in self.sources.values():
            if source.name not in self.indexes:
                await self._init_index(source, only_if_present=True)

        # Open all the other sources (using previous sources as resolvers)
        for source in self.sources.values():
            if source.name not in self.indexes:
                await self._init_index(source, force_reindex=force_reindex)

    def run_query(self, query_txt: str, k: int = 5) -> list[aggregator.AggregateHit]:
        # Remove "1" from the end of queries, this helps since games are
        # always stored as "Portal" not "Portal 1"
        query_txt = re.sub(r"\s+[1I]$", "", query_txt.strip())

        qp = MultifieldParser(('name', 'storyline', 'summary'), general_schema)
        query = qp.parse(query_txt)

        searchers = [(idx.searcher(), idxname) for idxname, idx in self.indexes.items()]
        topk_results = aggregator.aggregate_search(query, searchers, k)
        return topk_results

    def evaluate(self, suite: BenchmarkSuite) -> list[BenchmarkResult]:
        res = []
        for bench in suite.benchmarks:
            topk = self.run_query(bench.query, 10)
            data = {(s.source, s.id): s.relevance for s in bench.scores}
            entries = []
            for row in topk:
                relevance = next((d for hit, source in row.hits if (d := data.get((source, hit['id']))) is not None), 0)
                entries.append(relevance)
            res.append(BenchmarkResult(bench.query, entries))
        return res

    def prompt(self):
        while True:
            try:
                query_txt = input(">")
            except KeyboardInterrupt:
                return
            except EOFError:
                return

            topk_results = self.run_query(query_txt)
            
            # print process
            for itr, el in enumerate(topk_results):
                print("\n\n\n***********************")
                print(f"Result n. {itr + 1}: ")
                print("***********************")
                for hit, source in el.hits:
                    print("------------------------")
                    print(f"{hit['name']}")
                    if hit.get('date', "no") != "no":
                        print(f"Release date: {hit['date']}")
                    print(f"Developers: {hit['devs']}")
                    print(f"According to {source}")
                    # print(f"{list_el[0].score}")  # Used for single-score debugging
                    print(f"\n\"{hit['summary'][0:150]}...\"")
                    print("------------------------\n")
                print(".................")
                print(f"Score {el.total_score}")
                print(".................")
            print("___________________________________________________________________________")
            
            
            
            

