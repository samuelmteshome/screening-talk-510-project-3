"""Regenerate the made-up colorectal fixtures (random values, not real data).

Usage: python tests/fixtures/make_colorectal_fixtures.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "raw" / "colorectal"
N = 120
CYCLES = {"2003-2004": ("C", 21005), "2013-2014": ("H", 73557)}


def make_cycle(cycle: str, s: str, seqn0: int, rng: np.random.Generator) -> None:
    seqn = np.arange(seqn0, seqn0 + N)
    folder = OUT / cycle
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"SEQN": seqn, "RIAGENDR": rng.choice([1, 2], N), "RIDAGEYR": rng.integers(20, 85, N),
                  "RIDRETH1": rng.integers(1, 6, N), "WTMEC2YR": rng.uniform(5e3, 6e4, N).round(1)}
                 ).to_csv(folder / f"DEMO_{s}.csv", index=False)
    bmi = pd.DataFrame({"SEQN": seqn, "BMXBMI": rng.uniform(18, 45, N).round(1)})
    bmi.loc[rng.choice(N, 5, replace=False), "BMXBMI"] = np.nan
    bmi.to_csv(folder / f"BMX_{s}.csv", index=False)
    ever = rng.choice([1, 2], N, p=[0.45, 0.55])
    pd.DataFrame({"SEQN": seqn, "SMQ020": ever, "SMQ040": np.where(ever == 1, rng.choice([1, 2, 3], N), np.nan)}
                 ).to_csv(folder / f"SMQ_{s}.csv", index=False)
    pd.DataFrame({"SEQN": seqn, "DIQ010": rng.choice([1, 2, 3], N, p=[0.12, 0.85, 0.03])}).to_csv(folder / f"DIQ_{s}.csv", index=False)
    cancer = rng.choice([1, 2, 9], N, p=[0.25, 0.73, 0.02])
    types = rng.choice([14, 16, 23, 30, 31, 32], N)
    mcq = pd.DataFrame({"SEQN": seqn, "MCQ220": cancer, "MCQ230A": np.where(cancer == 1, types, np.nan),
                        "MCQ230B": np.nan, "MCQ230C": np.nan})
    mcq.loc[(cancer == 1) & (rng.random(N) < 0.2), "MCQ230B"] = 31
    mcq.to_csv(folder / f"MCQ_{s}.csv", index=False)


if __name__ == "__main__":
    rng = np.random.default_rng(510)
    for cycle, (s, seqn0) in CYCLES.items():
        make_cycle(cycle, s, seqn0, rng)
    print(f"Wrote fixtures to {OUT}")
