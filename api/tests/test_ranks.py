import random

import pytest

from atc.ranks import after, between


def test_between_open_ends():
    assert between(None, None)
    assert between(None, "V") < "V" and between("V", None) > "V"


def test_between_is_strictly_between():
    assert "a" < between("a", "b") < "b"
    assert "a" < between("a", "a0V") < "a0V"


def test_repeated_insertion_at_front_and_middle_stays_ordered():
    keys = [after(None)]
    for _i in range(500):
        keys.insert(0, between(None, keys[0]))
        mid = len(keys) // 2
        keys.insert(mid, between(keys[mid - 1], keys[mid]))
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert not any(k.endswith("0") for k in keys)


def test_between_rejects_inverted_bounds():
    with pytest.raises(ValueError):
        between("b", "a")


def test_between_rejects_equal_bounds_and_bad_characters():
    with pytest.raises(ValueError):
        between("a", "a")
    with pytest.raises(ValueError):
        between("a-", None)


def test_after_appends_repeatedly_in_order():
    keys = [after(None)]
    for _ in range(200):
        keys.append(after(keys[-1]))
    assert keys == sorted(keys) and not any(k.endswith("0") for k in keys)


def test_adjacent_keys_and_zero_padding():
    # Consecutive digits, and a lower bound that is a prefix of the upper one.
    for lo, hi in [("1", "2"), ("0V", "1"), ("a", "a1"), ("zz", None), ("", "1"), ("0V", "1V")]:
        k = between(lo or None, hi)
        assert (lo or "") < k and (hi is None or k < hi) and not k.endswith("0")


def test_random_insertions_stay_ordered():
    rng = random.Random(7)
    keys = [after(None)]
    for _ in range(2000):
        i = rng.randrange(len(keys) + 1)
        lo = keys[i - 1] if i else None
        hi = keys[i] if i < len(keys) else None
        keys.insert(i, between(lo, hi))
    assert keys == sorted(keys) and len(set(keys)) == len(keys)


def test_between_rejects_upper_bound_ending_in_zero():
    with pytest.raises(ValueError):
        between("a", "b0")
