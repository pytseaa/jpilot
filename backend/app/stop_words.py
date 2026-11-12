"""The one English stop list. It cleans the keywords Qwen proposes, and later the search itself."""

STOP_WORDS = frozenset("""
a an and as at be but by for from in into is it of on or the to with
ability able candidate company good great knowledge level looking need needed
responsibilities responsibility responsible role roles skill skills strong team teams
work working worked year years experience experienced
""".split())


def remove(keywords):
    """Drop each keyword whose every word is a stop word. A longer phrase with a real word stays."""
    # An empty or blank keyword has no words, so it is dropped too.
    return [kw.strip() for kw in keywords
            if not all(word in STOP_WORDS for word in kw.lower().split())]
