"""One-page explorer: everything the page needs is computed up front."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import explorer  # noqa: E402

MAN = {"sex": "male", "age": "56", "bmi": "31", "sbp": "150", "diabetes": "1", "current_smoker": "1"}


def flat(detail):
    """Blocks with the "See more" section opened."""
    out = []
    for b in detail:
        out += [b] + (flat(b["blocks"]) if b["type"] == "more" else [])
    return out


def options(data, organ):
    o = next(x for x in data["organs"] if x["id"] == organ)
    return {op["id"]: op for b in o["branches"] for op in b["options"]}


def test_every_option_has_numbers_for_an_eligible_person():
    data = explorer.payload(MAN, set(), {})
    assert [o["id"] for o in data["organs"]] == ["prostate", "heart", "colorectal"]
    for organ in ("prostate", "heart", "colorectal"):
        for op in options(data, organ).values():
            assert op["detail"], op["id"]
    heart = options(data, "heart")
    assert any(b["type"] == "compare" for b in flat(heart["statin"]["detail"]))
    bp = next(b for b in flat(heart["bp"]["detail"]) if b["type"] == "bp")
    assert bp["current"] == 150 and bp["known"] and bp["outcomes"][0]["per5"] < 1
    assert any(b["type"] == "compare" for b in flat(options(data, "colorectal")["colonoscopy"]["detail"]))


def test_prior_disease_gives_reason_and_evidence_not_numbers():
    data = explorer.payload(MAN, {"prior_cvd"}, {})
    heart = next(o for o in data["organs"] if o["id"] == "heart")
    assert not heart["eligible"] and "heart attack" in heart["note"] and heart["evidence"]
    assert all(not op["detail"] for op in options(data, "heart").values())


def test_women_get_no_prostate_and_search_respects_it():
    data = explorer.payload({**MAN, "sex": "female"}, set(), {})
    assert "prostate" not in [o["id"] for o in data["organs"]]
    assert all(h["organ"] != "prostate" for h in data["search"])
    assert any("atorvastatin" in h["names"] and h["option"] == "statin" for h in data["search"])


def test_api_prediction_shown_when_available():
    api = {"prostate": {"prediction": {"per_100": 7, "probability": 0.07}},
           "heart": {"prediction": {"risk_cv_death_10y": 0.03}}}
    data = explorer.payload(MAN, set(), api)
    psa = flat(options(data, "prostate")["psa"]["detail"])
    assert {"type": "stat", "big": "about 7", "label": "out of 100 people like you"} in psa
    assert any(r[1] == explorer.MODEL for b in psa if b["type"] == "sources" for r in b["rows"])
    outs = [b["outcome"] for b in flat(options(data, "heart")["statin"]["detail"]) if b["type"] == "compare"]
    assert outs == ["have a heart attack or stroke", "die of heart disease or stroke"]


def test_render_fills_template_and_escapes_script_end():
    html = explorer.render(MAN, set(), {}, {"organ": "heart", "branch": "medications", "option": "statin"})
    assert "{{" not in html and 'data-organ="heart"' in html
    blob = re.search(r"const DATA = (.*);\n", html).group(1)
    assert "</" not in blob
    assert json.loads(blob.replace("<\\/", "</"))["start"]["option"] == "statin"


def test_questionnaire_answers_round_trip_through_the_url():
    import intake
    a = {"sex": "male", "age": 61, "bmi": 25.8, "race_eth": None, "history": ["prior_cvd"], "family_crc": None,
         "smoking": "former", "diabetes": True, "on_bp_meds": False, "sbp": 145}
    p = intake.to_params(a)
    assert p == {"sex": "male", "age": "61", "bmi": "25.8", "sbp": "145", "diabetes": "1", "ever_smoked": "1",
                 "prior_cvd": "1"}
    back = intake.from_params(p, {"prior_cvd"})
    assert back["smoking"] == "former" and back["age"] == 61 and back["history"] == ["prior_cvd"]
    assert intake.bp_reading(145, {})[0].startswith("High") and intake.hdl_reading(45, {"sex": "female"})[0].startswith("Low")


def test_every_option_opens_with_a_headline_then_see_more_with_sources():
    data = explorer.payload(MAN, set(), {"heart": {"prediction": {"risk_cv_death_10y": 0.04}}})
    for organ in ("prostate", "heart", "colorectal"):
        for op in options(data, organ).values():
            d = op["detail"]
            assert d[0]["type"] == "headline" and d[-1]["type"] == "more", op["id"]
            assert any(b["type"] == "sources" and b["rows"] for b in d[-1]["blocks"]), op["id"]
    heart = options(data, "heart")
    assert re.search(r"Starting a statin would lower your chance of a heart attack or stroke by about <b>28%</b> "
                     r"\(from [\d.]+% to [\d.]+% over 10 years\) and may add <b>about 1 year</b>", heart["statin"]["detail"][0]["html"])
    assert "not been shown to add years" in heart["aspirin"]["detail"][0]["html"]


def test_lifestyle_branch_for_smokers_and_non_smokers():
    smoker = options(explorer.payload(MAN, set(), {}), "heart")
    head = smoker["quit_smoking"]["detail"][0]["html"]
    assert "Quitting smoking would lower your chance of a heart attack or stroke" in head and "<b>4 years</b>" in head  # quit at 55-64
    never = options(explorer.payload({**MAN, "current_smoker": "0"}, set(), {}), "heart")
    assert "You don&#x27;t smoke now" in never["quit_smoking"]["detail"][0]["html"]
    assert "150 to 300 minutes a week of vigorous" in str(smoker["exercise"]["detail"])
    assert "Losing 10 pounds would lower your top blood pressure number by about <b>5 points</b>" in smoker["weight_loss"]["detail"][0]["html"]


def test_stool_test_and_sigmoidoscopy_use_their_own_trials():
    colon = options(explorer.payload(MAN, set(), {}), "colorectal")
    assert list(colon) == ["colonoscopy", "fobt", "sigmoidoscopy"]
    assert "dying of colorectal cancer by about <b>32%</b>" in colon["fobt"]["detail"][0]["html"]
    sig = colon["sigmoidoscopy"]["detail"][0]["html"]
    assert "getting colorectal cancer by about <b>21%</b>" in sig and "dying of it by about <b>20%</b>" in sig
