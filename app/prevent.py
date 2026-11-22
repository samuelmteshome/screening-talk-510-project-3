"""AHA PREVENT base equations: 10-year risk of a first heart attack, stroke, or heart failure.

Khan SS et al. Development and Validation of the American Heart Association's
PREVENT Equations. Circulation 2024;149:430-449. Base model, ages 30-79, people
without known heart disease. Coefficients transcribed from the published
formula (MDCalc review of PREVENT, 2026); check against the paper's supplement
before relying on them.

Used for (1) the heart attack / stroke chance on the heart pages, since NHANES
only records deaths, and (2) people aged 30-39 or 76-79, outside our model's
40-75 range. eGFR (kidney function) is not asked, so it is set to 90 (normal).
"""
from __future__ import annotations

import math

AGE_MIN, AGE_MAX = 30, 79
MG_PER_MMOL = 38.67  # cholesterol mg/dL -> mmol/L

# Typical values (NHANES 1999-2006 adults 40-75, our EDA) used when an answer is left blank.
TYPICAL = {"total_chol": 207.0, "hdl": 51.0, "sbp": 127.0}

TERMS = ("const", "cage", "cnhdl", "chdl", "csbp", "csbp2", "dm", "smoking", "cegfr", "cegfr2",
         "bptreat", "statin", "csbp2_bptreat", "cnhdl_statin", "cage_cnhdl", "cage_chdl", "cage_csbp2",
         "cage_dm", "cage_smoking", "cage_cegfr")

# Base 10-year total CVD (MI, stroke, heart failure).
CVD = {
    "female": (-3.307728, 0.7939329, 0.0305239, -0.1606857, -0.2394003, 0.3600781, 0.8667604, 0.5360739,
               0.6045917, 0.0433769, 0.3151672, -0.1477655, -0.0663612, 0.1197879, -0.0819715, 0.0306769,
               -0.0946348, -0.27057, -0.078715, -0.1637806),
    "male": (-3.031168, 0.7688528, 0.0736174, -0.0954431, -0.4347345, 0.3362658, 0.7692857, 0.4386871,
             0.5378979, 0.0164827, 0.288879, -0.1337349, -0.0475924, 0.150273, -0.0517874, 0.0191169,
             -0.1049477, -0.2251948, -0.0895067, -0.1543702),
}
# Base 10-year ASCVD (MI and stroke only) — what the heart pages call "heart attack or stroke".
ASCVD = {
    "female": (-3.819975, 0.719883, 0.1176967, -0.151185, -0.0835358, 0.3592852, 0.8348585, 0.4831078,
               0.4864619, 0.0397779, 0.2265309, -0.0592374, -0.0395762, 0.0844423, -0.0567839, 0.0325692,
               -0.1035985, -0.2417542, -0.0791142, -0.1671492),
    "male": (-3.500655, 0.7099847, 0.1658663, -0.1144285, -0.2837212, 0.3239977, 0.7189597, 0.3956973,
             0.3690075, 0.0203619, 0.2036522, -0.0865581, -0.0322916, 0.114563, -0.0300005, 0.0232747,
             -0.0927024, -0.2018525, -0.0970527, -0.1217081),
}


def in_range(age: float) -> bool:
    return AGE_MIN <= age <= AGE_MAX


def _x(sex: str, age: float, total_chol: float, hdl: float, sbp: float, diabetes: bool, smoker: bool,
       bp_meds: bool, statin: bool, egfr: float) -> dict[str, float]:
    tc, h = total_chol / MG_PER_MMOL, hdl / MG_PER_MMOL
    v = {
        "const": 1.0,
        "cage": (age - 55) / 10,
        "cnhdl": tc - h - 3.5,
        "chdl": (h - 1.3) / 0.3,
        "csbp": (min(sbp, 110) - 110) / 20,
        "csbp2": (max(sbp, 110) - 130) / 20,
        "dm": float(diabetes),
        "smoking": float(smoker),
        "cegfr": (min(egfr, 60) - 60) / -15,
        "cegfr2": (max(egfr, 60) - 90) / -15,
        "bptreat": float(bp_meds),
        "statin": float(statin),
    }
    v["csbp2_bptreat"] = v["csbp2"] * v["bptreat"]
    v["cnhdl_statin"] = v["cnhdl"] * v["statin"]
    for k in ("cnhdl", "chdl", "csbp2", "dm", "smoking", "cegfr"):
        v[f"cage_{k}"] = v["cage"] * v[k]
    return v


def risk(sex: str, age: float, total_chol: float | None = None, hdl: float | None = None,
         sbp: float | None = None, diabetes: bool = False, smoker: bool = False, bp_meds: bool = False,
         statin: bool = False, egfr: float = 90.0, outcome: str = "ascvd") -> float:
    """10-year risk as a fraction (0-1). Blank lab values use typical values. Raises outside ages 30-79."""
    if not in_range(age):
        raise ValueError(f"PREVENT covers ages {AGE_MIN}-{AGE_MAX}")
    coef = (ASCVD if outcome == "ascvd" else CVD)[sex]
    v = _x(sex, age, total_chol or TYPICAL["total_chol"], hdl or TYPICAL["hdl"], sbp or TYPICAL["sbp"],
           diabetes, smoker, bp_meds, statin, egfr)
    x = sum(b * v[t] for t, b in zip(TERMS, coef))
    return math.exp(x) / (1 + math.exp(x))


def from_profile(p: dict, outcome: str = "ascvd") -> tuple[float, list[str]]:
    """Risk for the intake answers, and which answers were blank (filled with typical values)."""
    missing = [k for k in TYPICAL if not float(p.get(k, 0) or 0)]
    r = risk(p["sex"], float(p["age"]), float(p.get("total_chol", 0) or 0), float(p.get("hdl", 0) or 0),
             float(p.get("sbp", 0) or 0), bool(int(p.get("diabetes", 0))), bool(int(p.get("current_smoker", 0))),
             bool(int(p.get("on_bp_meds", 0))), outcome=outcome)
    return r, missing
