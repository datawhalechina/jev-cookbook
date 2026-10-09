"""JevBench v1.2 final: the JevBench Score (jevbench/composite_v12.py) applied to the frozen v1.2 measurements.

    python3 scripts/v1.2/finalize.py

Input : results/v1.2/wip/jevbench-v1.2-wip-results.json  (the v1.2-wip artifact: every measurement, tag v1.2-wip)
        results/v1.2/wip/jevbench-v1.2-wip-per-task.json
Output: results/v1.2/jevbench-v1.2-results.json, results/v1.2/jevbench-v1.2-per-task.json

v1.2.1 (19 Sep 2026): rows measured after the v1.2 freeze on the same frozen items and code are added from
results/v1.2/additions/<key>.json (+ <key>-per-task.json); nothing else changes. Additions: djev (v1.2.1); Laya, jeff, GLiNER2, openJev Verdict, classifier.dev (v1.2.2); the four kev checkpoints (v1.2.5); openJev Verdict 1.4 and identified SimpleJev demo models (v1.2.6).

v1.2.3 (20 Sep 2026): the cost of each row is recomputed with every decision counted exactly once, from
results/v1.2/cost-correction-v1.2.3.json. No tariff, measurement, item or answer changed.

v1.2.4 (20 Sep 2026): a service that runs another entrant's model is listed, but not ranked against the models
(HONORABLE below). classifier.dev (fast tier), which runs Jev, leaves the ranking and becomes an honorable mention.
No measurement, no axis and no score changed; only its rank is gone and every other row moves up one place.

No measurement changes here. What changes: the score (4 axes, geometric mean), one open-alternative-jev row instead of two,
and the Needle 3 options-as-tools price (it had none; now priced on Needle 3's per-token basis).
"""
import copy
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from jevbench import composite_v12 as C  # noqa: E402

V12 = ROOT / "results/v1.2"
WIP = json.loads((V12 / "wip/jevbench-v1.2-wip-results.json").read_text())
WIP_TASKS = json.loads((V12 / "wip/jevbench-v1.2-wip-per-task.json").read_text())
ADDITIONS = {p.stem: json.loads(p.read_text()) for p in sorted((V12 / "additions").glob("*.json")) if not p.stem.endswith("-per-task")}
COST_FIX = json.loads((V12 / "cost-correction-v1.2.3.json").read_text())
COST_FIX_SUFFIX = (" [corrected in v1.2.3: the price now averages each of the 314 v1.1 decisions once; "
                   "see results/v1.2/cost-correction-v1.2.3.json]")


def cost_unit_example():
    """The worked example that makes the unit unmistakable, built from Jev's own numbers, never hand-written."""
    fix = COST_FIX["systems"]["jev-1.13.0"]
    n11, nh = COST_FIX["n_v11_decisions"], COST_FIX["n_hard_decisions"]
    hard_in = next(s for s in WIP["systems"] if s["key"] == "jev-1.13.0")["hard"]["mean_input_tokens"]
    mean_in = (fix["mean_input_tokens"] * n11 + hard_in * nh) / (n11 + nh)
    p_in, usd = fix["price_in_per_m"], fix["usd_per_1000"]
    long = (f"One decision is a whole question, not a token. Jev 1.13.0 reads {mean_in:.0f} input tokens per decision on average "
            f"over the {n11 + nh} v1.2 decisions. At its public tariff of ${p_in:g} per MILLION input tokens "
            f"(output tokens are free, https://docs.typesafe.ai/models), 1,000 decisions therefore cost "
            f"{mean_in:.0f} x 1,000 x ${p_in:g} / 1,000,000 = ${usd:.4f}. "
            f"That is what the Cost column shows: ${usd:.4f} per 1,000 decisions, not per 1,000 tokens.")
    short = (f"One decision ≈ {mean_in:.0f} input tokens on average; at Jev's ${p_in:g} per million input tokens "
             f"that is ${usd:.4f} per 1,000 decisions.")
    return {"long": long, "short": short, "mean_input_tokens_per_decision": mean_in}


COST_UNIT_EXAMPLE = cost_unit_example()
# Which revision added which row. A row's revision is fixed; the artifact's revision is the newest one present.
ADDED_IN = {"djev": "v1.2.1", "laya": "v1.2.2", "jeff": "v1.2.2", "gliner2": "v1.2.2", "openjev-verdict": "v1.2.2",
            "classifier-dev-fast": "v1.2.2", "programasweights": "v1.2.8",
            "jqv": "v1.2.8", "gliner2.5-small": "v1.2.7", "gliner2.5-multi": "v1.2.7", "opendecision": "v1.2.8",
            "kev-0.5b": "v1.2.5", "kev-0.6b": "v1.2.5", "kev-4b": "v1.2.5", "kev-8b": "v1.2.5",
            "openjev-verdict-1.4": "v1.2.6", "simplejev-qwen3.8-27b": "v1.2.6", "simplejev-qwen3.6-35b-a3b": "v1.2.6",
            "decider-35b-a3b": "v1.2.8", "reflex-27b": "v1.2.8", "decision-machine-1": "v1.2.8", "decider-2b": "v1.2.8",
            "reflex-4b": "v1.2.8", "gliner2-large": "v1.2.8", "jev-local": "v1.2.8", "nimble-9b": "v1.2.8", "litjev": "v1.2.8"}
assert set(ADDITIONS) <= set(ADDED_IN), set(ADDITIONS) - set(ADDED_IN)
# A complete re-run that replaces an earlier row (same frozen items, same scorer); the old score stays in the artifact.
SUPERSEDES = {"nimble-9b": "Re-run in v1.2.8 after Bespoke Labs raised the serving prompt limit from 2,048 to 8,192 tokens "
                           "(bespokelabsai/nimble PR #4); the v1.1.3 run had failed long items on that limit."}
COST_FIX_REVISION = "v1.2.3"
HONORABLE_REVISION = "v1.2.4"
_rk = lambda r: [int(x) for x in r[1:].split(".")]
REVISION = max([ADDED_IN[k] for k in ADDITIONS] + [COST_FIX_REVISION, HONORABLE_REVISION], default="v1.2", key=_rk)
REVISION_LOG = [e for e in [
    {"revision": "v1.2.8", "date": "2026-09-21", "note":
     "Added requested systems on the unchanged frozen 534-decision set, each through its author's own server and the "
     "existing TypeSafe adapter, one request at a time: decider-35b-a3b and reflex-27b (issues #4, #5), decider-2b (#2), "
     "reflex 4B (#3), OpenDecision, jev-local and LitJev on our RunPod GPUs; GLiNER2 large on our CPU; and "
     "decision-machine-1 (#8), a closed decision model behind milliseconds.ai's production API, shown in its own class. "
     "jqv (#6, #9) was re-run in full on our own GPU from its now-public serving code; that complete run replaces the "
     "v1.2.7 partial row. Bespoke Nimble 9B was re-run at Bespoke Labs' request after they raised its serving prompt "
     "limit from 2,048 to 8,192 tokens; the complete re-run replaces the v1.1.3 row (its old score is kept under "
     "superseded_rows). "
     "Mappings, endpoint conditions and cost bases were pushed before the runs (docs/v1.2-additions-run4.md, "
     "docs/v1.2-additions-run4b.md). No earlier measurement changed."},
    {"revision": "v1.2.7", "date": "2026-09-20", "note":
     "Added three systems: jqv (a stock Qwen3-32B read as a decision model, submitted with a public endpoint) and the "
     "GLiNER2.5 small and multi checkpoints. The GLiNER2.5 rows ran the full frozen 534-decision set on our CPU with "
     "the same mapping as the GLiNER2 row. jqv is a partial row: its endpoint is the submitter's own machine, and "
     "this revision stopped sending held-out items to an endpoint a submitter operates. The easy and standard/judge "
     "tiers had already been sent in full when that was decided; the 109 held-out hard items never were, so the row "
     "covers 425 of 534 decisions and carries no rank. Mappings, endpoint conditions and cost bases were "
     "committed before any row was aggregated and before the published GLiNER2.5 runs started "
     "(docs/v1.2-additions-run3.md); jqv's run had begun about ten minutes earlier, but it needs no mapping and is "
     "priced at its base model's public tariff. No earlier row changed."},
    {"revision": "v1.2.6", "date": "2026-09-20", "note": "Added openJev Verdict 1.4 and the identified SimpleJev public-demo configurations on the unchanged frozen 534-decision set. No earlier row changed."},
    {"revision": "v1.2.5", "date": "2026-09-20", "note": "Added kev 0.5B and the 0.6B, 4B and 8B research previews. Each ran the full frozen v1.2 set (534 decisions including held-out items) through kev's native TypeSafe-compatible endpoint on an RTX 3090. No other row changed."},
    {"revision": "v1.2.4", "date": "2026-09-20", "note":
     "classifier.dev (fast tier) leaves the ranking and becomes an honorable mention. It is not its own model: its own "
     "pages say \"The fast tier is Jev, TypeSafe's decision model\" (https://classifier.dev/benchmark), so ranking it "
     "against Jev ranks Jev's model against Jev's model at a different price. General rule from this revision on: a "
     "service that runs another entrant's model is listed with all of its scores and axes, but is not ranked against "
     "the models. Its numbers, axes, cost basis, radars and per-task outcomes are unchanged; only its rank is gone. "
     "Every other row moves up one place; no score changed."},
    {"revision": "v1.2.3", "date": "2026-09-20", "note":
     "Cost correction. Every row's $ per 1,000 decisions is recomputed with each of the 534 decisions counted exactly "
     "once and priced exactly once. Three arithmetic mistakes were fixed: the 242-decision standard+judge run was "
     "averaged twice in the v1.1-tier price (556 rows instead of 314); rows priced from the gemini-3.1-flash-lite token "
     "counts used that run's standard+judge-only average (452 input tokens per decision) for all 314 v1.1 decisions "
     "instead of its average over all 314 (383); and requests whose answer came back unparseable were left unpriced "
     "although they were billed (9 DeepSeek V4.1 Flash decisions). The first two made the affected rows look 1.5-11 % "
     "more expensive than they are; the third made DeepSeek look 2.6 % cheaper. No tariff, no measurement, no item and "
     "no answer changed, and no rank changed. Details: results/v1.2/cost-correction-v1.2.3.json."},
    {"revision": "v1.2.2", "date": "2026-09-19", "note": "Added five systems requested by readers: Laya, jeff, GLiNER2, openJev Verdict and "
     "classifier.dev (fast tier). Full v1.2 set each (534 decisions incl. held-out), scored with the unchanged v1.2 rules. Local systems ran "
     "on our CPU (4 threads) with the usual self-hosted latency adjustment; classifier.dev is a production API. Mappings were fixed before "
     "the runs (docs/v1.2-additions.md). No other row changed."},
    {"revision": "v1.2.1", "date": "2026-09-19", "note": "Added djev (Maisa, diffusion-gemma): full v1.2 set (534 decisions incl. held-out) "
     "through its production API, scored with the unchanged v1.2 rules. Cost at djev's announced price ($0.035/M input tokens, output free), "
     "which is not yet charged (free preview). No other row changed."},
    {"revision": "v1.2", "date": "2026-09-19", "note": "Final JevBench Score: 4 axes, geometric mean."},
] if e["revision"] in {"v1.2", COST_FIX_REVISION, HONORABLE_REVISION} or e["revision"] in {ADDED_IN[k] for k in ADDITIONS}]
ADDED_NAMES = {r: [ADDITIONS[k]["display"] for k in ADDITIONS if ADDED_IN[k] == r] for r in sorted({ADDED_IN[k] for k in ADDITIONS})}

# open-alternative-jev: the ranked row is the run with the author's own yes/no option order ("A. yes, B. no", as his
# yes_no() helper builds it). Our first adapter reversed it; that run is kept as raw files and one footnote, not ranked.
OAJ_RANKED, OAJ_REVERSED = "open-alternative-jev-yesfirst", "open-alternative-jev"
OAJ_KEY, OAJ_NAME = "open-alternative-jev", "open-alternative-jev (Qwen3.5-4B, IkerMoel)"
# 21 % / 72 %: the 68 yes/no answer-judging items (family "adequacy", imported judge set) of the v1.1 judge run — 20.6 % vs 72.1 %,
# recomputed from the GPU round's runs/open-alternative-jev{,-yesfirst}--v1/results.jsonl on 19 Sep 2026.
OAJ_FOOTNOTE = ("With the options in reverse order (A. no, B. yes) the same model scored 21 % instead of 72 % on yes/no "
                "answer-judging items — small models are very sensitive to option order.")

# v1.2.4 (Florian, 20 Sep 2026): a service that runs another entrant's model is listed, but not ranked against the
# models. classifier.dev is the only such row today; it was #1 in v1.2.2 and v1.2.3. Everything in HONORABLE below is
# either measured by us or quoted from the service's own pages (read 2026-09-20, saved with the job's evidence).
HONORABLE_RULE = (
    "A service that runs another entrant's model is listed with all of its scores and axes, but is not ranked against "
    "the models. Ranking it would rank the same model twice, once at the model's own price and once at the service's. "
    "The row keeps every number, axis, cost basis and per-task outcome; it carries no rank number.")
HONORABLE_HEADING = "Honorable mentions — services built on another entrant's model"
HONORABLE = {
    "classifier-dev-fast": {
        "runs_on_key": "jev-1.13.0",
        "runs_on": "Jev (TypeSafe)",
        "short_reason": "runs on Jev (TypeSafe) — listed, not ranked",
        "why_not_ranked": (
            "classifier.dev is not its own model. Its own pages say so: \"The fast tier is Jev, TypeSafe's decision "
            "model\" (https://classifier.dev/benchmark, read 2026-09-20), and the API answers with "
            "\"model\": \"jev-1.13.0\" — the same model version this benchmark measures directly as Jev 1.13.0. What "
            "it adds is a price and, on its smart tier, an orchestration layer: \"The smart tier is Jev plus a "
            "reasoning model re-asking only the answers Jev put under 0.7 confidence\" — escalation on low confidence "
            "(a model cascade), not best-of-N, not self-consistency and not a committee. Its published escalation "
            "model is gemini-3.8-flash. Ranking it against Jev would rank Jev's model against Jev's model, so from "
            "v1.2.4 it is an honorable mention instead of #1."),
        "tier_measured": (
            "Only the fast tier was measured. The smart tier's escalation was never run, so nothing here scores it."),
        "price_note": (
            "$0.0033 per 1,000 decisions is an estimate from the published flat-rate plan at full use: classifier.dev "
            "Pro is $20/month for 200,000 fast classifications a day (https://classifier.dev/pricing, read "
            "2026-09-20), and one classification is one decision. Lower use costs more per decision — at a tenth of "
            "that allowance it is $0.033 per 1,000 — and the free tier (20,000 fast classifications a day), which is "
            "what our run used, costs nothing. Their pages do not say how the flat rate is funded, so we do not know "
            "their cost basis; the only figure they publish is what the model costs a caller: \"The model behind the "
            "fast tier costs about $0.005 per thousand classifications and needs a TypeSafe key\" "
            "(https://classifier.dev/pricing) — for their short single-sentence inputs, not for JevBench's whole "
            "questions."),
        "not_pass_through": (
            "On our set the fast tier scored 97.3 % on the judge tier against Jev's "
            "94.5 %, and 70.5 % against 74.1 % on the hard tier. classifier.dev's own explanation for differences of "
            "this kind is batching (\"The fast tier is Jev, packed a thousand to a request\"); on their own two test "
            "sets they measured the same difference as noise."),
        "credit": (
            "A legitimate, well-documented product: free without an account, open source "
            "(https://github.com/mrmps/classifier-dev), by Michael Ryaboy (@michael_chomsky)."),
        "sources": ["https://classifier.dev", "https://classifier.dev/benchmark", "https://classifier.dev/pricing",
                    "https://classifier.dev/about"],
        "sources_read": "2026-09-20",
    },
}


def endpoint_kind(cond):
    c = cond.lower()
    if c.startswith("production api") or c.startswith("chutes shared"):
        return "api"
    if "runpod gpu" in c:
        return "gpu"
    if "demo endpoint" in c or "author-hosted endpoint" in c:
        return "demo"
    if "our cpu" in c:
        return "cpu"
    raise ValueError(f"unknown endpoint condition: {cond}")


def needle_tools_price(row, needle):
    """Needle 3 options-as-tools never ran the hard tier: price its 314 v1.1 decisions on Needle 3's per-token basis."""
    c = row["cost"]
    usd = c["usd_per_1000_v11_tiers"]
    assert usd and "llama-3.2-1b-instruct list price $0.027/M in, $0.201/M out" in c["basis_v11"] and "llama-3.2-1b" in needle["cost"]["basis_v11"]
    c["usd_per_1000"] = usd
    c["basis_final"] = ("ESTIMATE: same per-token price as Needle 3 (openrouter meta-llama/llama-3.2-1b-instruct $0.027/M in, $0.201/M out) "
                        "x 452 input and 20 output tokens per decision, over the 314 easy/standard/judge decisions it ran (no hard-tier run). "
                        "The v1.2 score lab had no price for this row and scored it 100; fixed.")
    return row


def apply_cost_correction_one(key, row):
    """The v1.2.3 price correction for one frozen row (used to record a superseded row's old score)."""
    apply_cost_correction({key: row}, only={key})
    return row


def apply_cost_correction(src, skip=(), only=None):
    """v1.2.3: replace every row's v1.1-tier price with the one that counts each of the 314 decisions once.

    The corrected figures and their derivation (tariff, mean input tokens, output tokens charged, n) are in
    results/v1.2/cost-correction-v1.2.3.json, which is data, not code: the raw runs it was derived from include
    held-out items and stay out of the repo. Nothing but the price changes.
    """
    n11, nh = COST_FIX["n_v11_decisions"], COST_FIX["n_hard_decisions"]
    # The frozen correction covers rows present in v1.2.3. Later additions are
    # already aggregated with each decision counted exactly once.
    if only is None:
        assert set(COST_FIX["systems"]) <= set(src), set(COST_FIX["systems"]) - set(src)
    for key, fix in COST_FIX["systems"].items():
        if key in skip or (only is not None and key not in only):
            continue
        c = src[key]["cost"]
        assert abs(c["usd_per_1000_v11_tiers"] - fix["usd_per_1000_v11_tiers_old"]) < 1e-12, key
        assert abs(c["usd_per_1000"] - fix["usd_per_1000_old"]) < 1e-12, key
        c["usd_per_1000_v11_tiers"] = fix["usd_per_1000_v11_tiers"]
        c["usd_per_1000"] = (fix["usd_per_1000_v11_tiers"] * n11 + c["usd_per_1000_hard"] * nh) / (n11 + nh) \
            if c["usd_per_1000_hard"] is not None else fix["usd_per_1000_v11_tiers"]
        assert abs(c["usd_per_1000"] - fix["usd_per_1000"]) < 1e-12, (key, c["usd_per_1000"], fix["usd_per_1000"])
        if fix["unchanged"]:
            continue
        # Keep the basis readable: correct the token figure it quotes, and say the price was corrected.
        for field in ("basis_v11", "basis_final"):
            b = c.get(field)
            if not b:
                continue
            if "mean_input_tokens" in fix:
                b = re.sub(r"x \d+ input and (\d+) output tokens per decision",
                           lambda m: f"x {fix['mean_input_tokens']:.0f} input and {m.group(1)} output tokens per decision", b, count=1)
            c[field] = b + COST_FIX_SUFFIX
    return src


def build_row(s):
    kind = endpoint_kind(s["endpoint_condition"])
    sb = s["speed_block"]
    p50, p95 = sb["p50_s"], sb["p95_s"]
    axes = {
        "intelligence": C.intelligence(s["tiers"]),
        "calibration": s["calibration"]["score"],
        "speed": C.speed(p50, p95, kind),
        "cost": C.cost(s["cost"]["usd_per_1000"]),
    }
    row = {k: s.get(k) for k in ("key", "display", "class", "open", "author", "repo", "licence", "underlying", "has_distribution", "probability_source")}
    # Three ways to be listed, exactly one per row: ranked, partial (a tier under 95 % coverage), honorable mention
    # (a service running another entrant's model — v1.2.4). Only a ranked row carries a rank number.
    listing = "partial" if s["partial"] else ("honorable_mention" if s["key"] in HONORABLE else "ranked")
    row.update({
        "endpoint_condition": s["endpoint_condition"], "endpoint_kind": kind,
        "partial": s["partial"], "ranked": listing == "ranked", "listing": listing,
        "not_ranked_because": HONORABLE[s["key"]]["short_reason"] if listing == "honorable_mention" else None,
        "tiers": s["tiers"], "axes": axes, "jevbench_score": C.jevbench_score(axes),
        "speed": {
            "p50_s_raw": p50, "p95_s_raw": p95,
            "p50_s_adjusted": C.adjusted_latency(p50, kind), "p95_s_adjusted": C.adjusted_latency(p95, kind),
            "adjustment": "none (production API)" if kind == "api" else
                          f"x{C.LOAD_FACTOR:g}" + (f" + {C.OWN_SERVER_ADD_S} s" if kind in C.OWN_SERVERS else "") + " (assumption, not measured)",
            "run": sb.get("run"), "hardware": sb.get("hardware"), "measured_where": sb.get("measured_where"),
            "hard_tier_p50_s": (s.get("hard") or {}).get("latency_p50_s"), "hard_tier_p95_s": (s.get("hard") or {}).get("latency_p95_s"),
        },
        "cost": {"kind": s["cost"]["kind"], "usd_per_1000": s["cost"]["usd_per_1000"],
                 "basis": s["cost"].get("basis_final") or " | ".join(b for b in (s["cost"]["basis_v11"], s["cost"]["basis_hard"]) if b),
                 "usd_per_1000_v11_tiers": s["cost"]["usd_per_1000_v11_tiers"], "usd_per_1000_hard": s["cost"]["usd_per_1000_hard"],
                 "self_host_sensitivity": s["cost"]["self_host_sensitivity"]},
        "calibration": {**s["calibration"], "note": None if s["calibration"]["score"] is not None else
                        "returns a label, not a probability distribution: no calibration score (counts as 0 in the JevBench Score)"},
        "hard": s.get("hard"),
    })
    row["presets"] = {name: C.preset_score(axes, w) for name, w in C.PRESETS.items()}
    return row


def main():
    src = {s["key"]: copy.deepcopy(s) for s in WIP["systems"]}
    rev = src.pop(OAJ_REVERSED)
    own = src.pop(OAJ_RANKED)
    own.update(key=OAJ_KEY, display=OAJ_NAME, run_key=OAJ_RANKED)
    src[OAJ_KEY] = own
    needle_tools_price(src["needle-3-tools"], src["needle-3"])
    superseded = {}
    for k, row in ADDITIONS.items():
        if k in src:  # v1.2.8: a complete re-run on the same frozen items replaces the earlier row (named in SUPERSEDES)
            assert k in SUPERSEDES, k
            old = build_row(apply_cost_correction_one(k, copy.deepcopy(src[k])))
            superseded[k] = {"reason": SUPERSEDES[k], "old_score": old["jevbench_score"], "old_tiers": old["tiers"],
                             "old_endpoint_condition": old["endpoint_condition"]}
        src[k] = copy.deepcopy(row)
    apply_cost_correction(src, skip=set(superseded))

    rows = [build_row(s) for s in src.values()]
    rows[[r["key"] for r in rows].index(OAJ_KEY)]["run_key"] = OAJ_RANKED
    by = lambda kind: sorted((r for r in rows if r["listing"] == kind), key=lambda r: -r["jevbench_score"])
    ranked, honorable, partial = by("ranked"), by("honorable_mention"), by("partial")
    assert set(HONORABLE) == {r["key"] for r in honorable}, set(HONORABLE) ^ {r["key"] for r in honorable}
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    for r in honorable + partial:
        r["rank"] = None
    for name in C.PRESETS:
        for i, r in enumerate(sorted(ranked, key=lambda r: -r["presets"][name]), 1):
            r.setdefault("rank_under", {})[name] = i

    footnote = OAJ_FOOTNOTE
    art = {
        "benchmark": "JevBench", "revision": REVISION, "revision_log": REVISION_LOG, "protocol": "jevbench::v1.2", "status": "final",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "measured_in": "v1.2-wip (tag v1.2-wip); no measurement changed for v1.2 final" + (
            "; later additions measured on the same frozen items: " + "; ".join(f"{r}: " + ", ".join(n) for r, n in ADDED_NAMES.items()) if ADDITIONS else ""),
        "revision_note": "v1.2 final: 4 axes (Intelligence, Calibration, Speed, Cost), 25 % each, geometric mean; hard tier 30 % of Intelligence; "
                         "latency of non-production endpoints adjusted (assumption); one open-alternative-jev row (author's option order); "
                         "Needle 3 options-as-tools priced." + "".join(f" {r}: added " + ", ".join(n) + "." for r, n in ADDED_NAMES.items()),
        "score_name": "JevBench Score",
        "score_one_liner": "Intelligence, Calibration, Speed, Cost — 25 % each, geometric mean: a weak axis pulls the score down hard.",
        "tiers": WIP["tiers"], "tier_weights": C.TIER_WEIGHTS, "axis_weights": C.WEIGHTS,
        "presets": {k: dict(zip(C.AXES, v)) for k, v in C.PRESETS.items()}, "main": C.MAIN,
        "speed_note": C.SPEED_NOTE,
        "cost_unit": {
            # Key names avoid the artifact's forbidden-key list (no "label"): the page rejects anything that could
            # carry item-level content, and this block is published straight into the browser bundle.
            "unit": "$ per 1,000 decisions",
            "not_unit": "$ per 1,000 tokens",
            "one_liner": "Dollars per 1,000 decisions, not per 1,000 tokens: one decision is a whole question — state, rubric and options.",
            "worked_example": COST_UNIT_EXAMPLE["long"],
            "short_note": COST_UNIT_EXAMPLE["short"],
            "mean_input_tokens_per_decision_jev": COST_UNIT_EXAMPLE["mean_input_tokens_per_decision"],
        },
        "cost_correction": {"revision": COST_FIX_REVISION, "file": "results/v1.2/cost-correction-v1.2.3.json",
                            "what_was_wrong": COST_FIX["what_was_wrong"], "rule": COST_FIX["rule"]},
        "cost_correction_table": {k: {"old": f["usd_per_1000_old"], "new": f["usd_per_1000"],
                                      "pct": f["delta_pct"], "unchanged": f["unchanged"]}
                                  for k, f in COST_FIX["systems"].items()},
        "scoring": {
            "jevbench_score": "exp(sum over the four axes of 0.25 x ln(max(axis, 1))) — the geometric mean of Intelligence, Calibration, Speed and Cost. "
                              "A weak axis pulls the score down hard; a strong axis cannot buy it back.",
            "intelligence": "100 x weighted accuracy: hard 30 %, easy 14 %, standard 28 %, judge 28 %. Accuracy = correct / all items; failed, "
                            "timed-out or unparseable answers count as wrong.",
            "hard_tier": WIP["scoring"]["hard_tier"],
            "calibration": WIP["scoring"]["calibration"].split(" Label-only")[0] + " Label-only systems have none; it counts as 0 in the JevBench Score.",
            "speed": "Mean of score(p50) and score(p95) of the serial 242-decision standard+judge run; score(s) = 100 - 20 log10(s / 0.1 s), "
                     "clipped to 0..100 (0.1 s = 100, 1 s = 80, 10 s = 60). " + C.SPEED_NOTE +
                     " Production APIs (Jev, djev, classifier.dev, OpenAI, Google, DeepSeek, Chutes) are not adjusted.",
            "cost": "US dollars per 1,000 DECISIONS — not per 1,000 tokens. One decision is one whole question: its state, its rubric "
                    "and its options, which is hundreds to thousands of input tokens. Pooled over all 534 v1.2 decisions; "
                    "score = 100 - 30 log10(usd / 0.001), clipped to 0..100 "
                    "($0.001 = 100, $0.01 = 70, $0.10 = 40, $1 = 10). Measured = public tariff x measured tokens. est. = hosted-provider list price "
                    "of the same weights or size class x tokens (for a flat-rate service, its published plan price at full use). announced = the provider's published price, not yet charged (free preview), x measured tokens.",
            "ranked": "Ranked: a system's own model, with every tier attempted for >= 95 % of its decisions. Partial runs are shown below the ranking, marked, without a rank. " + HONORABLE_RULE,
            "presets": "Other views reweight the same four axes and combine them the same way (geometric mean). They are not the JevBench Score.",
        },
        "hard_dataset": WIP.get("hard_dataset"),
        "footnotes": {OAJ_KEY: footnote, **{k: r["footnote"] for k, r in ADDITIONS.items() if r.get("footnote")}},
        "superseded_rows": superseded,
        "excluded_runs": [{
            "key": "open-alternative-jev-reversed-order", "run_key": OAJ_REVERSED, "why_not_ranked":
            "Our first adapter put the options in reverse order (A. no, B. yes); the author's yes_no() helper builds A. yes, B. no. "
            "An adapter mistake, not a model weakness, so the author-order run is the ranked row. Raw run files are kept.",
            "tiers": rev["tiers"], "footnote": footnote,
        }],
        "honorable_mentions": {"heading": HONORABLE_HEADING, "rule": HONORABLE_RULE,
                               "systems": {k: dict(v) for k, v in HONORABLE.items()}},
        "systems": ranked + honorable + partial,
    }
    (V12 / "jevbench-v1.2-results.json").write_text(json.dumps(art, indent=1, ensure_ascii=False) + "\n")

    tasks = copy.deepcopy(WIP_TASKS)
    tasks["systems"].pop(OAJ_REVERSED)
    tasks["systems"][OAJ_KEY] = tasks["systems"].pop(OAJ_RANKED)
    if isinstance(tasks["systems"][OAJ_KEY], dict) and "display" in tasks["systems"][OAJ_KEY]:
        tasks["systems"][OAJ_KEY]["display"] = OAJ_NAME
    for k in ADDITIONS:
        tasks["systems"][k] = json.loads((V12 / "additions" / f"{k}-per-task.json").read_text())
    tasks.update(revision=REVISION, status="final")
    (V12 / "jevbench-v1.2-per-task.json").write_text(json.dumps(tasks, indent=1, ensure_ascii=False) + "\n")

    for r in ranked + honorable + partial:
        a = r["axes"]
        f = lambda v: "  -  " if v is None else f"{v:5.1f}"
        print(f"{str(r['rank'] or '-'):>2} {r['key'][:28]:28} {f(r['jevbench_score'])}  I {f(a['intelligence'])} C {f(a['calibration'])} "
              f"S {f(a['speed'])} K {f(a['cost'])}  ${r['cost']['usd_per_1000']:.4f} {r['cost']['kind'][:4]} "
              f"{'' if r['ranked'] else ('PARTIAL' if r['partial'] else 'HONORABLE MENTION')}")
    print(footnote)


if __name__ == "__main__":
    main()
