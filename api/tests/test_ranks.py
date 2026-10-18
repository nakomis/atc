import random

import pytest

from atc.ranks import after, between, spread


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


def test_ten_thousand_appends_stay_ordered_and_short():  # final review I2
    keys = [after(None)]
    for _ in range(10_000):
        keys.append(after(keys[-1]))
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert not any(k.endswith("0") for k in keys)
    assert max(map(len, keys)) <= 10_000 // 61 + 2  # one digit per 61 appends, not per six


def test_after_shortens_a_long_key():
    assert after("a5Qzz") == "b"
    assert after("zzz") == "zzz1"


def test_deep_keys_need_no_recursion():
    deep = "V" + "z" * 5000
    k = between(deep, "W")
    assert deep < k < "W"
    assert "V" < between("V", "V" + "0" * 4000 + "1") < "V" + "0" * 4000 + "1"
    assert after("z" * 5000) > "z" * 5000


@pytest.mark.parametrize("n", [0, 1, 2, 61, 62, 500, 3844, 5000])
def test_spread_is_ordered_unique_and_short(n):
    keys = spread(n)
    assert len(keys) == n and keys == sorted(keys) and len(set(keys)) == n
    assert all(k and not k.endswith("0") for k in keys)
    assert all(len(k) <= 3 for k in keys)
