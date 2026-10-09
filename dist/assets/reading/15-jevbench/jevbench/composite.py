"""JevBench v1.1 scoring: three sub-benchmarks and the Main Score.

Everything here is a pure function of published aggregates, so anyone can
recompute a system's Main Score from results/v1.1/jevbench-v1.1-results.json.

Capability  mean of the easy, standard and judge tier accuracies (1/3 each), x 100
Speed       latency t -> 100 * log10(10 s / t) / 2, clipped: 0.1 s = 100, 1 s = 50, 10 s = 0;
            Speed = mean of the p50 and p95 scores
Cost        $ per 1,000 decisions c -> 100 * log10($10 / c) / 4, clipped:
            $0.001 = 100, $0.01 = 75, $0.10 = 50, $1 = 25, $10 = 0
            (v1.1.2: four decades instead of three, so no benchmarked system sits at
            the 100 cap and every real price difference shows in the score)
Main Score  (Capability + Speed + Cost) / 3, "Balanced 33:33:33" (v1.1.2, 19 Sep 2026;
            v1.1 and v1.1.1 used 0.6 / 0.2 / 0.2, kept as the preset "Emphasis on Accuracy")

Calibration (Brier, ECE) is reported beside these, not folded in: label-only
systems have no distribution, and a penalty for that would be our invention.
"""
import math

WEIGHTS = (1 / 3, 1 / 3, 1 / 3)
COST_BEST, COST_WORST = 0.001, 10  # $ per 1,000 decisions -> 100 and 0
HEADLINE = "33/33/33 balanced (headline)"
SENSITIVITY = {
    HEADLINE: (1 / 3, 1 / 3, 1 / 3, "arith"),
    "60/20/20 accuracy emphasis": (0.6, 0.2, 0.2, "arith"),
    "20/60/20 speed emphasis": (0.2, 0.6, 0.2, "arith"),
    "20/20/60 cost emphasis": (0.2, 0.2, 0.6, "arith"),
    "capability only": (1.0, 0.0, 0.0, "arith"),
    "33/33/33 geometric": (1 / 3, 1 / 3, 1 / 3, "geo"),
}


def log_score(x, best, worst):
    """Map x onto 0..100 on a log scale: best -> 100, worst -> 0, clipped."""
    if x is None:
        return None
    if x <= 0:
        return 100.0
    v = 100 * (math.log10(worst) - math.log10(x)) / (math.log10(worst) - math.log10(best))
    return max(0.0, min(100.0, v))


def capability(tier_accuracies):
    accs = list(tier_accuracies)
    if not accs or any(a is None for a in accs):
        return None
    return 100 * sum(accs) / len(accs)


def speed(p50_s, p95_s):
    a, b = log_score(p50_s, 0.1, 10), log_score(p95_s, 0.1, 10)
    return None if None in (a, b) else (a + b) / 2


def cost(usd_per_1000):
    return log_score(usd_per_1000, COST_BEST, COST_WORST)


def main_score(cap, spd, cst, weights=SENSITIVITY[HEADLINE]):
    a, b, d = weights[:3]
    kind = weights[3] if len(weights) > 3 else "arith"
    if None in (cap, spd, cst):
        return None
    if kind == "geo":
        return (max(cap, 1e-9) ** a) * (max(spd, 1e-9) ** b) * (max(cst, 1e-9) ** d)
    return a * cap + b * spd + d * cst
