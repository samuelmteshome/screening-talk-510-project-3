"""Merge raw NHANES files, check them against schema.yaml, apply the topic's
cleaning rules, and write one parquet file per topic (see docs/data_contract.md).

Usage:
    python -m src.data.clean --topic prostate

Writes data/clean/<topic>/clean.parquet and docs/cleaning/<topic>.md (row
counts after each rule, plus the file's SHA-256).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from src.config import REPO_ROOT, load_config, load_topic, load_yaml, source_variable
from src.data import storage
from src.data.download import local_name

log = logging.getLogger(__name__)

RACE_ETH = {
    1: "mexican_american",
    2: "other_hispanic",
    3: "non_hispanic_white",
    4: "non_hispanic_black",
    5: "other_or_multiracial",
}
YES = 1  # NHANES yes/no questions: 1 yes, 2 no, 7 refused, 9 don't know


class SchemaError(ValueError):
    """A raw file is missing a column, or a value breaks schema.yaml."""


# Column positions in the 2019 public-use linked mortality files (fixed width,
# 1-based inclusive, from the NCHS read-in programs for NHANES).
MORTALITY_COLUMNS = {
    "SEQN": (1, 6),
    "ELIGSTAT": (15, 15),
    "MORTSTAT": (16, 16),
    "UCOD_LEADING": (17, 19),
    "DIABETES": (20, 20),
    "HYPERTEN": (21, 21),
    "PERMTH_INT": (43, 45),
    "PERMTH_EXM": (46, 48),
}


def read_mortality(path: Path) -> pd.DataFrame:
    """Read a linked mortality .dat file into numeric columns ('.' and blanks become NaN)."""
    colspecs = [(start - 1, end) for start, end in MORTALITY_COLUMNS.values()]
    df = pd.read_fwf(path, colspecs=colspecs, names=list(MORTALITY_COLUMNS), dtype=str)
    return df.apply(lambda col: pd.to_numeric(col.str.strip().replace({".": None, "": None}), errors="coerce"))


def read_raw(path: Path) -> pd.DataFrame:
    """Read a raw NHANES file (.xpt, .dat linked mortality, or .csv for test fixtures)."""
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".dat":
        return read_mortality(path)
    return pd.read_sas(path, format="xport", encoding=None)  # all columns used are numeric


def _raw_path(raw_dir: Path, topic: str, cycle: str, entry: str) -> Path:
    path = raw_dir / topic / cycle / local_name(entry)
    if path.exists():
        return path
    csv = path.with_suffix(".csv")
    if csv.exists():
        return csv
    raise FileNotFoundError(f"{path} not found: run `python -m src.data.download --topic {topic}`")


def load_cycle(topic: str, cycle: str, topic_cfg: dict[str, Any], raw_dir: Path) -> pd.DataFrame:
    """Merge one cycle's files on SEQN and rename NHANES variables to column names."""
    entries = topic_cfg["data"]["files"][cycle]
    merged: pd.DataFrame | None = None
    for entry in entries:
        frame = read_raw(_raw_path(raw_dir, topic, cycle, entry))
        merged = frame if merged is None else merged.merge(frame, on="SEQN", how="left")

    sources = topic_cfg["feature_sources"]
    mapping = {source_variable(sources, col, cycle): col for col in sources}
    missing = [f"{var} (for '{col}')" for var, col in mapping.items() if var not in merged.columns]
    if missing:
        raise SchemaError(
            f"{topic} {cycle}: missing {', '.join(missing)} in {entries}. "
            "NHANES may have renamed it: check the codebook and update feature_sources."
        )
    out = merged[["SEQN", *mapping]].rename(columns=mapping)
    out.insert(1, "cycle", cycle)
    return out


def validate(df: pd.DataFrame, rules: dict[str, dict[str, Any]], label: str) -> None:
    """Check columns and values against schema.yaml rules; raise listing every problem."""
    problems = []
    for col, rule in rules.items():
        if col not in df.columns:
            problems.append(f"{col}: column missing")
            continue
        values = df[col]
        if values.isna().any() and not rule.get("nullable", False):
            problems.append(f"{col}: {int(values.isna().sum())} missing values")
        present = values.dropna()
        if "allowed" in rule:
            bad = sorted(set(present.unique()) - set(rule["allowed"]))
            if bad:
                problems.append(f"{col}: unexpected values {bad[:5]}")
        for key, low in (("min", True), ("max", False)):
            if key in rule:
                off = present[present < rule[key]] if low else present[present > rule[key]]
                if len(off):
                    where = f" (cycles {sorted(df.loc[off.index, 'cycle'].unique())})" if "cycle" in df else ""
                    problems.append(f"{col}: values {'below' if low else 'above'} {rule[key]} "
                                    f"({len(off)} rows, e.g. {sorted(off.unique())[:5]}{where})")
    if problems:
        raise SchemaError(f"{label} failed schema.yaml checks:\n  " + "\n  ".join(problems))


def build_prostate(df: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    """Apply the prostate rules and build the target (PSA >= threshold)."""
    data = cfg["data"]
    counts = [("All participants in the merged files", len(df))]
    if data.get("male_only", True):
        df = df[df["sex"] == 1]
        counts.append(("Men", len(df)))
    df = df[df["age"].between(data["age_min"], data["age_max"])]
    counts.append((f"Aged {data['age_min']} to {data['age_max']}", len(df)))
    df = df[df["psa"].notna()]
    counts.append(("Have a total PSA result", len(df)))
    excluded = (df[data["exclude_if_yes"]] == YES).any(axis=1)
    df = df[~excluded]
    counts.append(("No prostate cancer history or recent prostate procedure", len(df)))

    out = pd.DataFrame(
        {
            "SEQN": df["SEQN"].astype("int64"),
            "cycle": df["cycle"],
            "target": (df["psa"] >= data["psa_threshold_ng_ml"]).astype("int64"),
            "exam_weight": df["exam_weight"].astype("float64"),
        }
    )
    for feature in cfg["features"]:
        out[feature] = df[feature]
    if "race_eth" in out:
        out["race_eth"] = out["race_eth"].astype(int).map(RACE_ETH)
    counts.append((f"Target: PSA >= {data['psa_threshold_ng_ml']} ng/mL", int(out["target"].sum())))
    return out, counts


def _yes(col: pd.Series) -> pd.Series:
    return (col == YES).astype("int64")


def build_heart(df: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    """Adults in the age range with no prior heart disease or stroke, linked to death
    records; target = died of heart disease or stroke within horizon_months of the exam."""
    data = cfg["data"]
    counts = [("All participants in the merged files", len(df))]
    df = df[df["age"].between(data["age_min"], data["age_max"])]
    counts.append((f"Aged {data['age_min']} to {data['age_max']}", len(df)))
    df = df[df["exam_weight"] > 0]
    counts.append(("Had the physical exam (exam weight > 0)", len(df)))
    df = df[df["eligstat"] == 1]
    counts.append(("Eligible for death-record linkage", len(df)))
    prior = (df[data["exclude_prior_cvd"]] == YES).any(axis=1)
    df = df[~prior]
    counts.append(("No prior heart failure, heart disease, angina, heart attack, or stroke", len(df)))
    horizon = data["horizon_months"]
    cvd_death = (df["mortstat"] == 1) & df["ucod_leading"].isin(data["ucod_codes"]) & (df["permth_exm"] <= horizon)
    # Alive people followed for less than the horizon have an unknown outcome (should be none: follow-up runs to 2019).
    unknown = (df["mortstat"] == 0) & (df["permth_exm"] < horizon)
    df, cvd_death = df[~unknown], cvd_death[~unknown]
    counts.append((f"Followed at least {horizon} months or died", len(df)))

    sbp = df[["sbp_1", "sbp_2", "sbp_3"]].mean(axis=1, skipna=True)
    out = pd.DataFrame(
        {
            "SEQN": df["SEQN"].astype("int64"),
            "cycle": df["cycle"],
            "target": cvd_death.astype("int64"),
            "exam_weight": df["exam_weight"].astype("float64"),
            "age": df["age"].astype("float64"),
            "sex": df["sex"].map({1: "male", 2: "female"}),
            "race_eth": df["race_eth"].astype(int).map(RACE_ETH),
            "bmi": df["bmi"],
            "total_chol": df["total_chol"],
            "hdl": df["hdl"],
            "sbp": sbp,
            # BPQ050A is only asked of people told they have high blood pressure.
            "on_bp_meds": _yes(df["bp_meds_now"]),
            "diabetes": _yes(df["diabetes_told"]),
            # Never-smokers (SMQ020 = 2) skip SMQ040; every day (1) or some days (2) = current smoker.
            "current_smoker": df["smoke_now"].isin([1, 2]).astype("int64"),
            "died_any_cause_10y": ((df["mortstat"] == 1) & (df["permth_exm"] <= horizon)).astype("int64"),
            "followup_months": df["permth_exm"],
        }
    )
    counts.append((f"Target: died of heart disease or stroke within {horizon // 12} years", int(out["target"].sum())))
    return out, counts


def build_colorectal(df: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    """Adults in the screening ages who answered the cancer question; target = ever told
    they had colon or rectal cancer (MCQ230A-C)."""
    data = cfg["data"]
    counts = [("All participants in the merged files", len(df))]
    df = df[df["age"].between(data["age_min"], data["age_max"])]
    counts.append((f"Aged {data['age_min']} to {data['age_max']}", len(df)))
    df = df[df["ever_cancer"].isin([1, 2])]
    counts.append(("Answered 'ever told you had cancer' yes or no", len(df)))
    codes = list(data["cancer_type_codes"].values())
    crc = df[["cancer_1", "cancer_2", "cancer_3"]].isin(codes).any(axis=1)
    out = pd.DataFrame(
        {
            "SEQN": df["SEQN"].astype("int64"),
            "cycle": df["cycle"],
            "target": crc.astype("int64"),
            "exam_weight": df["exam_weight"].fillna(0).astype("float64"),
            "age": df["age"].astype("float64"),
            "sex": df["sex"].map({1: "male", 2: "female"}),
            "race_eth": df["race_eth"].astype(int).map(RACE_ETH),
            "bmi": df["bmi"],
            "ever_smoked": _yes(df["smoked_100"]),
            "current_smoker": df["smoke_now"].isin([1, 2]).astype("int64"),
            "diabetes": _yes(df["diabetes_told"]),
            "other_cancer": ((df["ever_cancer"] == YES) & ~crc).astype("int64"),
        }
    )
    counts.append(("Target: ever told they had colon or rectal cancer", int(out["target"].sum())))
    return out, counts


BUILDERS: dict[str, Callable[[pd.DataFrame, dict[str, Any]], tuple[pd.DataFrame, list]]] = {
    "prostate": build_prostate,
    "heart": build_heart,
    "colorectal": build_colorectal,
}


def write_counts(path: Path, topic: str, counts: list[tuple[str, int]], sha256: str, n_by_cycle: pd.Series) -> None:
    """Write the cleaning counts as a short Markdown table."""
    lines = [f"# Cleaning counts: {topic}", "", "| Step | Rows |", "| --- | --- |"]
    lines += [f"| {step} | {n:,} |" for step, n in counts]
    lines += ["", "| Cycle | Rows in clean file |", "| --- | --- |"]
    lines += [f"| {cycle} | {n:,} |" for cycle, n in n_by_cycle.items()]
    lines += ["", f"SHA-256 of `clean.parquet`: `{sha256}`", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def clean_topic(
    topic: str,
    config: dict[str, Any] | None = None,
    topic_cfg: dict[str, Any] | None = None,
    raw_dir: Path | None = None,
    out_dir: Path | None = None,
    docs_dir: Path | None = None,
    schema: dict[str, Any] | None = None,
) -> Path:
    """Run the clean step for ``topic`` and return the path of the parquet file."""
    config = config or load_config()
    topic_cfg = topic_cfg or load_topic(topic)
    schema = schema if schema is not None else load_yaml(REPO_ROOT / "schema.yaml")
    raw_dir = Path(raw_dir or REPO_ROOT / config["data"]["raw_dir"])
    out_dir = Path(out_dir or REPO_ROOT / config["data"]["clean_dir"])
    docs_dir = Path(docs_dir or REPO_ROOT / "docs" / "cleaning")

    raw = pd.concat(
        [load_cycle(topic, cycle, topic_cfg, raw_dir) for cycle in topic_cfg["data"]["cycles"]],
        ignore_index=True,
    )
    validate(raw, schema.get(topic) or {}, f"{topic} raw data")
    clean, counts = BUILDERS[topic](raw, topic_cfg)
    clean = clean.sort_values(["cycle", "SEQN"]).reset_index(drop=True)

    path = out_dir / topic / "clean.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(path, index=False)
    sha = storage.sha256_file(path)
    write_counts(docs_dir / f"{topic}.md", topic, counts, sha, clean["cycle"].value_counts().sort_index())
    for step, n in counts:
        log.info("%-60s %8d", step, n)
    log.info("Wrote %s (sha256 %s)", path, sha)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clean_topic(args.topic)


if __name__ == "__main__":
    main()
