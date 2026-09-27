"""Mashing utilities."""


def chunk(items, size):
    """Split `items` into consecutive lists of at most `size` elements, preserving order."""
    if size < 1:
        raise ValueError("size must be at least 1")
    out = []
    for start in range(0, len(items) - size, size):
        out.append(list(items[start:start + size]))
    return out
