import asyncio
import os
from whoosh.filedb.filestore import FileStorage
from whoosh.index import Index
from whoosh.qparser import MultifieldParser

import igdb
import steam
from steam import schema
INDEX_DIR = 'indexes'

async def test(index1: Index, index2: Index):
    qp = MultifieldParser(('name', 'storyline', 'summary'), schema)
    query_txt = ""
    while True:
        try:
            query_txt = input(">")
        except KeyboardInterrupt:
            return
        except EOFError:
            return
            
        dictel = {}
        with index1.searcher() as searcher1:
            query1 = qp.parse(query_txt)
            res1 = searcher1.search(query1, limit=5)
            print(f'Found {len(res1)} results:')
            for (i, x) in enumerate(res1):
                dateyear = str(x.get('release_date'))[0:4]
                dictel[f"{x['name']}{dateyear}"] = x
            
            
        print("\n")
        
        dictel2 = {}
        with index2.searcher() as searcher2:
            query2 = qp.parse(query_txt)
            res2 = searcher2.search(query2, limit=5)
            print(f'Found {len(res2)} results:')
            for (i, x2) in enumerate(res2):
                dateyear = str(x2.get('release_date'))[0:4]
                dictel2[f"{x2['name']}{dateyear}"] = x2
            
        print("\n")
        
        results = []
        for key,val in dictel.items():
            if key in dictel2.keys():
                results.append((f"""
---------------------------------------------------------------------
{val['name']} according to igdb index: 
{val['name']} - {val['dev_companies']} {val.get('release_date')} - Score: {val.score}\n
{val['name']} according to steam index: 
{dictel2[key]['name']} - {dictel2[key]['dev_companies']} {dictel2[key].get('release_date')} - Score: {dictel2[key].score}
\nScore - {val.score + dictel2[key].score}
---------------------------------------------------------------------\n
""",val.score + dictel2[key].score))
            else:
                results.append((f"{val['name']} - {val['dev_companies']} {val.get('release_date')} - Score: {val.score}",val.score))
        
        for key,val in dictel2.items():
            if key not in dictel.keys():
                results.append((f"{val['name']} - {val['dev_companies']} {val.get('release_date')} - Score: {val.score}",val.score))
                
        for idx in sorted(results,key=lambda k:k[1],reverse=True):
            print(idx[0])
                
async def main():
    if not os.path.exists(INDEX_DIR):
        os.mkdir(INDEX_DIR)
    storage = FileStorage(INDEX_DIR)

    igdbIndex = await igdb.init_index(storage)
    steamIndex = await steam.init_index(storage)
    await test(igdbIndex,steamIndex)
   
    #await steam.test(steamIndex)

    
                

if __name__ == '__main__':
    asyncio.run(main())
