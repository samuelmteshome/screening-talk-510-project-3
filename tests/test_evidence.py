"""Checks on the evidence files and the PREVENT equations shown in the app."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

import prevent  # noqa: E402

EVIDENCE = REPO / "evidence"
TRIAL_FILES = sorted(p for p in EVIDENCE.glob("*.json") if p.name != "heart_actions.json")


@pytest.mark.parametrize("path", TRIAL_FILES, ids=lambda p: p.name)
def test_trial_file_has_source_numbers_and_verification(path):
    ev = json.loads(path.read_text())
    assert ev["source"] and ev["url"].startswith("https://")
    assert ev["denominator"] == 1000
    for key, item in ev["numbers"].items():
        assert item["ref"], f"{key} needs a ref"
        assert item["value"] is None or isinstance(item["value"], (int, float)), key
    assert ev["verified_by"] and ev["verified_on"] and ev["verified_against"]


def test_heart_actions_are_consistent():
    actions = json.loads((EVIDENCE / "heart_actions.json").read_text())["actions"]
    assert set(actions) == {"statin", "bp", "aspirin", "checkups"}
    for name, action in actions.items():
        assert action["verified_by"] and action["verified_against"], name
        for effect, e in action["effects"].items():
            low, high = e["ci"]
            assert low <= e["rr"] <= high, f"{name}.{effect}"
            if e.get("significant") is False:
                assert low <= 1 <= high, f"{name}.{effect} is marked not significant but its CI excludes 1"


def test_prevent_reproduces_the_preventr_example():
    """Example from the preventr R package README (base model, 10 years)."""
    args = dict(sex="female", age=50, total_chol=200, hdl=45, sbp=160, diabetes=True,
                smoker=False, bp_meds=True, statin=False, egfr=90)
    assert round(prevent.risk(**args, outcome="cvd"), 3) == 0.147
    assert round(prevent.risk(**args, outcome="ascvd"), 3) == 0.092
