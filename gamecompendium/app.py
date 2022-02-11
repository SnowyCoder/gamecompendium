import os
from typing import Callable, Awaitable, Dict

from whoosh.filedb.filestore import Storage, FileStorage
from whoosh.index import Index
from whoosh.qparser import MultifieldParser
import re

from resolver import EntityResolver, general_schema

from igdb import init_index as igdb_init_index
from steam import init_index as steam_init_index


import aggregator

INDEX_DIR = 'indexes'


class App:
    indexes: Dict[str, Index]
    storage: Storage

    def __init__(self):
        self.indexes = {}
        if not os.path.exists(INDEX_DIR):
            os.mkdir(INDEX_DIR)
        self.storage = FileStorage(INDEX_DIR)

    async def init_index(self, name, fn: Callable[[Storage, EntityResolver], Awaitable[Index]]):
        resolver = EntityResolver(*self.indexes.values())
        print(f"Initializing {name} (with {len(self.indexes)} resolvers)")
        index = await fn(self.storage, resolver)
        print(f"Done, stats: {resolver.reused} reused / {resolver.generated} generated / {resolver.conflicts} conflicts")
        self.indexes[name] = index

    async def init(self):
        await self.init_index('Igdb', igdb_init_index)
        await self.init_index('Steam', steam_init_index)

    def prompt(self):
        qp = MultifieldParser(('name', 'storyline', 'summary'), general_schema)
        while True:
            try:
                query_txt = input(">")
                # Remove "1" from the end of queries, this helps since games are
                # always stored as "Portal" not "Portal 1"
                query_txt = re.sub(r"\s*1$", "", query_txt)
            except KeyboardInterrupt:
                return
            except EOFError:
                return
            query = qp.parse(query_txt)
            print(f'Query: {query}')

            searchers = [(idx.searcher(), idxname) for idxname, idx in self.indexes.items()]
            topk_results = aggregator.aggregate_search(query, searchers, 5)
            
            # print process
            itr = 1
            for el in topk_results:
                print("\n\n\n***********************")
                print(f"Result n. {itr}: ")
                print("***********************")
                itr += 1
                for list_el in el[0]:
                    print("------------------------")
                    print(f"{list_el[0]['name']}")
                    if list_el[0].get('date', "no") != "no":
                        print(f"Release date: {list_el[0]['date']}")
                    print(f"Developers: {list_el[0]['devs']}")
                    print(f"According to {list_el[1]}")
                    # print(f"{list_el[0].score}")  # Used for single-score debugging
                    print(f"\n\"{list_el[0]['summary'][0:150]}...\"")
                    print("------------------------\n")
                print(".................")
                print(f"Score {el[1]}")
                print(".................")
            print("___________________________________________________________________________")
            
            
            
            

