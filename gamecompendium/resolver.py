import datetime
import sys
import traceback
from typing import List, Dict, Optional, Tuple

from whoosh import fields
from whoosh.fields import Schema
from whoosh.index import Index
from whoosh.qparser import QueryParser
from whoosh.query import And, Term, AndMaybe, Query, DateRange

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

# This module should map game description to game entities.
# But how can it be done? Game Entities are not well defined, we can't use humans to resolve entities
# We need a way to find a game given its information, and that is something our search engine could do!
# This is where our method, "recursive entity resolving" is born.
# Every entity will have an associated random UUID, game instance have an appropriate "uuid" field.
# The first source can generate every UUID randomly since any game is it's own entity
# From the second source we should check if a game is new or has already an entity, to do so
# we search our current indexes using the top-k query aggregator.
# And that's what the first version did, nothing too strange, it would pick the first result from the top-1
# (when present) and use that unless it was already used (a.k.a. a conflict).
# Now we use a more advanced algorithm that removes conflicts, but has to make another pass on the data.
#
# So, before exploring the new algorithm, let's explore some theory.
# We can see our resolver algorithm as an algorithm on a bipartite graph.
# On the left side, we have games, on the right side game entities, the edges are very sparse and
# represent the similarity between a game and an entity, when a game has no edge we shall create a new entity (uuid).
# The weights of the arcs are the similarities between games and entities, if it's higher we are "surer" that
# the game is an instance of that entity.
# The algorithm should select for every ENTITY ONLY the edge that has the highest weight, and should have AT MOST
# one entity for each game.
# If we have entity 3 that has both "Portal" with a weight of 2 and "Portal 2" with a weight of 3
# we should only select "Portal 2", "Portal" will need to have another entity (or create its own).
# This is why we need to have two passes, the algorithm is entity-centric.
# If there's a game A that has entity 1 as it's first choice, in a one-pass algorithm we should select edge A-1,
# but what if later in the graph we visit a game B that has higher similarity, we should backtrack our choice, select
# B-1, unselect A-1 and find another candidate for A. This cannot be done (easily) when our game is indexed.
#
# Our current algorithm works as follows:
# In the first pass, for every game we discover a predetermined number of edges (5 currently),
# We remove the ones that have an already assigned entity with higher similarity value, and we assign the remaining one
# to that game. If there was another game with that same entity but a lower similarity value we select another candidate
# and to the same, backtracking down until a game is left with no candidates, or until we assign it to an entity without
# previous contenders.
# This algorithm is O(N^2) in it's worst case, since each new game could backtrack all of previous selections, but since
# the graph is really sparse the runtime behaviour approximates O(N).


class EntityResolver:
    def __init__(self, *indexes: Index):
        self.indexes = indexes
        self.searchers = [x.searcher() for x in indexes]
        # UUID -> id, score  (selected edge)
        self.uuid_to_id = dict()  # type: Dict[str, tuple[object, float]]
        # id => list[uuid, score]  (candidates, first one must always be the selected edge)
        self.id_to_uuids = dict()  # type: Dict[object, list[tuple[str, float]]]
        self.generated = 0
        self.reused = 0

    def reset(self):
        self.uuid_to_id.clear()
        self.id_to_uuids.clear()
        self.generated = 0
        self.reused = 0

    def _query_best(self, query: Query) -> list[Tuple[str, float]]:
        """
        Queries the searchers for an aggregate result set given a query

        :param query: The query
        :return: a list of tuples (entity UUID, collective score)
        """
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
        """
        Checks if the resolver needs a pre-visit to compute associated entities

        :return: true only if a pre-visit is needed
        """
        return len(self.indexes) > 0

    def compute(self, index_id: object, name: str, dev_companies: List[str], release_date: Optional[datetime.datetime]) -> None:
        """
        Adds a game and its info to the system, to calculate the entity, should only be called in the first pass

        :param index_id: private id of the index
        :param name: name of the game
        :param dev_companies: dev companies (if known, else empty array)
        :param release_date: release date if known
        """
        if len(self.indexes) == 0:
            return

        name_parser = QueryParser('name', general_schema, [])
        query = name_parser.parse(name)

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

        # Add node and edges to the graph, select the active edge for the game (if any) and
        # backtrack choices if necessary
        self._backtrack_add_edges(index_id, res)

    def get_id(self, index_id: object) -> str:
        """
        Resolves the entity of the game given its index id.

        This should only be called in the second phase (or if needs_previsit returns False), else it can
        return partial results.
        :param index_id: internal index id of the game
        :return: UUID of the entity
        """
        gid = self.id_to_uuids.get(index_id, ((None, 0),))[0][0]
        if gid is None:
            self.generated += 1
            gid = uuid4().hex
        else:
            self.reused += 1
        return gid
