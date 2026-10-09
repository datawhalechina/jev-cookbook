"""JevBench v1.2 final scoring: the JevBench Score (four axes, geometric mean).

Pure functions of published aggregates, so anyone can recompute every number in results/v1.2/jevbench-v1.2-results.json.

Intelligence  100 x weighted accuracy: hard 30 %, easy 14 %, standard 28 %, judge 28 % (the 70 % left after hard, split 1 : 2 : 2).
              A tier a system never ran (partial runs only) is left out and the remaining weights are renormalised.
Calibration   hard tier, distribution-returning systems: mean of 100 x (1 - ECE / 0.5) (clipped at 0) and
              100 x (1 - mean TVD to the exact gold distribution on the probability items). Unchanged from v1.2-wip.
              Label-only systems have none; in the JevBench Score their Calibration counts as 0.
Speed         mean of score(p50) and score(p95), score(s) = clamp(100 - 20 log10(s / 0.1), 0, 100): 0.1 s = 100,
              each 10x slower costs 20 points. p50/p95 are the serial 242-decision standard+judge run.
              ASSUMPTION, not a measurement: endpoints that are not a production API (our RunPod GPUs, our CPU, authors'
              demo servers) ran one request at a time with no other load, so their latency is multiplied by 2; our own
              GPU/CPU servers additionally get +0.15 s (no API gateway, authentication or billing). Production APIs
              (Jev, OpenAI, Google, DeepSeek, Chutes) are unchanged. Raw p50/p95 are published beside the adjusted ones.
Cost          clamp(100 - 30 log10(usd_per_1000 / 0.001), 0, 100): $0.001 per 1,000 decisions = 100, each 10x more
              expensive costs 30 points. A missing price is an error, never an automatic 100.
JevBench Score  exp(sum 0.25 ln(max(axis, 1))) — the geometric mean of the four axes, so a weak axis pulls it down hard.
"""
import math

TIER_WEIGHTS = {"easy": 0.14, "standard": 0.28, "judge": 0.28, "hard": 0.30}
AXES = ("intelligence", "calibration", "speed", "cost")
WEIGHTS = {"intelligence": 0.25, "calibration": 0.25, "speed": 0.25, "cost": 0.25}
SPEED_BEST_S, SPEED_PER_DECADE = 0.1, 20
COST_BEST_USD, COST_PER_DECADE = 0.001, 30
# Endpoint kinds. Only non-production endpoints are adjusted; the +0.15 s applies to servers we ran ourselves.
PRODUCTION = {"api"}
LOAD_FACTOR = 2.0
OWN_SERVER_ADD_S = 0.15
OWN_SERVERS = {"gpu", "cpu"}
SPEED_NOTE = ("Latency of self-hosted and demo endpoints is adjusted ×2 (+0.15 s on our own servers) to approximate "
              "production load — an assumption, not a measurement; raw measurements are in the table and the repo.")

# The reader-selectable views. Weights are Intelligence : Calibration : Speed : Cost, always combined geometrically.
PRESETS = {
    "JevBench Score (25:25:25:25)": (0.25, 0.25, 0.25, 0.25),
    "Balanced 33:33:33 (no calibration)": (1 / 3, 0.0, 1 / 3, 1 / 3),
    "Emphasis on Accuracy 60:20:20": (0.6, 0.0, 0.2, 0.2),
    "Emphasis on Speed 20:60:20": (0.2, 0.0, 0.6, 0.2),
    "Emphasis on Cost 20:20:60": (0.2, 0.0, 0.2, 0.6),
    "Intelligence only": (1.0, 0.0, 0.0, 0.0),
}
MAIN = "JevBench Score (25:25:25:25)"


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def intelligence(tiers):
    s = tw = 0.0
    for t, w in TIER_WEIGHTS.items():
        if tiers.get(t) is not None:
            s += w * tiers[t]
            tw += w
    return 100 * s / tw if tw else None


def adjusted_latency(seconds, endpoint_kind):
    if seconds is None:
        return None
    if endpoint_kind in PRODUCTION:
        return seconds
    return seconds * LOAD_FACTOR + (OWN_SERVER_ADD_S if endpoint_kind in OWN_SERVERS else 0.0)


def speed_point(seconds):
    return clamp(100 - SPEED_PER_DECADE * math.log10(seconds / SPEED_BEST_S))


def speed(p50_s, p95_s, endpoint_kind):
    a, b = adjusted_latency(p50_s, endpoint_kind), adjusted_latency(p95_s, endpoint_kind)
    if a is None or b is None:
        return None
    return (speed_point(a) + speed_point(b)) / 2


def cost(usd_per_1000):
    if usd_per_1000 is None or not usd_per_1000 > 0:
        raise ValueError("every system needs a positive price; a missing price is never scored as 100")
    return clamp(100 - COST_PER_DECADE * math.log10(usd_per_1000 / COST_BEST_USD))


def tvd(p, q, labels):
    return 0.5 * sum(abs(p.get(l, 0.0) - q.get(l, 0.0)) for l in labels)


def calibration(ece, mean_tvd=None):
    if ece is None:
        return None
    a = max(0.0, 100 * (1 - ece / 0.5))
    return a if mean_tvd is None else (a + 100 * (1 - mean_tvd)) / 2


def geometric(axes, weights=WEIGHTS):
    """Weighted geometric mean of the axis scores; a missing axis (label-only Calibration) counts as 0 -> floor 1."""
    tot = sum(weights[k] for k in AXES)
    return math.exp(sum(weights[k] / tot * math.log(max(axes.get(k) or 0.0, 1.0)) for k in AXES if weights[k] > 0))


def jevbench_score(axes):
    return geometric(axes, WEIGHTS)


def preset_score(axes, weights):
    return geometric(axes, dict(zip(AXES, weights)))
