"""Small-sample statistics (plan §26): Wilson intervals for rates, percentile bootstrap for means,
exact McNemar for paired hit@k, paired bootstrap for paired mean differences.

All resampling uses a fixed seed so reports are reproducible.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

Z95 = 1.959963984540054
BOOTSTRAP_SAMPLES = 10_000
SEED = 20261005


@dataclass(frozen=True, slots=True)
class Interval:
    estimate: float
    low: float
    high: float

    def as_dict(self) -> dict[str, float]:
        return {"estimate": self.estimate, "low": self.low, "high": self.high}


def wilson(successes: int, n: int, z: float = Z95) -> Interval:
    if n == 0:
        return Interval(0.0, 0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half))


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    pos = q * (len(sorted_values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_mean(
    values: Sequence[float], samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED
) -> Interval:
    n = len(values)
    if n == 0:
        return Interval(0.0, 0.0, 0.0)
    rng = random.Random(seed)  # noqa: S311 - reproducible resampling, not cryptography
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(samples))
    return Interval(sum(values) / n, _percentile(means, 0.025), _percentile(means, 0.975))


def paired_bootstrap_diff(
    a: Sequence[float], b: Sequence[float], samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED
) -> Interval:
    """CI for mean(b - a) over paired items."""
    if len(a) != len(b):
        raise ValueError("paired samples must have equal length")
    return bootstrap_mean([y - x for x, y in zip(a, b, strict=True)], samples, seed)


@dataclass(frozen=True, slots=True)
class McNemar:
    only_a: int  # items A hits and B misses
    only_b: int
    p_value: float


def mcnemar_exact(a_hits: Sequence[bool], b_hits: Sequence[bool]) -> McNemar:
    """Two-sided exact (binomial) McNemar test on discordant pairs."""
    if len(a_hits) != len(b_hits):
        raise ValueError("paired samples must have equal length")
    only_a = sum(1 for x, y in zip(a_hits, b_hits, strict=True) if x and not y)
    only_b = sum(1 for x, y in zip(a_hits, b_hits, strict=True) if y and not x)
    n = only_a + only_b
    if n == 0:
        return McNemar(only_a, only_b, 1.0)
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return McNemar(only_a, only_b, min(1.0, 2 * tail))


def percentile(values: Sequence[float], q: float) -> float:
    return _percentile(sorted(values), q)
