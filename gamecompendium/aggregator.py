
from typing import List, Optional

from whoosh.matching import IntersectionMatcher, ListMatcher
from whoosh.query import Query
from whoosh.searching import Searcher


def random_access_score(query: Query, searcher: Searcher, uuid: str) -> Optional[tuple]:
    # Yes, I wrote this, but I think it's using arcane magic.
    # Staring too deep into a dinamically-typed codebase does this, be warned.
    # On a serious note, this IS efficient, the first time IntersectionMatcher is called
    # it skips all of the others ids (it calls matcher.skip_to(docid))
    docid = searcher.document_number(uuid=uuid)
    if docid:
        for subsearcher, offset in searcher.leaf_searchers():
            m = query.matcher(subsearcher, context=searcher.context())
            m = IntersectionMatcher(ListMatcher([docid], [0]), m)
            if m.is_active():
                return m.id(), m.score()
    #necessary in case of no hit for docid
    return (0,0)


def aggregate_search(query: Query, searchers: List[Searcher], weights: List[int], k: int, limit=10):
    # Threshold algorithm
    #results = [s.search(query, limit=limit) for s in searchers]
    results = []
    for s in searchers:
        #include searcher too for exclusion in subsequent score calculation from other searchers
        results.append((s.search(query,limit=limit),s))
    # TODO
    topk = []
    
    #only iterate for the lenght of the smallest hit collection
    for i in range(min([len(res[0]) for res in results])):
        print(f"Iteration n. {i+1}")
        threshold = 0
        
        #compute one "row" of results at a time, ie: all first results, then all second results
        for res in results:
            
            #obtain score for every index/searcher
            topscore = 0
            for s in [src for src in searchers if src != res[1]]:
                #print(s)
                #print(res[0][i]['uuid'])
                topscore += random_access_score(query,s,res[0][i]['uuid'])[1]
                
            #check duplicates
            if res[0][i]['uuid'] not in [el[0]['uuid'] for el in topk]:
                topk.append((res[0][i],topscore+res[0][i].score))
                threshold += res[0][i].score
                
            #check lenght
            if len(topk) > k:
                el = [topk[i] for i in range(len(topk)) if topk[i][1] == min([top_el[1] for top_el in topk]) ][0]
                topk.remove(el)
            
            
        print("----------------------------------------------")
        for el in topk:
            print(el[0]['name'])
            print(el[1])
        print(f"threshold: {threshold}")
        print("----------------------------------------------")
        
        #check if threshold smaller than all top-k results and stop iterating in case
        tsmaller = True
        for el in topk:
            if threshold > el[1] :
                tsmaller = False
                
        if tsmaller==True:
            break
        
        

