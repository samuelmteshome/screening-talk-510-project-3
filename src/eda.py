"""Exploratory data analysis for a cleaned topic, written for choosing features.

Usage:
    python -m src.eda --topic heart [--clean data/clean/heart/clean.parquet]

Writes docs/eda/<topic>/README.md plus bar charts (PNG) next to it. Uses only
the training and validation cycles, so the test cycles stay unseen.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pandas.api.types import is_numeric_dtype  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from src.config import REPO_ROOT, load_config, load_topic  # noqa: E402

log = logging.getLogger(__name__)

LABELS = {
    "age": "Age (years)", "sex": "Sex", "race_eth": "Race / ethnicity", "bmi": "BMI",
    "total_chol": "Total cholesterol (mg/dL)", "hdl": "HDL cholesterol (mg/dL)",
    "sbp": "Systolic blood pressure (mmHg)", "on_bp_meds": "Takes BP medicine",
    "diabetes": "Diabetes", "current_smoker": "Current smoker",
}
BAR = "#2563eb"
LABELS.update({"ever_smoked": "Ever smoked (100+ cigarettes)", "other_cancer": "Had another cancer"})

# What the target means, per topic (chart axis and report wording).
OUTCOME = {
    "heart": ("Died of heart disease or stroke within 10 years",
              "Deaths from heart disease or stroke per 1,000 (10 years)"),
    "colorectal": ("Ever told they had colon or rectal cancer",
                   "People who have had colon or rectal cancer, per 1,000"),
}


def _bins(series: pd.Series) -> pd.Series:
    """Readable, ordered groups: Yes/No for flags, as-is for categories, quintiles like "40-45" for numbers."""
    if not is_numeric_dtype(series):
        return series.map(lambda v: v if pd.isna(v) else str(v).replace("_", " ").capitalize())
    if series.nunique() <= 2:
        return series.map({1: "Yes", 0: "No", 1.0: "Yes", 0.0: "No"})
    q = pd.qcut(series, 5, duplicates="drop")
    labels = [f"{iv.left:.0f} to {iv.right:.0f}" for iv in q.cat.categories]
    labels[0] = f"Under {q.cat.categories[0].right:.0f}"
    labels[-1] = f"Over {q.cat.categories[-1].left:.0f}"
    return q.cat.rename_categories(labels)


def rate_by(df: pd.DataFrame, col: str) -> pd.DataFrame:
    g = df.groupby(_bins(df[col]), dropna=True, observed=True, sort=True)["target"]
    return pd.DataFrame({"n": g.size().astype(int), "events": g.sum().astype(int),
                         "per_1000": (g.mean() * 1000).round(1)})


def bar(ax, table: pd.DataFrame, title: str, xlabel: str = OUTCOME["heart"][1]) -> None:
    ax.barh(table.index.astype(str), table["per_1000"], color=BAR)
    for y, (v, n) in enumerate(zip(table["per_1000"], table["n"])):
        ax.text(v, y, f" {v:g}  (n={n:,})", va="center", fontsize=8)
    ax.set_title(title, fontsize=10, loc="left")
    ax.set_xlabel(xlabel, fontsize=8)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)


def univariate(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """AUC of each feature alone, and the age-adjusted odds ratio per SD (or yes vs no)."""
    rows = []
    for f in features:
        d = df[list(dict.fromkeys(["target", "age", f]))].dropna()
        x = pd.get_dummies(d[[f]], drop_first=True, dtype=float) if not is_numeric_dtype(d[f]) else d[[f]].astype(float)
        auc = roc_auc_score(d["target"], LogisticRegression(max_iter=1000).fit(x, d["target"]).predict_proba(x)[:, 1])
        row = {"feature": LABELS.get(f, f), "n": len(d), "AUC alone": round(auc, 3)}
        if f != "age" and x.shape[1] == 1:
            z = x.iloc[:, 0]
            scale = z.std() if z.nunique() > 2 else 1.0
            xa = pd.DataFrame({"age": d["age"], f: z / scale})
            coef = LogisticRegression(max_iter=1000, C=1e6).fit(xa, d["target"]).coef_[0][1]
            row["Age-adjusted odds ratio"] = round(float(np.exp(coef)), 2)
            row["per"] = "1 SD" if scale != 1.0 else ("men vs women" if f == "sex" else "yes vs no")
        rows.append(row)
    return pd.DataFrame(rows)


def md_table(df: pd.DataFrame, index: bool = False) -> str:
    """Markdown table without extra dependencies."""
    if index:
        df = df.reset_index()
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    lines += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def run(topic: str, clean_path: Path, out_dir: Path) -> Path:
    cfg = load_topic(topic)
    df = pd.read_parquet(clean_path)
    keep = cfg["split"]["train_cycles"] + cfg["split"]["val_cycles"]
    held_out = cfg["split"]["test_cycles"]
    df = df[df["cycle"].isin(keep)].copy()
    features = [f for f in cfg["features"] if f in df.columns]
    out_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# EDA: {topic}", "",
          f"Training and validation cycles only ({', '.join(keep)}); test cycles ({', '.join(held_out)}) are not looked at.", ""]

    n, events = len(df), int(df["target"].sum())
    md += ["## Outcome", "",
           f"- People: **{n:,}**",
           f"- {OUTCOME.get(topic, OUTCOME['heart'])[0]}: **{events:,}** ({events / n * 1000:.1f} per 1,000)"]
    if "died_any_cause_10y" in df:
        md.append(f"- Died of any cause within 10 years: {int(df['died_any_cause_10y'].sum()):,} "
                  "(deaths from other causes count as no event)")
    md.append("")

    by_cycle = rate_by(df.assign(cycle_=df["cycle"]), "cycle_")
    md += ["| Cycle | People | Events | Per 1,000 |", "| --- | --- | --- | --- |"]
    md += [f"| {c} | {int(r.n):,} | {int(r.events):,} | {r.per_1000:g} |" for c, r in by_cycle.iterrows()]
    md.append("")

    miss = (df[features].isna().mean() * 100).round(1).sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(6, 0.35 * len(miss) + 1))
    ax.barh([LABELS.get(c, c) for c in miss.index], miss.values, color=BAR)
    for y, v in enumerate(miss.values):
        ax.text(v, y, f" {v:g}%", va="center", fontsize=8)
    ax.set_title("Missing values by feature (%)", fontsize=10, loc="left")
    ax.invert_yaxis(); ax.spines[["top", "right"]].set_visible(False); ax.tick_params(labelsize=8)
    fig.tight_layout(); fig.savefig(out_dir / "missing.png", dpi=150); plt.close(fig)
    complete = int(df[features].notna().all(axis=1).sum())
    md += ["## Missing values", "", "![Missing values](missing.png)", "",
           f"People with every candidate feature present: **{complete:,}** of {n:,} ({complete / n:.0%}).", ""]

    summary = []
    for f in features:
        s = df[f]
        if not is_numeric_dtype(s):
            top = s.value_counts(normalize=True).round(3).head(5)
            summary.append((LABELS.get(f, f), ", ".join(f"{k} {v:.0%}" for k, v in top.items())))
        elif s.nunique() <= 2:
            summary.append((LABELS.get(f, f), f"{s.mean():.1%} yes"))
        else:
            summary.append((LABELS.get(f, f), f"median {s.median():g} (IQR {s.quantile(.25):g} to {s.quantile(.75):g})"))
    md += ["## Feature summary", "", "| Feature | Values |", "| --- | --- |"]
    md += [f"| {a} | {b} |" for a, b in summary] + [""]

    cols = 2
    rows = int(np.ceil(len(features) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(11, 2.4 * rows))
    for ax, f in zip(axes.flat, features):
        bar(ax, rate_by(df, f), LABELS.get(f, f), OUTCOME.get(topic, OUTCOME["heart"])[1])
    for ax in list(axes.flat)[len(features):]:
        ax.axis("off")
    fig.tight_layout(); fig.savefig(out_dir / "event_rate_by_feature.png", dpi=150); plt.close(fig)
    md += ["## Event rate by feature", "",
           "Continuous features are split into five equal-sized groups.", "",
           "![Event rate by feature](event_rate_by_feature.png)", ""]

    uni = univariate(df, features)
    md += ["## How much each feature tells us", "",
           "AUC alone: 0.5 is a coin flip, 1.0 is perfect. Odds ratio is after accounting for age "
           "(per standard deviation for numbers, yes vs no for yes/no features).", "",
           md_table(uni), ""]

    cont = [f for f in features if is_numeric_dtype(df[f]) and df[f].nunique() > 2]
    md += ["## Correlation between numeric features", "", md_table(df[cont].corr().round(2).rename(index=LABELS), index=True), ""]

    path = out_dir / "README.md"
    path.write_text("\n".join(md))
    log.info("Wrote %s", path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", required=True)
    parser.add_argument("--clean", type=Path, help="clean parquet (default: data/clean/<topic>/clean.parquet)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clean = args.clean or REPO_ROOT / load_config()["data"]["clean_dir"] / args.topic / "clean.parquet"
    run(args.topic, clean, REPO_ROOT / "docs" / "eda" / args.topic)


if __name__ == "__main__":
    main()
