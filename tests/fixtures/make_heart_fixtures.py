"""Regenerate the made-up heart fixtures (random values, not real data).

Usage: python tests/fixtures/make_heart_fixtures.py

Two cycles cover both HDL variable names (LBDHDL in 2001-2002 in L13_B,
LBDHDD in 2005-2006 in its own HDL_D file). The mortality file is written in
the real fixed-width .dat layout so the reader is tested too.
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "raw" / "heart"
N = 80
CYCLES = {
    "2001-2002": {"s": "B", "seqn0": 9966, "hdl": "LBDHDL", "lab": ["L13_B"]},
    "2005-2006": {"s": "D", "seqn0": 31128, "hdl": "LBDHDD", "lab": ["TCHOL_D", "HDL_D"]},
}


def dat_line(seqn, elig, mort, ucod, permth) -> str:
    line = [" "] * 48
    def put(start, end, val):
        text = "." if val is None else str(val)
        text = text.rjust(end - start + 1, "0" if val is not None and start == 17 else " ")
        line[start - 1:end] = list(text)
    put(1, 6, seqn)
    put(15, 15, elig)
    put(16, 16, mort)
    put(17, 19, ucod)
    put(46, 48, permth)
    return "".join(line)


def make_cycle(cycle: str, spec: dict, rng: np.random.Generator) -> None:
    s = spec["s"]
    seqn = np.arange(spec["seqn0"], spec["seqn0"] + N)
    folder = OUT / cycle
    folder.mkdir(parents=True, exist_ok=True)
    age = rng.integers(30, 85, size=N)
    pd.DataFrame({"SEQN": seqn, "RIAGENDR": rng.choice([1, 2], N), "RIDAGEYR": age,
                  "RIDRETH1": rng.integers(1, 6, N),
                  "WTMEC2YR": np.where(rng.random(N) < 0.05, 0, rng.uniform(5e3, 6e4, N).round(1))}
                 ).to_csv(folder / f"DEMO_{s}.csv", index=False)
    pd.DataFrame({"SEQN": seqn, "BMXBMI": rng.uniform(18, 45, N).round(1)}).to_csv(folder / f"BMX_{s}.csv", index=False)
    chol = rng.normal(205, 40, N).round()
    hdl = rng.normal(52, 14, N).round()
    if len(spec["lab"]) == 1:
        pd.DataFrame({"SEQN": seqn, "LBXTC": chol, spec["hdl"]: hdl}).to_csv(folder / f"{spec['lab'][0]}.csv", index=False)
    else:
        pd.DataFrame({"SEQN": seqn, "LBXTC": chol}).to_csv(folder / f"{spec['lab'][0]}.csv", index=False)
        pd.DataFrame({"SEQN": seqn, spec["hdl"]: hdl}).to_csv(folder / f"{spec['lab'][1]}.csv", index=False)
    bpx = pd.DataFrame({"SEQN": seqn, **{f"BPXSY{i}": rng.normal(128, 18, N).round() for i in (1, 2, 3)}})
    bpx.loc[rng.choice(N, 4, replace=False), "BPXSY1"] = np.nan
    bpx.to_csv(folder / f"BPX_{s}.csv", index=False)
    told = rng.choice([1, 2], N, p=[0.35, 0.65])
    pd.DataFrame({"SEQN": seqn, "BPQ020": told, "BPQ050A": np.where(told == 1, rng.choice([1, 2], N), np.nan)}
                 ).to_csv(folder / f"BPQ_{s}.csv", index=False)
    pd.DataFrame({"SEQN": seqn, "DIQ010": rng.choice([1, 2, 3], N, p=[0.12, 0.85, 0.03])}).to_csv(folder / f"DIQ_{s}.csv", index=False)
    ever = rng.choice([1, 2], N)
    pd.DataFrame({"SEQN": seqn, "SMQ020": ever, "SMQ040": np.where(ever == 1, rng.choice([1, 2, 3], N), np.nan)}
                 ).to_csv(folder / f"SMQ_{s}.csv", index=False)
    mcq = pd.DataFrame({"SEQN": seqn, **{f"MCQ160{x}": 2 for x in "BCDEF"}})
    for row, col in zip(rng.choice(N, 5, replace=False), [f"MCQ160{x}" for x in "BCDEF"]):
        mcq.loc[row, col] = 1  # a few people with prior heart disease or stroke
    mcq.to_csv(folder / f"MCQ_{s}.csv", index=False)

    a, b = cycle.split("-")
    lines = []
    for i, q in enumerate(seqn):
        if i % 20 == 7:      # not eligible for linkage
            lines.append(dat_line(q, 2, None, None, None)); continue
        died = rng.random() < 0.25
        ucod = int(rng.choice([1, 2, 5, 10])) if died else None
        permth = int(rng.integers(1, 200)) if died else int(rng.integers(150, 240))
        lines.append(dat_line(q, 1, 1 if died else 0, ucod, permth))
    (folder / f"NHANES_{a}_{b}_MORT_2019_PUBLIC.dat").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    rng = np.random.default_rng(5100)
    for cycle, spec in CYCLES.items():
        make_cycle(cycle, spec, rng)
    print(f"Wrote fixtures to {OUT}")
