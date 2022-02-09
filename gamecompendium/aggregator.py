
from typing import List, Optional

from whoosh.matching import IntersectionMatcher, ListMatcher
from whoosh.query import Query
from whoosh.searching import Searcher
from whoosh.index import Index
import re

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
    # necessary in case of no hit for docid
    return (0,0)


def aggregate_search(query: Query, indexes: List[Index], weights: List[int], k: int, limit=100000):
    # Threshold algorithm
    
    # create searcher,indexname structure for future need to associate index names
    searchers_idxs = [(idx.searcher(),idxname) for idxname,idx in indexes.items()]
    
    results = []
    for s in searchers_idxs:
        # include searcher too for exclusion in subsequent score calculation from other searchers
        # include index name so every result can be associated with its origin index
        results.append((s[0].search(query,limit=limit),s[0],s[1]))
   
    topk = []
    # iterate for max lenght
    visited = []
    for i in range( max( [len(res[0]) for res in results] )):
        print("\n\n___________________________________________________________________________________________________________________________")
        print(f"Iteration n. {i+1}")
        threshold = 0
        
        # compute one "row" of results at a time, ie: all first results, then all second results
        for res in results:
            
            if i < len(res[0]):
               
                # update threshold
                threshold += res[0][i].score
                
                # check duplicates
                if res[0][i]['uuid'] not in visited:
                    # update visited docs
                    visited.append(res[0][i]['uuid'])
                    # initialize top score
                    top_score = 0
                    # initialize list of doc variants
                    doclist = [(res[0][i],res[2])]
                    for s in [src for src in searchers_idxs if src[0] != res[1]]:
                        # get doc id and score
                        doc_found = random_access_score(query,s[0],res[0][i]['uuid'])
                        # update score
                        top_score += doc_found[1]
                        # find exact doc and append it
                        el = s[0].ixreader.stored_fields(doc_found[0])
                        doclist.append((el,s[1]))
                    
                    #insert into topk results
                    topk.append((doclist, top_score+res[0][i].score))
                    
                
                # check lenght and remove top k with smallest score if needed
                if len(topk) > k:
                    el = [topk[i] for i in range(len(topk)) if topk[i][1] == min([top_el[1] for top_el in topk]) ][0]
                    topk.remove(el)
            
            
        
        # print process
        itr = 1
        for el in topk:
            print("\n\n\n***********************")
            print(f"Result n. {itr}: ")
            print("***********************")
            itr += 1
            for list_el in el[0]:
                # regex filter for html tags
                summary = list_el[0]['summary'][0:150]
                summary = re.sub("\<(.*?)\>","",summary)
                
                print("------------------------")
                print(f"{list_el[0]['name']}")
                print(f"According to {list_el[1]}")
                #print(f"{list_el[0].score}")
                print(f"\n\"{summary}...\"")
                print("------------------------\n")
            print(".................")
            print(f"Score {el[1]}")
            print(".................")
        print(f"\nthreshold: {threshold}")
        print("___________________________________________________________________________")
        
        # check if threshold smaller than all top-k results and stop iterating in case
        tsmaller = True
        for el in topk:
            if threshold > el[1] :
                tsmaller = False
                
        if tsmaller==True and len(topk) >= k:
            #print("break")
            break
        
        

