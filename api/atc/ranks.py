"""Sortable ranks: keys that order bytewise (matching Postgres COLLATE "C") with room between any two.

Keys are strings over 0-9A-Za-z (62 symbols, ASCII-ordered), read as base-62 fractions with
implicit trailing zeros. A key never ends in "0", so there is always room before any key.
"""

import string

ALPHABET = string.digits + string.ascii_uppercase + string.ascii_lowercase
BASE = len(ALPHABET)
_VALUE = {c: i for i, c in enumerate(ALPHABET)}


def _digit(s: str, i: int) -> int:
    return _VALUE[s[i]] if i < len(s) else 0


def _mid(a: str, b: str | None) -> str:
    """Key strictly between a and b (b None = open end); a < b, b does not end in "0"."""
    if b is not None:
        n = 0
        while _digit(a, n) == _VALUE[b[n]]:
            n += 1
        if n:
            return b[:n] + _mid(a[n:], b[n:])
    lo = _digit(a, 0)
    hi = BASE if b is None else _VALUE[b[0]]
    if hi - lo > 1:
        return ALPHABET[(lo + hi) // 2]
    if b is not None and len(b) > 1:
        return b[0]
    return ALPHABET[lo] + _mid(a[1:], None)


def between(lo: str | None, hi: str | None) -> str:
    """A key strictly between lo and hi in byte order (None = open end)."""
    for k in (lo, hi):
        if k is not None and (not k or any(c not in _VALUE for c in k)):
            raise ValueError(f"invalid rank {k!r}")
    if hi is not None and hi.endswith("0"):
        raise ValueError(f"invalid rank {hi!r}: ends in 0")
    if lo is not None and hi is not None and lo >= hi:
        raise ValueError(f"lower bound {lo!r} is not below upper bound {hi!r}")
    return _mid(lo or "", hi)


def after(last: str | None) -> str:
    return between(last, None)
