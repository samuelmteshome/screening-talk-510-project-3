"""Smoke test for the deployed API: /health, /topics and one /predict per topic.

Usage:
    python scripts/smoke_test.py https://screening-talk-api-xxxx.run.app
Prints each response and exits non-zero if any call fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

EXAMPLE = json.loads((Path(__file__).resolve().parents[1] / "tests" / "example_request.json").read_text())
REQUESTS = [
    EXAMPLE,
    {"topic": "heart", "age_years": 60, "sex": "female", "bmi_kg_m2": 28, "total_chol": 210, "hdl": 50,
     "sbp": 140, "on_bp_meds": False, "diabetes": False, "current_smoker": True},
    {"topic": "colorectal", "age_years": 60, "sex": "male", "bmi_kg_m2": 29, "ever_smoked": True, "diabetes": False},
]


def main(base: str) -> int:
    base = base.rstrip("/")
    failed = 0
    for method, path, body in [("GET", "/health", None), ("GET", "/topics", None)] + [("POST", "/predict", b) for b in REQUESTS]:
        r = requests.request(method, base + path, json=body, timeout=60)
        ok = r.status_code == 200
        failed += not ok
        out = r.json() if ok else r.text
        if path == "/predict" and ok:  # keep the output short: drop the evidence text
            out = {k: v for k, v in out.items() if k != "evidence"} | {"evidence_files": [e["file"] for e in out["evidence"]]}
        print(f"{method} {path} -> {r.status_code}\n{json.dumps(out, indent=2)[:1500]}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
