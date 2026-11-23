"""One-page explorer: everything the page needs is computed up front."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import explorer  # noqa: E402

MAN = {"sex": "male", "age": "56", "bmi": "31", "sbp": "150", "diabetes": "1", "current_smoker": "1"}


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
    assert any(b["type"] == "compare" for b in heart["statin"]["detail"])
    bp = next(b for b in heart["bp"]["detail"] if b["type"] == "bp")
    assert bp["current"] == 150 and bp["known"] and bp["outcomes"][0]["per5"] < 1
    assert any(b["type"] == "compare" for b in options(data, "colorectal")["colonoscopy"]["detail"])


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
    assert options(data, "prostate")["psa"]["detail"][0] == {"type": "stat", "big": "about 7", "label": "out of 100 people like you"}
    outs = [b["outcome"] for b in options(data, "heart")["statin"]["detail"] if b["type"] == "compare"]
    assert outs == ["have a heart attack or stroke", "die of heart disease or stroke"]


def test_render_fills_template_and_escapes_script_end():
    html = explorer.render(MAN, set(), {}, {"organ": "heart", "branch": "medications", "option": "statin"})
    assert "{{" not in html and 'data-organ="heart"' in html
    blob = re.search(r"const DATA = (.*);\n", html).group(1)
    assert "</" not in blob
    assert json.loads(blob.replace("<\\/", "</"))["start"]["option"] == "statin"
