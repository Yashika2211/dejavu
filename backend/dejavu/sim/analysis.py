"""Small numeric helpers the tools use to summarise a series: change points and sparklines."""

from dataclasses import dataclass

import numpy as np

BARS = "▁▂▃▄▅▆▇█"


@dataclass(frozen=True)
class ChangePoint:
    index: int
    before: float
    after: float


def change_point(values: np.ndarray, *, min_score: float = 6.0, min_rel: float = 0.25) -> ChangePoint | None:
    """Single most significant level shift (binary segmentation on the mean), if any."""
    n = len(values)
    if n < 8:
        return None
    best: tuple[float, int] | None = None
    for i in range(3, n - 2):
        a, b = values[:i], values[i:]
        pooled = np.sqrt((a.var() * len(a) + b.var() * len(b)) / n) + 1e-9
        score = abs(a.mean() - b.mean()) / pooled * np.sqrt(len(a) * len(b) / n)
        if best is None or score > best[0]:
            best = (float(score), i)
    if best is None or best[0] < min_score:
        return None
    i = best[1]
    before, after = float(values[:i].mean()), float(values[i:].mean())
    scale = max(abs(before), abs(after), 1e-6)
    if abs(after - before) < min_rel * scale:
        return None
    # A ramp splits in its middle; walk back to where the series first left the old level.
    spread = float(values[:i].std()) or 1e-9
    j = i
    while j > 1 and abs(values[j - 1] - before) > 3 * spread:
        j -= 1
    return ChangePoint(j, before, after)


def sparkline(values: np.ndarray, buckets: int = 24) -> str:
    chunks = [c for c in np.array_split(values, min(buckets, len(values))) if len(c)]
    means = np.array([c.mean() for c in chunks])
    lo, hi = float(means.min()), float(means.max())
    if hi - lo <= 0.03 * max(abs(hi), abs(lo), 1e-9):
        return BARS[3] * len(means)
    idx = np.round((means - lo) / (hi - lo) * (len(BARS) - 1)).astype(int)
    return "".join(BARS[i] for i in idx)
