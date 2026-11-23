"""Train and evaluate a topic's model, and log the run to Weights & Biases.

Usage:
    python -m src.train --topic prostate            # fit on train, pick C and report on validation
    python -m src.train --topic prostate --final    # refit on train+validation, report on test (once)

Options for local work: ``--data-uri data/clean/prostate/clean.parquet``
reads a local file, ``--allow-unverified`` accepts it before a hash is
recorded, ``--no-upload`` skips copying the model to the bucket.
Without WANDB_API_KEY the run is logged offline (``wandb sync`` uploads it later).

Each run writes runs/<run_id>/: model.joblib (preprocessing + model in one
Pipeline), model_card.json, metrics.json, calibration.png, run_metadata.yaml
and train.log. The same files are logged to W&B as a model artifact.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml

from src import evaluate
from src.config import REPO_ROOT, bucket_name, load_config, load_topic, resolve_uri
from src.data import storage
from src.data.ingest import load_clean
from src.features import AgeGroupBaseline, build_model, feature_types

log = logging.getLogger(__name__)
PACKAGES = ["numpy", "pandas", "pyarrow", "scikit-learn", "joblib", "wandb"]


def split_by_cycle(df: pd.DataFrame, split_cfg: dict[str, list[str]]) -> dict[str, pd.DataFrame]:
    """Train / validation / test sets from the survey cycles in the topic config."""
    parts = {name: df[df["cycle"].isin(split_cfg[f"{name}_cycles"])] for name in ("train", "val", "test")}
    for name, part in parts.items():
        if part.empty:
            raise ValueError(f"No rows for the {name} cycles {split_cfg[f'{name}_cycles']}")
    return parts


def git_info() -> dict[str, Any]:
    """Current commit and whether there are uncommitted changes."""
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()

    try:
        return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": os.environ.get("GIT_COMMIT", "unknown"), "dirty": None}


def package_versions() -> dict[str, str]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def start_wandb(config: dict[str, Any], topic: str, final: bool, run_config: dict[str, Any]):
    """Start a W&B run; offline when no API key is set (unless WANDB_MODE says otherwise)."""
    import wandb

    mode = os.environ.get("WANDB_MODE") or ("online" if os.environ.get("WANDB_API_KEY") else "offline")
    entity = (config.get("tracking") or {}).get("entity")
    return wandb.init(
        project=config["tracking"]["project"],
        entity=None if not entity or entity.startswith("<") else entity,
        job_type="final" if final else "train",
        tags=[topic, "final" if final else "dev"],
        config=run_config,
        mode=mode,
    )


def select_C(topic_cfg, parts, seed, weights) -> tuple[float, dict[float, float]]:
    """Pick C by validation Brier score (lower is better)."""
    features = topic_cfg["features"]
    train, val = parts["train"], parts["val"]
    scores = {}
    for C in topic_cfg["model_params"]["C_grid"]:
        model = build_model(topic_cfg, C, seed, train)
        model.fit(train[features], train["target"], model__sample_weight=weights(train))
        p = model.predict_proba(val[features])[:, 1]
        scores[C] = evaluate.metrics(val["target"], p, weights(val))["brier"]
        log.info("C=%-6g validation Brier %.5f", C, scores[C])
    best = min(scores, key=scores.get)
    return best, scores


def run(
    topic: str,
    final: bool = False,
    data_uri: str | None = None,
    allow_unverified: bool = False,
    upload: bool = True,
    runs_dir: Path | None = None,
    config: dict[str, Any] | None = None,
    topic_cfg: dict[str, Any] | None = None,
) -> Path:
    """Train, evaluate and log one run. Returns the run folder."""
    config = config or load_config()
    topic_cfg = topic_cfg or load_topic(topic)
    seed = int(config["seed"])
    np.random.seed(seed)
    features = topic_cfg["features"]
    use_weights = bool(topic_cfg["model_params"].get("use_survey_weights", False))

    def weights(part: pd.DataFrame):
        return part["exam_weight"].to_numpy() if use_weights else None

    wb = start_wandb(config, topic, final, {"topic": topic, "final": final, "seed": seed, "topic_config": topic_cfg})
    run_id = wb.id
    run_dir = Path(runs_dir or REPO_ROOT / "runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(run_dir / "train.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(file_handler)
    try:
        log.info("Run %s: topic=%s final=%s", run_id, topic, final)
        df, data_info = load_clean(topic, config, topic_cfg, uri=data_uri, allow_unverified=allow_unverified)
        parts = split_by_cycle(df, topic_cfg["split"])
        log.info("Rows: %s", {k: len(v) for k, v in parts.items()})

        best_C, c_scores = select_C(topic_cfg, parts, seed, weights)
        log.info("Selected C=%g", best_C)
        if final:
            log.warning("Final run: refitting on train+validation and scoring the test set")
            fit_on = pd.concat([parts["train"], parts["val"]])
            eval_name, eval_on = "test", parts["test"]
        else:
            fit_on, eval_name, eval_on = parts["train"], "val", parts["val"]

        model = build_model(topic_cfg, best_C, seed, fit_on)
        model.fit(fit_on[features], fit_on["target"], model__sample_weight=weights(fit_on))
        baseline = AgeGroupBaseline().fit(fit_on, fit_on["target"], sample_weight=weights(fit_on))

        y = eval_on["target"].to_numpy()
        p_model = model.predict_proba(eval_on[features])[:, 1]
        p_base = baseline.predict_proba(eval_on)[:, 1]
        m_model = evaluate.metrics(y, p_model, weights(eval_on))
        m_base = evaluate.metrics(y, p_base, weights(eval_on))
        auc_lo, auc_hi = evaluate.bootstrap_auc_ci(y, p_model, seed)
        results = {
            "split": eval_name,
            "model": {**m_model, "auc_ci95": [auc_lo, auc_hi]},
            "baseline_age_group": m_base,
            "brier_skill_vs_baseline": evaluate.brier_skill(m_model["brier"], m_base["brier"]),
            "selected_C": best_C,
            "validation_brier_by_C": {str(k): v for k, v in c_scores.items()},
        }
        calib = evaluate.calibration_table(y, p_model)
        evaluate.plot_calibration(calib, run_dir / "calibration.png", f"{topic}: predicted vs observed ({'validation' if eval_name == 'val' else eval_name} set)")
        subgroups = evaluate.subgroup_table(eval_on, y, p_model, "race_eth") if "race_eth" in eval_on else None
        log.info(
            "%s AUC %.3f (95%% CI %.3f-%.3f), Brier %.5f vs baseline %.5f, skill %.3f",
            eval_name, m_model["auc"], auc_lo, auc_hi, m_model["brier"], m_base["brier"],
            results["brier_skill_vs_baseline"],
        )

        joblib.dump(model, run_dir / "model.joblib")
        (run_dir / "metrics.json").write_text(json.dumps(results, indent=2))
        model_card = {
            "topic": topic,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "target": topic_cfg["data"].get("target"),
            "features": features,
            "feature_types": feature_types(topic_cfg, fit_on),
            "model": f"LogisticRegression(C={best_C})",
            "trained_on_cycles": sorted(fit_on["cycle"].unique().tolist()),
            "evaluated_on": eval_name,
            "metrics": results,
            "data": data_info,
            "survey_weights": use_weights,
            "intended_use": "Educational demo for patient-doctor conversations. Not medical advice.",
        }
        (run_dir / "model_card.json").write_text(json.dumps(model_card, indent=2))
        metadata = {
            "run_id": run_id,
            "created_at": model_card["created_at"],
            "topic": topic,
            "final": final,
            "git": git_info(),
            "docker_image": os.environ.get("DOCKER_IMAGE"),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": package_versions(),
            "seed": seed,
            "data": data_info,
            "config": config,
            "topic_config": topic_cfg,
        }
        (run_dir / "run_metadata.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False))

        model_uri = None
        if upload and bucket_name(config):
            template = topic_cfg["serve"]["model_uri"].replace("<run_id>", run_id)
            model_uri = storage.put(run_dir / "model.joblib", resolve_uri(template, config))
            log.info("Model uploaded to %s", model_uri)

        _log_to_wandb(wb, topic, run_dir, results, calib, subgroups, model_card, model_uri)
        return run_dir
    finally:
        logging.getLogger().removeHandler(file_handler)
        file_handler.close()
        wb.finish()


def _log_to_wandb(wb, topic, run_dir, results, calib, subgroups, model_card, model_uri) -> None:
    import wandb

    split = results["split"]
    flat = {
        f"{split}/auc": results["model"]["auc"],
        f"{split}/auc_ci_low": results["model"]["auc_ci95"][0],
        f"{split}/auc_ci_high": results["model"]["auc_ci95"][1],
        f"{split}/brier": results["model"]["brier"],
        f"{split}/baseline_auc": results["baseline_age_group"]["auc"],
        f"{split}/baseline_brier": results["baseline_age_group"]["brier"],
        f"{split}/brier_skill": results["brier_skill_vs_baseline"],
        f"{split}/observed_rate": results["model"]["observed_rate"],
        "selected_C": results["selected_C"],
    }
    wb.log({**flat, "calibration": wandb.Image(str(run_dir / "calibration.png")),
            "calibration_table": wandb.Table(dataframe=calib)})
    if subgroups is not None:
        wb.log({"subgroups": wandb.Table(dataframe=subgroups)})
    wb.summary.update({**flat, "model_uri": model_uri})
    artifact = wandb.Artifact(f"{topic}-model", type="model", metadata=model_card)
    for name in ("model.joblib", "model_card.json", "metrics.json", "run_metadata.yaml", "train.log", "calibration.png"):
        artifact.add_file(str(run_dir / name))
    wb.log_artifact(artifact)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", required=True)
    parser.add_argument("--final", action="store_true", help="refit on train+validation and score the test set")
    parser.add_argument("--data-uri", help="read clean data from this URI or local file instead of data.clean_uri")
    parser.add_argument("--allow-unverified", action="store_true", help="accept data before a hash is recorded")
    parser.add_argument("--no-upload", action="store_true", help="do not copy the model to the bucket")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_dir = run(args.topic, args.final, args.data_uri, args.allow_unverified, upload=not args.no_upload)
    print(f"Run folder: {run_dir}")


if __name__ == "__main__":
    main()
