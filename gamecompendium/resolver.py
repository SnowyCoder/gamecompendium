import datetime
import sys
import traceback
from typing import List, Dict, Optional, Tuple

from whoosh import fields
from whoosh.fields import Schema
from whoosh.index import Index
from whoosh.qparser import QueryParser
from whoosh.query import And, Or, Term, AndMaybe, Query, DateRange, Phrase, ConstantScoreQuery, Regex

from uuid import uuid4

import aggregator
from analyzers import keep_numbers_analyzer

general_schema = Schema(
    name=fields.TEXT(stored=True, analyzer=keep_numbers_analyzer()),
    devs=fields.KEYWORD(stored=True),
    date=fields.DATETIME(stored=True),
    summary=fields.TEXT(stored=True),
    storyline=fields.TEXT(stored=True),
)


class EntityResolver:
    def __init__(self, *indexes: Index):
        self.indexes = indexes
        self.searchers = [x.searcher() for x in indexes]
        # UUID -> id, score
        self.uuid_to_id = dict()  # type: Dict[str, tuple[object, float]]
        # id => list[uuid, score]
        self.id_to_uuids = dict()  # type: Dict[object, list[tuple[str, float]]]
        self.generated = 0
        self.reused = 0

    def reset(self):
        self.uuid_to_id.clear()
        self.id_to_uuids.clear()
        self.generated = 0
        self.reused = 0

    def _query_best(self, query: Query) -> list[Tuple[str, float]]:
        # We don't care about searcher names
        searchers = [(s, '') for s in self.searchers]
        res = aggregator.aggregate_search(query, searchers, k=5)
        return [(r.hits[0][0]['uuid'], r.total_score) for r in res]

    def _backtrack_add_edges(self, cid: object, edges: list[Tuple[str, float]]) -> None:
        """
        Adds a node cid to the graph, trying all the edges

        if an edge can override the previous uuid -> id binding it's replaced and the algorithm is
        executed again to "backtrack" the adds.

        :param cid: id of the node to add (left node)
        :param edges: list of (uuid, score) (edges to the right nodes)
        """
        while True:
            while len(edges) > 0 and edges[0][1] <= self.uuid_to_id.get(edges[0][0], (None, -1))[1]:
                edges = edges[1:]

            if len(edges) <= 0:
                self.id_to_uuids.pop(cid, None)
                return

            prev_id = self.uuid_to_id.get(edges[0][0], (None,))[0]
            self.uuid_to_id[edges[0][0]] = (cid, edges[0][1])
            self.id_to_uuids[cid] = edges
            cid = prev_id
            if cid is None:
                break
            edges = self.id_to_uuids[cid]

    def needs_previsit(self) -> bool:
        return len(self.indexes) > 0

    def compute(self, index_id: object, name: str, dev_companies: List[str], release_date: Optional[datetime.datetime]):
        if len(self.indexes) == 0:
            return

        name_parser = QueryParser('name', general_schema, [])
        name_query = name_parser.parse(name)

        query = name_query
        if release_date is not None:
            td = datetime.timedelta(weeks=4) / 2
            year_query = DateRange('date', release_date - td, release_date + td, boost=0.5)
            query = AndMaybe(
                    query,
                    year_query
            )

        if len(dev_companies) > 0:
            dev_query = And([Term('devs', x) for x in dev_companies], boost=2)
            query = AndMaybe(
                query,
                dev_query,
            )
        query = query.normalize()

        try:
            res = self._query_best(query)
        except ValueError:
            print(f"Whoosh exception on query: {repr(query)} on game {index_id}", file=sys.stderr)
            traceback.print_exc()
            res = []

        if name == 'Left 4 Dead':
            print(repr(query))
            print(res)

        self._backtrack_add_edges(index_id, res)

    def get_id(self, index_id: object) -> str:
        gid = self.id_to_uuids.get(index_id, ((None, 0),))[0][0]
        if gid is None:
            self.generated += 1
            gid = uuid4().hex
        else:
            self.reused += 1
        return gid
