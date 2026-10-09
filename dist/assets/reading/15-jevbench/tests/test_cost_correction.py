"""v1.2.3 cost correction: every price is tariff x tokens with each of the 534 decisions counted once.

These tests are what stops the two mistakes v1.2.3 fixed from coming back: a decision counted twice in the
price average, and a token count measured on one part of the suite being applied to all of it.
"""
import json
import math
from pathlib import Path

import pytest

from jevbench.composite_v12 import cost, jevbench_score

ROOT = Path(__file__).resolve().parents[1]
FIX = json.loads((ROOT / "results/v1.2/cost-correction-v1.2.3.json").read_text())
ART = json.loads((ROOT / "results/v1.2/jevbench-v1.2-results.json").read_text())
SYS = {s["key"]: s for s in ART["systems"]}
N11, NHARD = FIX["n_v11_decisions"], FIX["n_hard_decisions"]


def test_every_decision_counted_once():
    """314 v1.1 decisions + 220 hard. A complete run prices all 314; a partial run prices the ones it ran."""
    assert N11 == 314 and NHARD == 220 and N11 + NHARD == 534
    for key, f in FIX["systems"].items():
        partial = SYS[key]["partial"]
        assert f["n_decisions"] == N11 or (partial and f["n_decisions"] < N11), (key, f["n_decisions"])
        if "n_priced_decisions" in f:
            assert f["n_priced_decisions"] == f["n_decisions"], (key, f["n_priced_decisions"])


def test_v11_price_is_tariff_times_tokens():
    """The recomputed v1.1-tier price must equal the tariff times the tokens it says it used."""
    for key, f in FIX["systems"].items():
        if "price_in_per_m" not in f:
            continue  # classifier.dev: a flat plan price per decision, no token dependency
        if f["kind"] in ("measured", "announced"):
            continue  # priced from the provider's own per-decision charge, checked below
        want = 1000 * (f["mean_input_tokens"] * f["price_in_per_m"] + f["output_tokens_charged"] * f["price_out_per_m"]) / 1e6
        assert f["usd_per_1000_v11_tiers"] == pytest.approx(want, rel=1e-12), key


def test_metered_rows_match_their_measured_tokens():
    """A metered row's price must be reproducible from its own mean token counts and its tariff."""
    for key, f in FIX["systems"].items():
        if f["kind"] not in ("measured", "announced"):
            continue
        want = 1000 * (f["mean_input_tokens"] * f["price_in_per_m"] + f["mean_output_tokens"] * f["price_out_per_m"]) / 1e6
        assert f["usd_per_1000_v11_tiers"] == pytest.approx(want, rel=1e-9), key


def test_pooled_price_is_the_weighted_mean_of_the_two_halves():
    for key, f in FIX["systems"].items():
        if f["usd_per_1000_hard"] is None:
            assert f["usd_per_1000"] == pytest.approx(f["usd_per_1000_v11_tiers"]), key
            continue
        want = (f["usd_per_1000_v11_tiers"] * N11 + f["usd_per_1000_hard"] * NHARD) / (N11 + NHARD)
        assert f["usd_per_1000"] == pytest.approx(want, rel=1e-12), key


def test_published_artifact_uses_the_corrected_prices():
    assert ART["revision"] >= "v1.2.3"
    for key, f in FIX["systems"].items():
        if key in ART.get("superseded_rows", {}):  # v1.2.8: a complete re-run replaced this row; it is priced from its own run
            continue
        c = SYS[key]["cost"]
        assert c["usd_per_1000"] == pytest.approx(f["usd_per_1000"], rel=1e-12), key
        assert c["usd_per_1000_v11_tiers"] == pytest.approx(f["usd_per_1000_v11_tiers"], rel=1e-12), key
        assert SYS[key]["axes"]["cost"] == pytest.approx(cost(f["usd_per_1000"]), rel=1e-12), key


def test_jev_price_is_the_public_tariff_times_its_own_tokens():
    """Jev 1.13.0: $0.042 per MILLION input tokens, output free (https://docs.typesafe.ai/models, read 20 Sep 2026)."""
    f = FIX["systems"]["jev-1.13.0"]
    assert f["price_in_per_m"] == 0.042 and f["price_out_per_m"] == 0.0
    hard = SYS["jev-1.13.0"]["hard"]
    mean_in = (f["mean_input_tokens"] * N11 + hard["mean_input_tokens"] * NHARD) / (N11 + NHARD)
    assert mean_in == pytest.approx(ART["cost_unit"]["mean_input_tokens_per_decision_jev"], rel=1e-9)
    assert SYS["jev-1.13.0"]["cost"]["usd_per_1000"] == pytest.approx(1000 * mean_in * 0.042 / 1e6, rel=1e-9)


def test_the_unit_is_stated_as_decisions_everywhere_it_is_named():
    u = ART["cost_unit"]
    assert u["unit"] == "$ per 1,000 decisions" and u["not_unit"] == "$ per 1,000 tokens"
    forbidden = {"text", "prompt", "question", "questions", "state", "rubric", "instructions", "label", "labels", "gold",
                 "expected", "prediction", "predictions", "predicted", "item", "items", "raw", "response", "responses",
                 "reply", "replies", "answer", "answers", "completion", "messages", "content", "records"}
    for block in (u, ART["cost_correction"], ART["cost_correction_table"]):
        assert not (set(block) & forbidden), set(block) & forbidden  # the page rejects any of these anywhere
    for text in (u["one_liner"], u["worked_example"], u["short_note"], ART["scoring"]["cost"]):
        assert "decision" in text.lower()
    assert "not per 1,000 tokens" in ART["scoring"]["cost"] or "not per 1,000 tokens" in u["one_liner"]
    assert "per MILLION input tokens" in u["worked_example"]  # the tariff's unit, spelled out


def test_the_correction_is_small_and_changed_no_rank():
    """Every row moved cheaper except DeepSeek, whose unparseable-but-billed requests are now priced."""
    ranked = [s for s in ART["systems"] if s["ranked"]]
    assert [s["rank"] for s in ranked] == sorted(s["rank"] for s in ranked)
    for a, b in zip(ranked, ranked[1:]):
        assert a["jevbench_score"] >= b["jevbench_score"]
    for key, f in FIX["systems"].items():
        assert abs(f["delta_pct"]) < 15, key
        if key != "deepseek-flash":
            assert f["usd_per_1000"] <= f["usd_per_1000_old"] + 1e-12, key


def test_no_price_is_missing_or_zero():
    for key, s in SYS.items():
        assert s["cost"]["usd_per_1000"] and s["cost"]["usd_per_1000"] > 0, key
        assert s["axes"]["cost"] == pytest.approx(max(0.0, min(100.0, 100 - 30 * math.log10(s["cost"]["usd_per_1000"] / 0.001))))
