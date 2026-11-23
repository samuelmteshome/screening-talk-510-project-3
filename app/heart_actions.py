"""Turn a person's baseline 10-year heart risk plus a trial's relative effect into
plain-language "without vs with" numbers.

Baseline risks come from the API (heart model); effects come from
evidence/heart_actions.json. Pure Python so it can be tested in CI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from catalog import EVIDENCE_DIR

ACTIONS = {
    "statin": "Take a daily statin (cholesterol medicine)",
    "bp": "Lower my blood pressure with medicine",
    "aspirin": "Take a daily low-dose aspirin",
    "checkups": "Get regular general health checkups",
}

OUTCOME_WORDS = {
    "event": "have a heart attack or stroke",
    "cv_death": "die of heart disease or stroke",
    "crc": "get colorectal cancer",
    "crc_death": "die of colorectal cancer",
}


def load_effects() -> dict:
    return json.loads((EVIDENCE_DIR / "heart_actions.json").read_text())["actions"]


def bp_rr(per_5: float, current_sbp: float, target_sbp: float) -> float:
    """Relative risk for lowering systolic BP from current to target (log-linear per 5 mmHg)."""
    drop = max(0.0, current_sbp - target_sbp)
    return per_5 ** (drop / 5)


@dataclass
class Line:
    outcome: str          # "event" or "cv_death"
    denom: int            # 100 or 1000
    without: int
    with_: int
    certain: bool         # False when the studies' result could be no effect

    @property
    def fewer(self) -> int:
        return self.without - self.with_


def compare(baseline: float, rr: float, outcome: str, certain: bool = True) -> Line:
    """baseline: 10-year risk as a fraction (0.08 = 8%)."""
    denom = 100 if baseline >= 0.05 else 1000
    without = round(baseline * denom)
    with_ = round(baseline * rr * denom)
    return Line(outcome, denom, without, with_, certain)


def sentence(line: Line) -> str:
    """Plain-language sentence a patient can read."""
    who = f"Out of {line.denom:,} people like you"
    words = OUTCOME_WORDS[line.outcome]
    base = f"{who}, about **{line.without}** would {words} in the next 10 years without this, and about **{line.with_}** with it."
    if not line.certain:
        return base + " The studies could not rule out **no difference**, so treat this as uncertain."
    if line.fewer > 0:
        return base + f" That is about **{line.fewer} fewer** out of {line.denom:,}."
    if line.fewer < 0:
        return base + f" That is about **{-line.fewer} more** out of {line.denom:,}."
    return base + " For people at your risk, the difference rounds to zero."


KEYWORDS = {
    "statin": ("statin", "cholesterol", "rosuvastatin"),
    "bp": ("blood pressure", "hypertension"),
    "aspirin": ("aspirin",),
    "checkups": ("checkup", "primary care"),
}


def action_for_query(query: str) -> str | None:
    q = query.lower()
    for action, words in KEYWORDS.items():
        if any(w in q for w in words):
            return action
    return None


def pct_change(rr: float) -> str:
    """0.92 -> '8% fewer', 1.44 -> '44% more'."""
    change = round(abs(1 - rr) * 100)
    return f"{change}% {'fewer' if rr < 1 else 'more'}"
