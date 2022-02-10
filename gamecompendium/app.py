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
                query_txt = re.sub(r"\s*1$", "", query_txt)  # Remove HTML tags
            except KeyboardInterrupt:
                return
            except EOFError:
                return
            query = qp.parse(query_txt)
            print(f'Query: {query}')
            
            """
            dictel = {}
            # game uuid -> (score, Array<(name, entry)>)
            for name, index in self.indexes.items():
                with index.searcher() as searcher:
                    res = searcher.search(query, limit=5)
                    print(f'Found {len(res)} results in {name}:')
                    for x in res:
                        res = dictel.setdefault(x['uuid'], [0, []])
                        res[0] += x.score
                        res[1].append((name, x))

            for score, entries in sorted(dictel.values(), key=lambda k: k[0], reverse=True):
                print("---------------------------------------------------------------------")
                print(f"              Total score: {score}")
                for name, entry in entries:
                    print(f"{name}\t{entry['name']}\t{entry['dev_companies']}\t{entry.get('release_date')} - Score: {entry.score}")
                print("---------------------------------------------------------------------")
            """
            
            ######### aggregator test here ##############
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
                    # regex filter for html tags
                    #summary = list_el[0]['summary'][0:150]
                    #summary = re.sub(r"<(.*?)>", "", summary)  # Remove HTML tags
    
                    print("------------------------")
                    print(f"{list_el[0]['name']}")
                    if list_el[0].get('release_date',"no") != "no":
                        print(f"Release date: {list_el[0]['release_date']}")
                    print(f"Developers: {list_el[0]['dev_companies']}")
                    print(f"According to {list_el[1]}")
                    # print(f"{list_el[0].score}")  # Used for single-score debugging
                    print(f"\n\"{list_el[0]['summary'][0:150]}...\"")
                    #print(summary)
                    print("------------------------\n")
                print(".................")
                print(f"Score {el[1]}")
                print(".................")
            print("___________________________________________________________________________")
            
            
            
            

