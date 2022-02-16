import math
from typing import NamedTuple

from whoosh.matching import ListMatcher, AndMaybeMatcher
from whoosh.query import Query
from whoosh.searching import Searcher, Hit


def random_access_score(query: Query, searcher: Searcher, uuid: str) -> tuple[int, float]:
    # Yes, I wrote this, but I think it's using arcane magic.
    # Staring too deep into a dynamically-typed codebase does this, be warned.
    # On a serious note, this IS efficient, the first time AndMaybeMatcher is called
    # it skips all the others ids (it calls matcher.skip_to(docid))
    docid = searcher.document_number(uuid=uuid)
    if docid:
        for subsearcher, offset in searcher.leaf_searchers():
            m = query.matcher(subsearcher, context=searcher.context())
            m = AndMaybeMatcher(ListMatcher([docid], [0]), m)
            if m.is_active():
                return m.id(), m.score()
    # Necessary in case of no hit for docid
    return -1, 0

# We use a normal Top-K threshold algorithm, but we need to change the scoring aggregation function.
# Since we can't discriminate between how many sources an entity is found in (a game is still important
# even if it's not sold on steam) we can't use a sum $Sc_a = sum(a)$, but we need to find something more complex.
# An average of the score between sources where the entity is present would be perfect.
# We can model an entity not being in a source as having score zero, then our scoring aggregation function would be
# $Sc_x = sum(Sc_i for i in x) / sum(i > 0 for i in x)
# This is NOT a monotonic function, there's a "jump" when a score hits zero, so we can't rely on previous work.
# Let's begin by shredding some initial hypothesis:
# Our scoring aggregation function cannot be the average of the last row seen:
#   given this input [(5, A)], [(1, B)] this version of the threshold would give us
#   threshold = (5+1)/2 = 3, but we can see that the entity A has a score that is higher than the threshold.
#   It would work if in the second column there would be another hit for A (since the average would be <= 5)
#   But we cannot be sure that every entity has instances in every index.
# Our scoring aggregation function must then be the maximum value of the last row seen:
# ------------------------------------------------------- PROOF --------------------------------------------------------
# Proof that "the maximum value of the last row" is an acceptable threshold function.
#   Let's prove this by contradiction.
#   Let's assume that there is an entity X, below our last row, that has average score > threshold.
#   At least one score of X must be >= of the average, and since Sc(X) > threshold
#   at least one score of X must be > threshold, but this is impossible since the threshold is
#   the maximum value in the current row, and all the columns are in decreasing order.
# This proves that this is a possible threshold value, but to prove that it's the minimum possible threshold value
# we shall also prove that with a value that is less than the maximum of the current row, there would be a case in which
# the threshold invariant does not hold.
# This is a bit more complex, we'll assume that the scoring aggregation function can only access the current row.
# (if it can check all the rows it can simulate the algorithm and compute the perfect threshold)
#   Given theoretical threshold Y < max(x.score for x in current_row):
#   If the next row has the same values as the current row, but their entities are singular (only found in that
#   particular column) the maximum score achievable by all the entities is max(x.score for x in next_row).
#   Since the values are equal to the current row max(x.score for x in next_row) = max(x.score for x in current_row) > Y
#   So the threshold is incorrect.
#   (we need to assume a second row with different entities since the hypothetical threshold function
#   could also use entities in its input)
# So our threshold function is both acceptable and minimal given our score aggregation function.


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
        threshold = 0
        
        # compute one "row" of results at a time, ie: all first results, then all second results
        for res, searcher, index_name in results:
            if i < len(res):
                current_hit = res[i]

                # update threshold
                threshold = max(threshold, current_hit.score)
                
                # check duplicates
                if current_hit['uuid'] not in visited:
                    # update visited docs
                    visited.add(current_hit['uuid'])
                    # initialize top score
                    top_score = current_hit.score
                    # initialize list of doc variants
                    doclist = [(current_hit, index_name)]  # type: list[tuple[Hit, str]]
                    index_count = 1

                    for other_searcher, other_name in [src for src in searchers_idxs if src[0] != searcher]:
                        # get doc id and score
                        found_index, found_score = random_access_score(query, other_searcher, current_hit['uuid'])
                        if found_index == -1:
                            continue  # Not present
                        # update score
                        top_score += found_score
                        index_count += 1
                        # find exact doc and append it
                        el = other_searcher.ixreader.stored_fields(found_index)
                        doclist.append((el, other_name))
                    
                    # insert into topk results
                    topk.append(AggregateHit(doclist, top_score / index_count))

                # check length and remove top k with smallest score if needed
                if len(topk) > k:
                    topk.remove(min(topk, key=lambda x: x.total_score))
        
        # check if threshold smaller than all top-k results and stop iterating in case
        if len(topk) >= k and all(score >= threshold for hits, score in topk):
            break
        
    return sorted(topk, key=lambda x: x.total_score, reverse=True)
        

