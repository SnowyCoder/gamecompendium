from whoosh.analysis import RegexTokenizer, default_pattern, LowercaseFilter, StopFilter, Analyzer


def keep_numbers_analyzer() -> Analyzer:
    """
    Same as the StandardAnalyzer but keeps singular numbers and letters (ex. "a Portal 2" => ["a", "Portal", "2"].
    Quite useful in games as you might guess.
    :return: Analyzer
    """
    # To keep numbers but not character we use the regular StopFilter with a minsize=1 (so it will keep every short
    # word) and pipe it with a regex filter that removes single chars.
    ret = RegexTokenizer(expression=default_pattern)
    chain = ret | LowercaseFilter() | StopFilter(minsize=1)
    return chain
