from dataclasses import dataclass
from typing import TextIO, Optional

import re


@dataclass
class BenchmarkEntry:
    relevance: int
    source: str
    id: str


@dataclass
class Benchmark:
    query: str
    scores: list[BenchmarkEntry]


@dataclass
class BenchmarkSuite:
    benchmarks: list[Benchmark]


@dataclass
class BenchmarkResult:
    query: str
    raw: list[int]


# query portal 2 # comment
QUERY_REGEX = re.compile(r'^query\s+([^#]+?)\s*(?:#.*)?$', re.IGNORECASE)
# 3 steam 24201 # comment
ENTRY_REGEX = re.compile(r'^(\d+)\s+(\w+)\s+(\w+)\s*(?:#.*)?$')


def parse_suite(lines: TextIO) -> BenchmarkSuite:
    res: list[Benchmark] = []
    query: Optional[str] = None
    entries: list[BenchmarkEntry] = []

    def end_query():
        if query is not None:
            res.append(Benchmark(query, entries))

    rown = 0
    for line in lines:
        rown += 1
        line = line.strip()
        if line == "":
            continue
        if match := QUERY_REGEX.fullmatch(line):
            end_query()
            query = match.groups()[0]
            entries = []
        elif match := ENTRY_REGEX.fullmatch(line):
            if query is None:
                raise ValueError(f"Found entry before any query at line {rown}")

            rel, source, doc_id = match.groups()
            entries.append(BenchmarkEntry(int(rel), source, doc_id))
        else:
            raise ValueError(f"Cannot read benchmark file! syntax error at line {rown}")

    end_query()
    return BenchmarkSuite(res)
