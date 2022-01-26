
from typing import List, Optional

from whoosh.matching import IntersectionMatcher, ListMatcher
from whoosh.query import Query
from whoosh.searching import Searcher


def random_access_score(query: Query, searcher: Searcher, uuid: str) -> Optional[(int, int)]:
    # Yes, I wrote this, but I think it's using arcane magic.
    # Staring too deep into a dinamically-typed codebase does this, be warned.
    # On a serious note, this IS efficient, the first time IntersectionMatcher is called
    # it skips all of the others ids (it calls matcher.skip_to(docid))
    docid = searcher.document_number(uuid=uuid)
    for subsearcher, offset in searcher.leaf_searchers():
        m = query.matcher(subsearcher, context=searcher.context())
        m = IntersectionMatcher(ListMatcher([docid]), m)
        if m.is_active():
            return m.id(), m.score()


def aggregate_search(query: Query, searchers: List[Searcher], weights: List[int], limit=10):
    # Threshold algorithm
    results = [s.search(query, limit=limit) for s in searchers]
    # TODO


