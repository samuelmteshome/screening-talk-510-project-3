"""Experiment tracking with MLflow, shared by every training script.

Each training run becomes one MLflow run with its parameters, metrics and
files (model, model card, metrics, calibration chart, run metadata, log).
By default runs are stored in ``mlflow.db`` (SQLite) and their files in
``mlruns/`` at the repo root; set MLFLOW_TRACKING_URI to use another store.

View the runs with:
    mlflow ui --backend-store-uri sqlite:///mlflow.db
"""
from __future__ import annotations

import math
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.config import REPO_ROOT

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def tracking_uri(config: dict[str, Any]) -> str:
    """MLflow store: MLFLOW_TRACKING_URI, else tracking.uri in config.yaml (relative to the repo)."""
    uri = os.environ.get("MLFLOW_TRACKING_URI") or (config.get("tracking") or {}).get("uri") or "sqlite:///mlflow.db"
    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
        uri = f"sqlite:///{REPO_ROOT / uri.removeprefix('sqlite:///')}"
    return uri


def _artifact_root(uri: str) -> str | None:
    """Keep run files next to a SQLite store (``<folder>/mlruns``); a server decides for itself."""
    if uri.startswith("sqlite:///"):
        return (Path(uri.removeprefix("sqlite:///")).parent / "mlruns").as_uri()
    return None


@contextmanager
def run(config: dict[str, Any], run_name: str, tags: dict[str, str]) -> Iterator[Any]:
    """Open an MLflow run; it is marked FAILED if the block raises."""
    import mlflow

    uri = tracking_uri(config)
    mlflow.set_tracking_uri(uri)
    name = (config.get("tracking") or {}).get("experiment") or "screening-talk"
    experiment = mlflow.get_experiment_by_name(name)
    experiment_id = (
        experiment.experiment_id if experiment else mlflow.create_experiment(name, artifact_location=_artifact_root(uri))
    )
    with mlflow.start_run(experiment_id=experiment_id, run_name=run_name, tags=tags) as active:
        yield active


def _param(value: Any) -> str:
    text = ", ".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value)
    return text[:6000]  # MLflow's limit for one parameter value


def log_run(
    params: dict[str, Any],
    metrics: dict[str, float],
    files: Iterable[str | Path] = (),
    folders: Iterable[str | Path] = (),
) -> None:
    """Log parameters, finite numeric metrics, and files to the active run."""
    import mlflow

    mlflow.log_params({key: _param(value) for key, value in params.items()})
    finite = {
        key: float(value)
        for key, value in metrics.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    }
    mlflow.log_metrics(finite)
    for folder in folders:
        mlflow.log_artifacts(str(folder))
    for path in files:
        if Path(path).exists():
            mlflow.log_artifact(str(path))
