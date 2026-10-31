# SPDX-License-Identifier: LGPL-3.0-or-later

"""Reproducible sampling shared with the Rust twin of extract-situations."""

from collections.abc import Iterable
from typing import TypeVar

K = TypeVar("K")

_MASK = 0xFFFF_FFFF_FFFF_FFFF
_TWO_64 = 1 << 64


def _check_seed(seed: int) -> None:
    if not 0 <= seed < _TWO_64:
        raise ValueError(f"seed must satisfy 0 <= seed < 2**64, got {seed}")


class SplitMix64:
    """SplitMix64 generator with wrapping 64-bit arithmetic.

    Args:
        seed: Initial state, 0 <= seed < 2**64.
    """

    def __init__(self, seed: int) -> None:
        _check_seed(seed)
        self._state = seed

    def next_u64(self) -> int:
        """Return the next raw 64-bit output."""
        self._state = (self._state + 0x9E3779B97F4A7C15) & _MASK
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        return z ^ (z >> 31)

    def uniform(self, m: int) -> int:
        """Return an exactly uniform integer in [0, m) by rejection."""
        if m < 1:
            raise ValueError(f"m must be >= 1, got {m}")
        limit = _TWO_64 - (_TWO_64 % m)
        u = self.next_u64()
        while u >= limit:
            u = self.next_u64()
        return u % m


def reservoir(keys: Iterable[K], size: int, seed: int) -> list[K]:
    """Sample ``size`` keys uniformly (Algorithm R), in original order.

    Args:
        keys: Keys in log order.
        size: Reservoir size, >= 1.
        seed: SplitMix64 seed, 0 <= seed < 2**64.

    Returns:
        The selected keys in their original order.
    """
    if size < 1:
        raise ValueError(f"size must be >= 1, got {size}")
    rng = SplitMix64(seed)
    slots: list[tuple[int, K]] = []
    for i, key in enumerate(keys):
        if i < size:
            slots.append((i, key))
            continue
        j = rng.uniform(i + 1)
        if j < size:
            slots[j] = (i, key)
    return [key for _, key in sorted(slots, key=lambda s: s[0])]
