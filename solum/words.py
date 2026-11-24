"""Plain-English pieces shared by the sentences the app shows."""


def listed(words: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    return " and ".join([", ".join(words[:-1]), words[-1]] if len(words) > 1 else words)
