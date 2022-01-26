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

from analyzers import keep_numbers_analyzer

general_schema = Schema(
    name=fields.TEXT(stored=True, analyzer=keep_numbers_analyzer()),
    dev_companies=fields.KEYWORD(stored=True),
    release_date=fields.DATETIME(stored=True),
    summary=fields.TEXT(stored=True),
)


class EntityResolver:
    def __init__(self, *indexes: Index):
        self.indexes = indexes
        self.searchers = [x.searcher() for x in indexes]
        self.mapping = dict()  # type: Dict[str, object]
        self.generated = 0
        self.reused = 0
        self.conflicts = 0

    def reset(self):
        self.mapping.clear()
        self.generated = 0
        self.reused = 0
        self.conflicts = 0

    def _query_best(self, query: Query) -> Optional[Tuple[str, str]]:
        # TODO: replace with query aggregator
        if len(self.searchers) == 1:
            # Little optimization
            for x in self.searchers[0].search(query, limit=1):
                return x['uuid'], x['name']
            return None

        data = {}
        for searcher in self.searchers:
            res = searcher.search(query, limit=5)
            for x in res:
                uid = x['uuid'], x['name']
                data[uid] = data.get(uid, 0) + x.score

        return max(data.items(), key=lambda k: k[1], default=[None])[0]

    def compute_id(self, index_id: object, name: str, dev_companies: List[str], release_date: Optional[datetime.datetime]) -> str:
        if len(self.indexes) == 0:
            self.generated += 1
            gid = uuid4().hex
            self.mapping[gid] = index_id
            return gid


        full_name_parser = ConstantScoreQuery(Phrase('name', [x.lower() for x in name.split(' ') if len(x) > 0]), 100000)
        name_parser = QueryParser('name', general_schema, [])
        name_query = name_parser.parse(name)

        query = Or([full_name_parser, name_query])
        if release_date is not None:
            td = datetime.timedelta(weeks=4) / 2
            year_query = DateRange('release_date', release_date - td, release_date + td, boost=10)
            query = AndMaybe(
                    query,
                    year_query
            )

        if len(dev_companies) > 0:
            dev_query = And([Term('dev_companies', x) for x in dev_companies], boost=20)
            query = AndMaybe(
                query,
                dev_query,
            )

        try:
            res = self._query_best(query)
        except:
            print("Whoosh exception on query: " + repr(query), file=sys.stderr)
            traceback.print_exc()
            res = None
        gid, gname = res if res is not None else (None, None)
        reused = True
        if gid is None:
            gid = uuid4().hex
            self.generated += 1
            reused = False

        if gid in self.mapping:
            print(f"Conflict - {gid} ({gname}) already assigned to {self.mapping[gid]}, trying to assign to {index_id}")
            gid = uuid4().hex
            self.conflicts += 1
            reused = False

        self.reused += reused
        self.mapping[gid] = index_id

        return gid
