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


# A generated key longer than this makes the caller re-rank its list (moves.place, reconcile), so
# keys stay short however many cards are dropped at the same end of a column.
REBALANCE_LENGTH = 24


def _mid(a: str, b: str | None) -> str:
    """Key strictly between a and b (b None = open end); a < b, b does not end in "0".

    Iterative: a deep key (thousands of digits) costs a loop, never a recursion.
    """
    out: list[str] = []
    i = 0
    if b is not None:
        while _digit(a, i) == _VALUE[b[i]]:  # the shared prefix; b cannot run out first as a < b
            out.append(b[i])
            i += 1
    while True:
        lo = _digit(a, i)
        hi = BASE if b is None else _VALUE[b[i]]
        if hi - lo > 1:
            out.append(ALPHABET[(lo + hi) // 2])
            return "".join(out)
        if b is not None and len(b) > i + 1:
            out.append(b[i])
            return "".join(out)
        # No room at this digit: keep a's digit and look for room below the open end.
        out.append(ALPHABET[lo])
        b = None
        i += 1


def _increment(a: str) -> str:
    """The shortest key above a: its first digit that is not the top one, plus one.

    Appending this way grows keys by one digit every 61 appends at worst (and shortens long keys),
    where a midpoint towards the open end grew one digit every six.
    """
    for i, c in enumerate(a):
        if c != ALPHABET[-1]:
            return a[:i] + ALPHABET[_VALUE[c] + 1]
    return a + ALPHABET[1]


def _validate(lo: str | None, hi: str | None) -> None:
    for k in (lo, hi):
        if k is not None and (not k or any(c not in _VALUE for c in k)):
            raise ValueError(f"invalid rank {k!r}")
    if hi is not None and hi.endswith("0"):
        raise ValueError(f"invalid rank {hi!r}: ends in 0")
    if lo is not None and hi is not None and lo >= hi:
        raise ValueError(f"lower bound {lo!r} is not below upper bound {hi!r}")


def between(lo: str | None, hi: str | None) -> str:
    """A key strictly between lo and hi in byte order (None = open end)."""
    _validate(lo, hi)
    if hi is None:
        return ALPHABET[BASE // 2] if lo is None else _increment(lo)
    return _mid(lo or "", hi)


def after(last: str | None) -> str:
    return between(last, None)


def spread(n: int) -> list[str]:
    """n keys in ascending order, evenly spaced and all as short as n allows (for re-ranking a list)."""
    length = 1
    while BASE**length <= n:
        length += 1
    span = BASE**length
    keys = []
    for i in range(1, n + 1):
        value = i * span // (n + 1)  # strictly increasing and non-zero, as span > n
        digits = []
        for _ in range(length):
            value, d = divmod(value, BASE)
            digits.append(ALPHABET[d])
        keys.append("".join(reversed(digits)).rstrip(ALPHABET[0]))
    return keys
