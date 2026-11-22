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
    assert html.count('class="organ-link') == 3


def test_prior_heart_attack_blocks_heart_number():
    from catalog import eligibility
    ok, why = eligibility(TOPICS["heart"], 39, {"prior_cvd"})
    assert not ok and "first heart attack" in why
    ok, why = eligibility(TOPICS["heart"], 39, set())
    assert not ok and "40 to 75" in why
    assert eligibility(TOPICS["heart"], 60, set()) == (True, "")


def test_ineligible_organ_drawn_grey():
    html = body_map.render("male", topics_for("male"), {"sex": "male"}, frozenset({"heart"}))
    assert 'organ-link off" href="?sex=male&amp;organ=heart"' in html
    assert "Not covered for you" in html


def test_heart_action_math_and_wording():
    import heart_actions as ha
    line = ha.compare(0.10, 0.72, "event")
    assert (line.denom, line.without, line.with_, line.fewer) == (100, 10, 7, 3)
    assert "3 fewer" in ha.sentence(line)
    small = ha.compare(0.03, 0.91, "cv_death", certain=False)
    assert small.denom == 1000 and "no difference" in ha.sentence(small)
    assert abs(ha.bp_rr(0.91, 150, 130) - 0.91 ** 4) < 1e-9
    assert ha.bp_rr(0.91, 120, 130) == 1.0
    assert ha.pct_change(0.92) == "8% fewer" and ha.pct_change(1.44) == "44% more"


def test_every_action_has_effects_and_source():
    import heart_actions as ha
    effects = ha.load_effects()
    assert set(effects) == set(ha.ACTIONS)
    for a in effects.values():
        assert a["source"] and a["url"].startswith("https://") and a["effects"]


def test_search_routes_to_heart_action():
    import heart_actions as ha
    assert [t.id for t in search("aspirin", "female")] == ["heart"]
    assert ha.action_for_query("Blood Pressure") == "bp"
    assert ha.action_for_query("Statin") == "statin"
