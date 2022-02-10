import math
from typing import NamedTuple

from whoosh.matching import IntersectionMatcher, ListMatcher
from whoosh.query import Query
from whoosh.searching import Searcher, Hit
from whoosh.index import Index
import re


def random_access_score(query: Query, searcher: Searcher, uuid: str) -> tuple[int, float]:
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
    return -1, 0


class AggregateHit(NamedTuple):
    # Hits from various searchers with their searcher name
    hits: list[tuple[Hit, str]]
    total_score: float


def aggregate_search(query: Query, searchers_idxs: list[tuple[Searcher, str]], k: int, limit=math.inf) -> list[AggregateHit]:
    # Threshold algorithm
    
    results = []  # list[(result, searcher, index_name)]
    for s in searchers_idxs:
        # include searcher too for exclusion in subsequent score calculation from other searchers
        # include index name so every result can be associated with its origin index
        results.append((s[0].search(query, limit=limit), s[0], s[1]))
   
    topk = []
    # iterate for max length
    visited = set()
    for i in range(max([len(res[0]) for res in results])):
        print("\n\n___________________________________________________________________________________________________________________________")
        print(f"Iteration n. {i+1}")
        threshold = 0
        
        # compute one "row" of results at a time, ie: all first results, then all second results
        for res, searcher, index_name in results:
            if i < len(res):
                current_hit = res[i]

                # update threshold
                threshold += current_hit.score
                
                # check duplicates
                if current_hit['uuid'] not in visited:
                    # update visited docs
                    visited.add(current_hit['uuid'])
                    # initialize top score
                    top_score = 0
                    # initialize list of doc variants
                    doclist = [(current_hit, index_name)]  # type: list[tuple[Hit, str]]
                    for other_searcher, other_name in [src for src in searchers_idxs if src[0] != searcher]:
                        # get doc id and score
                        found_index, found_score = random_access_score(query, other_searcher, current_hit['uuid'])
                        if found_index == -1:
                            continue  # Not present
                        # update score
                        top_score += found_score
                        # find exact doc and append it
                        el = other_searcher.ixreader.stored_fields(found_index)
                        doclist.append((el, other_name))
                    
                    # insert into topk results
                    topk.append(AggregateHit(doclist, top_score + current_hit.score))

                # check length and remove top k with smallest score if needed
                if len(topk) > k:
                    topk.remove(min(topk, key=lambda x: x.total_score))
        
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
                summary = re.sub(r"<(.*?)>", "", summary)  # Remove HTML tags

                print("------------------------")
                print(f"{list_el[0]['name']}")
                print(f"According to {list_el[1]}")
                # print(f"{list_el[0].score}")  # Used for single-score debugging
                print(f"\n\"{summary}...\"")
                print("------------------------\n")
            print(".................")
            print(f"Score {el[1]}")
            print(".................")
        print(f"\nthreshold: {threshold}")
        print("___________________________________________________________________________")
        
        # check if threshold smaller than all top-k results and stop iterating in case
        if len(topk) >= k and all(score >= threshold for hits, score in topk):
            #print("break")
            break
    return topk
        

