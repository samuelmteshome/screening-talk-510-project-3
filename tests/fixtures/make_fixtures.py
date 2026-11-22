"""Regenerate the made-up raw NHANES fixtures used by the tests.

Usage: python tests/fixtures/make_fixtures.py

Two prostate cycles are enough to test both biopsy variable names
(KIQ190 in 2003-2004, KIQ191 in 2009-2010). Values are random, not real data.
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "raw" / "prostate"
CYCLES = {
    "2003-2004": {"suffix": "C", "psa_file": "L11PSA_C", "biopsy": "KIQ190", "seqn0": 21005},
    "2009-2010": {"suffix": "F", "psa_file": "PSA_F", "biopsy": "KIQ191", "seqn0": 51624},
}
N = 60


def make_cycle(cycle: str, spec: dict, rng: np.random.Generator) -> None:
    seqn = np.arange(spec["seqn0"], spec["seqn0"] + N)
    sex = rng.choice([1, 2], size=N, p=[0.7, 0.3])
    age = rng.integers(30, 81, size=N)
    demo = pd.DataFrame(
        {
            "SEQN": seqn,
            "RIAGENDR": sex,
            "RIDAGEYR": age,
            "RIDRETH1": rng.integers(1, 6, size=N),
            "WTMEC2YR": rng.uniform(5_000, 60_000, size=N).round(2),
        }
    )
    bmx = pd.DataFrame({"SEQN": seqn, "BMXBMI": rng.uniform(18, 45, size=N).round(1)})
    bmx.loc[rng.choice(N, 3, replace=False), "BMXBMI"] = np.nan

    tested = (sex == 1) & (age >= 40)
    psa = pd.DataFrame({"SEQN": seqn[tested]})
    n = len(psa)
    for col in ["KIQ115", "KIQ185", spec["biopsy"], "KIQ195", "KIQ201"]:
        psa[col] = 2
    yes_rows = rng.choice(n, 5, replace=False)  # a few men excluded, one rule each
    for row, col in zip(yes_rows, ["KIQ115", "KIQ185", spec["biopsy"], "KIQ195", "KIQ201"]):
        psa.loc[row, col] = 1
    psa["LBXP1"] = rng.lognormal(mean=0.2, sigma=0.9, size=n).round(2)
    psa.loc[rng.choice(n, 2, replace=False), "LBXP1"] = np.nan  # no result

    folder = OUT / cycle
    folder.mkdir(parents=True, exist_ok=True)
    demo.to_csv(folder / f"DEMO_{spec['suffix']}.csv", index=False)
    bmx.to_csv(folder / f"BMX_{spec['suffix']}.csv", index=False)
    psa.to_csv(folder / f"{spec['psa_file']}.csv", index=False)


if __name__ == "__main__":
    rng = np.random.default_rng(510)
    for cycle, spec in CYCLES.items():
        make_cycle(cycle, spec, rng)
    print(f"Wrote fixtures to {OUT}")
