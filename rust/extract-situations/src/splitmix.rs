// SPDX-License-Identifier: LGPL-3.0-or-later

//! SplitMix64 and reservoir sampling, identical to `jupedsim_repertoires.sampling`.

/// SplitMix64 generator; all arithmetic wraps modulo 2^64.
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    /// Create a generator whose state starts at `seed`.
    pub fn new(seed: u64) -> Self {
        SplitMix64 { state: seed }
    }

    /// Return the next raw 64-bit output.
    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }

    /// Return an exactly uniform integer in `[0, m)` by rejection; `m >= 1`.
    pub fn uniform(&mut self, m: u64) -> u64 {
        assert!(m >= 1, "m must be >= 1");
        // The limit can equal 2^64, which does not fit in u64.
        let limit = (1u128 << 64) - ((1u128 << 64) % m as u128);
        loop {
            let u = self.next_u64();
            if (u as u128) < limit {
                return u % m;
            }
        }
    }
}

/// Sample `size` keys uniformly (Algorithm R), returned in their original order.
pub fn reservoir<K: Clone>(keys: &[K], size: usize, seed: u64) -> Vec<K> {
    assert!(size >= 1, "size must be >= 1");
    let mut rng = SplitMix64::new(seed);
    // Each slot remembers the log position of its key, to restore the order.
    let mut slots: Vec<(usize, K)> = Vec::with_capacity(size.min(keys.len()));
    for (i, key) in keys.iter().enumerate() {
        if i < size {
            slots.push((i, key.clone()));
            continue;
        }
        let j = rng.uniform(i as u64 + 1) as usize;
        if j < size {
            slots[j] = (i, key.clone());
        }
    }
    slots.sort_by_key(|slot| slot.0);
    slots.into_iter().map(|(_, key)| key).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splitmix64_vectors() {
        let cases: [(u64, [u64; 3]); 2] = [
            (0, [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]),
            (42, [0xBDD732262FEB6E95, 0x28EFE333B266F103, 0x47526757130F9F52]),
        ];
        for (seed, expected) in cases {
            let mut rng = SplitMix64::new(seed);
            let got = [rng.next_u64(), rng.next_u64(), rng.next_u64()];
            assert_eq!(got, expected);
        }
    }

    #[test]
    fn uniform_sequence() {
        let mut rng = SplitMix64::new(42);
        let got: Vec<u64> = (0..5).map(|_| rng.uniform(10)).collect();
        assert_eq!(got, [3, 1, 8, 4, 0]);
    }

    #[test]
    fn uniform_power_of_two_never_rejects() {
        // For m = 2^k the limit is exactly 2^64, which only fits in u128.
        let first = SplitMix64::new(42).next_u64();
        assert_eq!(SplitMix64::new(42).uniform(1), 0);
        assert_eq!(SplitMix64::new(42).uniform(1 << 63), first % (1 << 63));
    }

    fn pinned_keys() -> Vec<(u64, u64)> {
        (0..20).map(|i| (i % 3, i / 3)).collect()
    }

    #[test]
    fn reservoir_pinned() {
        let keys = pinned_keys();
        assert_eq!(
            reservoir(&keys, 5, 42),
            [(0, 1), (1, 2), (0, 3), (2, 3), (0, 6)]
        );
        assert_eq!(
            reservoir(&keys, 5, 0),
            [(2, 0), (0, 1), (1, 3), (1, 4), (0, 6)]
        );
        assert_eq!(reservoir(&keys, 1, 7), [(2, 0)]);
        assert_eq!(reservoir(&keys, 50, 1), keys);
    }
}
