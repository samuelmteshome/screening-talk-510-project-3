"""Train the heart model: chance of dying of heart disease or stroke within 10 years.

Usage:
    python -m src.train_heart [--clean data/clean/heart/clean.parquet] [--final]

Fits on the training cycles and reports on the validation cycle. ``--final`` also
reports on the held-out test cycle (run once, after the model is chosen).
Compares against an age + sex baseline. Logs to Weights & Biases when
WANDB_API_KEY is set. Writes models/heart/model.joblib and docs/models/heart.md.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from src.config import REPO_ROOT, load_topic  # noqa: E402

log = logging.getLogger(__name__)
BASELINE = ["age", "sex"]
BAR, BAR2 = "#2563eb", "#94a3b8"


def build(features: list[str], df: pd.DataFrame) -> Pipeline:
    cat = [f for f in features if not pd.api.types.is_numeric_dtype(df[f])]
    num = [f for f in features if f not in cat]
    pre = ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                          ("scale", StandardScaler())]), num),
        ("cat", OneHotEncoder(drop="first", handle_unknown="ignore"), cat),
    ])
    return Pipeline([("pre", pre), ("lr", LogisticRegression(max_iter=2000, C=1.0))])


def metrics(y: pd.Series, p: np.ndarray) -> dict:
    return {"auc": round(float(roc_auc_score(y, p)), 3), "brier": round(float(brier_score_loss(y, p)), 4),
            "events": int(y.sum()), "n": int(len(y)),
            "predicted_per_1000": round(float(p.mean() * 1000), 1), "observed_per_1000": round(float(y.mean() * 1000), 1)}


def calibration_chart(y: pd.Series, p: np.ndarray, path: Path, title: str) -> None:
    """Predicted vs observed deaths per 1,000, by fifth of predicted risk (bar chart)."""
    groups = pd.qcut(p, 5, labels=["Lowest", "Low", "Middle", "High", "Highest"])
    t = pd.DataFrame({"y": y.values, "p": p, "g": groups}).groupby("g", observed=True).mean() * 1000
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.bar(x - 0.2, t["p"], 0.4, label="Model predicted", color=BAR)
    ax.bar(x + 0.2, t["y"], 0.4, label="Actually died", color=BAR2)
    ax.set_xticks(x, [f"{g}\nrisk" for g in t.index])
    ax.set_ylabel("Deaths per 1,000 over 10 years")
    ax.set_title(title, loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def odds_ratios(model: Pipeline) -> pd.DataFrame:
    names = model.named_steps["pre"].get_feature_names_out()
    coef = model.named_steps["lr"].coef_[0]
    return pd.DataFrame({"term": [n.split("__", 1)[1] for n in names], "odds_ratio": np.exp(coef).round(2)})


def run(clean_path: Path, final: bool = False) -> dict:
    cfg = load_topic("heart")
    features = cfg["model_features"]
    df = pd.read_parquet(clean_path)
    sp = cfg["split"]
    train, val, test = (df[df["cycle"].isin(sp[k])] for k in ("train_cycles", "val_cycles", "test_cycles"))

    results, models = {}, {}
    for name, feats in (("baseline_age_sex", BASELINE), ("model", features)):
        m = build(feats, train).fit(train[feats], train["target"])
        models[name] = m
        results[name] = {"val": metrics(val["target"], m.predict_proba(val[feats])[:, 1])}
        if final:
            results[name]["test"] = metrics(test["target"], m.predict_proba(test[feats])[:, 1])

    out_docs = REPO_ROOT / "docs" / "models"
    out_docs.mkdir(parents=True, exist_ok=True)
    model = models["model"]
    calibration_chart(val["target"], model.predict_proba(val[features])[:, 1], out_docs / "heart_calibration_val.png",
                      "Validation (2005-2006): predicted vs actual heart and stroke deaths")

    out_model = REPO_ROOT / "models" / "heart"
    out_model.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": features, "version": cfg.get("version", "v1"),
                 "target": "cv_death_10y", "age_range": [cfg["data"]["age_min"], cfg["data"]["age_max"]]}, out_model / "model.joblib")
    (out_model / "metrics.json").write_text(json.dumps(results, indent=2))

    lines = ["# Heart model", "",
             f"Logistic regression on {', '.join(features)}. Target: death from heart disease or stroke "
             "within 10 years of the NHANES exam (linked death records).", "",
             f"Trained on {', '.join(sp['train_cycles'])} ({len(train):,} people, {int(train['target'].sum())} deaths).", "",
             "| Model | Split | People | Deaths | AUC | Brier | Predicted per 1,000 | Observed per 1,000 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, r in results.items():
        for split, m in r.items():
            lines.append(f"| {name} | {split} | {m['n']:,} | {m['events']} | {m['auc']} | {m['brier']} | "
                         f"{m['predicted_per_1000']} | {m['observed_per_1000']} |")
    lines += ["", "![Calibration](heart_calibration_val.png)", "", "## Odds ratios (per SD for numbers)", "",
              "| Term | Odds ratio |", "| --- | --- |"]
    lines += [f"| {r.term} | {r.odds_ratio} |" for r in odds_ratios(model).itertuples()]
    (out_docs / "heart.md").write_text("\n".join(lines) + "\n")

    if os.environ.get("WANDB_API_KEY"):
        import wandb
        run_ = wandb.init(project="screening-talk", job_type="train", name="heart-logreg",
                          config={"topic": "heart", "features": features, **sp})
        run_.log({f"{n}/{s}/{k}": v for n, r in results.items() for s, m in r.items() for k, v in m.items()})
        run_.log({"calibration_val": wandb.Image(str(out_docs / "heart_calibration_val.png"))})
        run_.finish()
    log.info("Results: %s", json.dumps(results))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clean", type=Path, default=REPO_ROOT / "data" / "clean" / "heart" / "clean.parquet")
    parser.add_argument("--final", action="store_true", help="also score the held-out test cycle")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.clean, args.final)


if __name__ == "__main__":
    main()
