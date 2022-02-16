import os
from typing import Dict

from tqdm import tqdm

from whoosh_bugs import run as dont_delete_me_im_fixing_whoosh_bugs
from whoosh.filedb.filestore import Storage, FileStorage
from whoosh.index import Index
from whoosh.qparser import syntax, Plugin, QueryParser, MultifieldPlugin
import re

from whoosh.searching import Searcher

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

dont_delete_me_im_fixing_whoosh_bugs()


class App:
    sources: Dict[str, Source]
    indexes: Dict[str, Index]
    storage: Storage
    _searchers: list[tuple[Searcher, str]]

    def __init__(self):
        self.sources = {}
        self.indexes = {}
        if not os.path.exists(INDEX_DIR):
            os.mkdir(INDEX_DIR)
        self.storage = FileStorage(INDEX_DIR)
        self._searchers = []

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
            print(f"Done, stats: {resolver.reused} reused / {resolver.generated} generated")

        self.indexes[source.name] = index

    async def scrape(self, update: bool):
        for source in self.sources.values():
            await source.scrape(update)

    async def init(self, force_reindex: bool = False):
        # Open sources that are already indexed
        if not force_reindex:
            for source in self.sources.values():
                if source.name not in self.indexes:
                    await self._init_index(source, only_if_present=True)

        # Open all the other sources (using previous sources as resolvers)
        for source in self.sources.values():
            if source.name not in self.indexes:
                await self._init_index(source, force_reindex=force_reindex)

    def _require_searchers(self) -> list[tuple[Searcher, str]]:
        if len(self._searchers) != len(self.sources):
            self._searchers = [(idx.searcher(), idxname) for idxname, idx in self.indexes.items()]
        return self._searchers

    def create_parser(self) -> QueryParser:
        p = QueryParser(None, general_schema, group=syntax.OrGroup)
        fieldboosts = {
            'name': 6,
            'storyline':1,
            'summary': 1,
        }
        mfp = MultifieldPlugin(('name', 'storyline', 'summary'), fieldboosts=fieldboosts)
        p.add_plugin(mfp)
        # adds custom set boosts to each field in case the user specifically selects one of them with "field:value"
        # some fields are already boosted by default like "name" but an additional boost can be added by specifing it
        p.add_plugin(FieldBoosterPlugin({
            'name':40, 'devs':40, 'date':40,'genres':40,'platforms':40
        }))
        return p

    def run_query(self, query_txt: str, k: int = 5) -> list[aggregator.AggregateHit]:
        # Remove "1" from the end of queries, this helps since games are
        # always stored as "Portal" not "Portal 1"
        query_txt = re.sub(r"\s+[1I]$", "", query_txt.strip())

        qp = self.create_parser()
        query = qp.parse(query_txt)
        #print(repr(query))
        searchers = self._require_searchers()
        topk_results = aggregator.aggregate_search(query, searchers, k)
        return topk_results

    def evaluate(self, suite: BenchmarkSuite) -> list[BenchmarkResult]:
        res = []
        for bench in tqdm(suite.benchmarks):
            topk = self.run_query(bench.query, 10)
            data = {(s.source, s.id): s.relevance for s in bench.scores}
            entries = []
            for row in topk:
                relevance = next((d for hit, source in row.hits if (d := data.get((source, hit['id']))) is not None), 0)
                entries.append(relevance)
            res.append(BenchmarkResult(bench, entries))
        return res

    def prompt(self):
        # Eager searcher initialization (reduces first interaction time)
        self._require_searchers()
        while True:
            try:
                query_txt = input(">")
            except KeyboardInterrupt:
                return
            except EOFError:
                return

            topk_results = self.run_query(query_txt)
            topk_results.reverse()
            # print process
            for itr, el in enumerate(topk_results):
                print("\n\n\n***********************")
                print(f"Result n. {len(topk_results) - itr}: ")
                print("***********************")
                for hit, source in el.hits:
                    print("------------------------")
                    print(f"{hit['name']}")
                    if hit.get('date', "no") != "no":
                        print(f"Release date: {hit['date']}")
                    if hit.get('genres', "no") != "no":
                        print(f"Genres: {hit['genres']}")
                    if hit.get('platforms', "no") != "no":
                        print(f"Platforms: {hit['platforms']}")
                    print(f"Developers: {hit['devs']}")
                    print(f"According to {source}")
                    # print(f"{list_el[0].score}")  # Used for single-score debugging
                    summary: str = hit.get('summary')
                    if summary is not None:
                        if len(summary) > 150:
                            summary = summary[0:150] + "..."
                        print(f"\n\"{summary}\"")
                    print("------------------------\n")
                print(".................")
                print(f"Score {el.total_score}")
                print(".................")
            print("___________________________________________________________________________")
            
            
class FieldBoosterPlugin(Plugin):
    boosts: Dict[str, float]

    def __init__(self, boosts: Dict[str, float]):
        self.boosts = boosts

    def filters(self, parser):
        # Run just before MultifieldPlugin (110)
        return [(self.do_boost, 105)]

    def do_boost(self, parser: QueryParser, group: syntax.GroupNode):
        for i, node in enumerate(group):
            if isinstance(node, syntax.GroupNode):
                # Recurse inside groups
                group[i] = self.do_boost(parser, node)
            elif node.has_fieldname and node.fieldname is not None:
                node.set_boost(node.boost * self.boosts.get(node.fieldname, 1.0))
        return group
            

