import re
from typing import Iterable, Pattern

from whoosh.analysis import Filter, Token, RegexTokenizer, default_pattern, LowercaseFilter, StopFilter, Analyzer


class RegexStopFilter(Filter):
    """Same as the regular StopWords but generalized, it takes a regex and stops any token that matches"""
    def __init__(self, pattern: Pattern, renumber=True):
        self.pattern = pattern
        self.renumber = renumber

    def __eq__(self, other):
        return (other
                and self.__class__ is other.__class__
                and self.pattern == other.pattern
                and self.renumber == other.renumber)

    def __call__(self, tokens: Iterable[Token]):
        pattern = self.pattern
        renumber = self.renumber
        # Partially copied from the original StopFilter, only generalized a bit

        pos = None
        for t in tokens:
            if t.stopped:
                continue
            if pattern.match(t.text) is None:
                # This is not a stop word
                if renumber and t.positions:
                    if pos is None:
                        pos = t.pos
                    else:
                        pos += 1
                        t.pos = pos
                t.stopped = False
                yield t
            else:
                # This is a stop word
                if not t.removestops:
                    # This IS a stop word, but we're not removing them
                    t.stopped = True
                    yield t


def keep_numbers_analyzer() -> Analyzer:
    """
    Same as the StandardAnalyzer but keeps singular numbers (ex. "a Portal 2" => ["Portal", "2"].
    Quite useful in games as you might guess.
    :return: Analyzer
    """
    # To keep numbers but not character we use the regular StopFilter with a minsize=1 (so it will keep every short
    # word) and pipe it with a regex filter that removes single chars.
    ret = RegexTokenizer(expression=default_pattern)
    chain = ret | LowercaseFilter() | StopFilter(minsize=1) |\
            RegexStopFilter(re.compile(r'^[a-z]$'))
    return chain
