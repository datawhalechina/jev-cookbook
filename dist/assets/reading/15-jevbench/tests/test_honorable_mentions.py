"""v1.2.4: a service that runs another entrant's model is listed, but not ranked against the models.

These tests pin the rule itself, not one row: any row marked as an honorable mention must be out of the ranking,
must name the ranked system whose model it runs, and must keep every number a ranked row has. They are what stops a
reseller of another entrant's model from silently taking a rank again.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ART = json.loads((ROOT / "results/v1.2/jevbench-v1.2-results.json").read_text())
SYS = {s["key"]: s for s in ART["systems"]}
HM = ART["honorable_mentions"]
LISTINGS = {"ranked", "honorable_mention", "partial"}


def rows(listing):
    return [s for s in ART["systems"] if s["listing"] == listing]


def test_every_row_has_exactly_one_listing():
    for s in ART["systems"]:
        assert s["listing"] in LISTINGS, (s["key"], s["listing"])
        assert s["ranked"] is (s["listing"] == "ranked"), s["key"]
        assert s["partial"] is (s["listing"] == "partial"), s["key"]


def test_only_ranked_rows_carry_a_rank():
    for s in ART["systems"]:
        assert (s["rank"] is not None) is s["ranked"], (s["key"], s["rank"])
    assert [s["rank"] for s in rows("ranked")] == list(range(1, len(rows("ranked")) + 1))


def test_ranks_follow_the_score_without_the_honorable_mentions():
    ranked = rows("ranked")
    assert ranked == sorted(ranked, key=lambda s: -s["jevbench_score"])
    best_hm = max((s["jevbench_score"] for s in rows("honorable_mention")), default=0)
    # The point of the rule: an honorable mention may outscore #1 and still not be ranked.
    assert all(s["rank"] != 1 or s["ranked"] for s in ART["systems"])
    if rows("honorable_mention"):
        assert best_hm > ranked[0]["jevbench_score"], "classifier.dev outscored the #1 model; that is why the rule exists"


def test_the_rule_is_published_and_says_not_ranked():
    for text in (HM["rule"], ART["scoring"]["ranked"]):
        assert "not ranked" in text.lower(), text
    assert "another entrant" in HM["rule"]
    assert HM["heading"].lower().startswith("honorable mentions")


@pytest.mark.parametrize("key", sorted(HM["systems"]))
def test_each_honorable_mention_names_the_model_it_runs(key):
    s, d = SYS[key], HM["systems"][key]
    assert s["listing"] == "honorable_mention"
    # The model it runs must itself be a ranked system of this benchmark — otherwise the rule does not apply.
    assert SYS[d["runs_on_key"]]["ranked"], d["runs_on_key"]
    assert d["runs_on_key"] != key
    for field in ("runs_on", "short_reason", "why_not_ranked", "price_note", "tier_measured", "not_pass_through", "credit"):
        assert isinstance(d[field], str) and d[field].strip(), (key, field)
    assert d["sources"] and all(u.startswith("https://") for u in d["sources"])
    assert s["not_ranked_because"] == d["short_reason"]


def test_honorable_mentions_keep_every_published_number():
    for key in HM["systems"]:
        s = SYS[key]
        for axis in ("intelligence", "calibration", "speed", "cost"):
            assert isinstance(s["axes"][axis], float), (key, axis)
        assert s["jevbench_score"] > 0 and s["cost"]["usd_per_1000"] > 0
        assert set(s["tiers"]) == {"easy", "standard", "judge", "hard"}
        assert s["presets"] and "rank_under" not in s, key


def test_classifier_dev_is_the_honorable_mention_and_jev_leads():
    assert [s["key"] for s in rows("honorable_mention")] == ["classifier-dev-fast"]
    assert rows("ranked")[0]["key"] == "jev-1.13.0"
    d = HM["systems"]["classifier-dev-fast"]
    assert d["runs_on_key"] == "jev-1.13.0"
    # The price caveat Florian asked to keep: the flat rate is only $0.0033 at full use.
    assert "$0.033 per 1,000" in d["price_note"] and "200,000" in d["price_note"]
    # The smart tier is escalation on low confidence, and we must not claim to have measured it.
    assert "0.7 confidence" in d["why_not_ranked"] and "not best-of-N" in d["why_not_ranked"]
    assert "never run" in d["tier_measured"]
