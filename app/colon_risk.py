"""Personal 10-year colorectal cancer risk and what a colonoscopy changes.

Baseline: SEER age- and sex-specific incidence and death rates (2013-2017),
summed year by year over the next 10 years. Adjusted by meta-analysis relative
risks for family history, smoking and obesity, multiplied together (assumes the
factors act independently). Colonoscopy effect: NordICC trial. All numbers are
in evidence/colorectal_risk.json. Pure Python so it can be tested in CI.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache

from catalog import EVIDENCE_DIR

AGE_MIN, AGE_MAX = 45, 75   # USPSTF screening ages


@lru_cache(maxsize=None)
def data() -> dict:
    return json.loads((EVIDENCE_DIR / "colorectal_risk.json").read_text())


def _rate(kind: str, sex: str, age: float) -> float:
    b = data()["baseline"]
    bands, rates = b["age_bands"], b[kind][sex]
    i = max(j for j, lo in enumerate(bands) if lo <= max(age, bands[0]))
    return rates[i] / 100_000


def factors(p: dict) -> dict[str, float]:
    """Relative risks that apply to this person (name -> RR)."""
    rf = data()["risk_factors"]
    out = {}
    if int(p.get("family_crc", 0)):
        out["family_history"] = rf["family_history"]["rr"]
    if int(p.get("ever_smoked", 0)) or int(p.get("current_smoker", 0)):
        out["ever_smoked"] = rf["ever_smoked"]["rr"]
    if float(p.get("bmi", 0) or 0) >= 30:
        out["obese"] = rf["obese"]["rr"]
    return out


def risk(p: dict, kind: str = "incidence", years: int = 10) -> float:
    """10-year chance (0-1) of getting ('incidence') or dying of ('mortality') colorectal cancer."""
    rr = math.prod(factors(p).values())
    age = float(p["age"])
    hazard = sum(_rate(kind, p["sex"], age + t) for t in range(years)) * rr
    return 1 - math.exp(-hazard)


def in_range(age: float) -> bool:
    return AGE_MIN <= age <= AGE_MAX
