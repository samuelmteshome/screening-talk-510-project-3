"""Front-end logic: which organs show, search, evidence loading, body map links."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import body_map  # noqa: E402
from catalog import TOPICS, in_range, load_evidence, number_rows, search, topics_for  # noqa: E402


def test_prostate_only_for_men():
    assert "prostate" in [t.id for t in topics_for("male")]
    assert "prostate" not in [t.id for t in topics_for("female")]
    assert {t.id for t in topics_for("female")} == {"heart", "colorectal"}


def test_search_finds_by_organ_test_and_medicine():
    assert [t.id for t in search("PSA", "male")] == ["prostate"]
    assert [t.id for t in search("statin", "female")] == ["heart"]
    assert [t.id for t in search("Colonoscopy", "male")] == ["colorectal"]
    assert search("psa", "female") == []
    assert search("  ", "male") == []


def test_age_range():
    assert in_range(TOPICS["prostate"], 56)
    assert not in_range(TOPICS["prostate"], 45)


def test_every_topic_has_evidence_in_repo():
    for t in TOPICS.values():
        evidence = load_evidence(t)
        assert evidence, t.id
        assert all("source" in e and "url" in e for e in evidence)


def test_number_rows_skips_missing_values():
    rows = number_rows({"numbers": {"a": {"value": 3}, "b": {"value": None}}})
    assert rows == [("a", 3)]


def test_body_map_links_each_organ():
    params = {"sex": "male", "age": "56", "bmi": "27.0"}
    html = body_map.render("male", topics_for("male"), params)
    for t in topics_for("male"):
        assert f"organ={t.id}" in html
    assert "age=56" in html


def test_prior_heart_attack_blocks_heart_number():
    from catalog import eligibility
    ok, why = eligibility(TOPICS["heart"], 39, {"prior_cvd"})
    assert not ok and "first heart attack" in why
    ok, why = eligibility(TOPICS["heart"], 39, set())
    assert not ok and "40 to 75" in why
    assert eligibility(TOPICS["heart"], 60, set()) == (True, "")


def test_ineligible_organ_drawn_grey():
    html = body_map.render("male", topics_for("male"), {"sex": "male"}, frozenset({"heart"}))
    assert "organ heart off" in html and "not for you" in html
