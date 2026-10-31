# SPDX-License-Identifier: LGPL-3.0-or-later

import pytest

from jupedsim_repertoires.sampling import SplitMix64, reservoir


def test_splitmix64_vectors():
    vectors = {
        0: [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F],
        42: [0xBDD732262FEB6E95, 0x28EFE333B266F103, 0x47526757130F9F52],
    }
    for seed, expected in vectors.items():
        rng = SplitMix64(seed)
        assert [rng.next_u64() for _ in range(3)] == expected


def test_uniform_sequence():
    rng = SplitMix64(42)
    assert [rng.uniform(10) for _ in range(5)] == [3, 1, 8, 4, 0]


def test_uniform_full_range():
    assert SplitMix64(42).uniform(2**64) == SplitMix64(42).next_u64()


def test_uniform_rejects_non_positive():
    with pytest.raises(ValueError):
        SplitMix64(0).uniform(0)


def test_seed_range_validated():
    for seed in (-1, 2**64):
        with pytest.raises(ValueError):
            SplitMix64(seed)


def test_reservoir_pinned():
    keys = [(i % 3, i // 3) for i in range(20)]
    assert reservoir(keys, 5, 42) == [(0, 1), (1, 2), (0, 3), (2, 3), (0, 6)]
    assert reservoir(keys, 5, 0) == [(2, 0), (0, 1), (1, 3), (1, 4), (0, 6)]
    assert reservoir(keys, 1, 7) == [(2, 0)]
    assert reservoir(keys, 50, 1) == keys


def test_reservoir_rejects_bad_arguments():
    for size, seed in ((0, 0), (5, -1), (5, 2**64)):
        with pytest.raises(ValueError):
            reservoir([1, 2, 3], size, seed)
