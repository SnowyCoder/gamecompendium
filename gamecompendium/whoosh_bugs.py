import functools

from whoosh import query, fields
from whoosh.qparser import RangeNode

# Here are some bug fixes that we duck-typed until
# https://github.com/mchaput/whoosh/pull/23 is merged upstream

# RangeNode is incorrectly marked as "non-boost-having" fix it.
RangeNode.has_boost = True


# Whoosh incorrectly forgets boost on an ambiguous field definition
def fix_parsequery(original):
    @functools.wraps(original)
    def wrapped(self, fieldname, qstring, boost=1.0):
        res = original(self, fieldname, qstring, boost=boost)
        if isinstance(res, query.NumericRange):
            res.boost = boost
        return res
    return wrapped


fields.DATETIME.parse_query = fix_parsequery(fields.DATETIME.parse_query)


def run():
    # Run on import, we're sure it gets executed once
    # Keep this method so that tools won't remove the import automatically
    pass
