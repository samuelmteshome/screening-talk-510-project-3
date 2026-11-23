"""Tests for features.py, evaluate.py and train.py on made-up clean data."""
import json

import joblib
import numpy as np
import pandas as pd
import pytest
import yaml

from src import evaluate
from src.features import AgeGroupBaseline, build_model, feature_types
from src.train import run, split_by_cycle

CYCLES = ["2001-2002", "2003-2004", "2005-2006", "2007-2008", "2009-2010"]
RACES = ["mexican_american", "other_hispanic", "non_hispanic_white", "non_hispanic_black", "other_or_multiracial"]


@pytest.fixture
def clean_file(tmp_path):
    """A clean parquet in the data-contract format, with risk rising with age."""
    rng = np.random.default_rng(0)
    n = 1000
    age = rng.integers(50, 70, n)
    risk = 1 / (1 + np.exp(-(-4.5 + 0.12 * (age - 50))))
    df = pd.DataFrame(
        {
            "SEQN": np.arange(n),
            "cycle": rng.choice(CYCLES, n),
            "target": (rng.random(n) < risk).astype("int64"),
            "exam_weight": rng.uniform(5_000, 60_000, n),
            "age": age.astype(float),
            "race_eth": rng.choice(RACES, n),
            "bmi": rng.normal(28, 5, n),
        }
    )
    df.loc[:9, "bmi"] = np.nan
    path = tmp_path / "clean.parquet"
    df.to_parquet(path, index=False)
    return path


def test_feature_types_and_pipeline_handle_missing_values(prostate_cfg):
    assert feature_types(prostate_cfg) == {"age": "spline", "race_eth": "categorical", "bmi": "numeric"}
    X = pd.DataFrame({"age": [55.0, 60.0, 65.0, 68.0], "race_eth": RACES[:4], "bmi": [27.0, np.nan, 31.0, 24.0]})
    model = build_model(prostate_cfg, C=1.0, seed=1).fit(X, [0, 0, 1, 1])
    p = model.predict_proba(pd.DataFrame({"age": [56.0], "race_eth": ["unknown_group"], "bmi": [np.nan]}))
    assert 0 < p[0, 1] < 1


def test_age_group_baseline_uses_band_rates():
    X = pd.DataFrame({"age": [50, 52, 60, 61]})
    baseline = AgeGroupBaseline().fit(X, [0, 1, 1, 1])
    assert baseline.predict_proba(pd.DataFrame({"age": [51, 62, 80]}))[:, 1].tolist() == [0.5, 1.0, 0.75]


def test_metrics_and_calibration_table():
    y = np.array([0, 0, 1, 1, 0, 1, 0, 0, 1, 1])
    p = np.linspace(0.05, 0.95, 10)
    m = evaluate.metrics(y, p)
    assert m["n"] == 10 and 0.5 < m["auc"] <= 1 and m["observed_rate"] == 0.5
    table = evaluate.calibration_table(y, p, groups=5)
    assert table["n"].tolist() == [2] * 5
    assert table["predicted"].is_monotonic_increasing
    assert evaluate.brier_skill(0.08, 0.1) == pytest.approx(0.2)


def test_split_uses_cycles(clean_file, prostate_cfg):
    parts = split_by_cycle(pd.read_parquet(clean_file), prostate_cfg["split"])
    assert set(parts["test"]["cycle"]) == {"2009-2010"}
    assert set(parts["val"]["cycle"]) == {"2007-2008"}


def test_train_writes_model_and_metadata(tmp_path, config, prostate_cfg, clean_file):
    run_dir = run("prostate", data_uri=str(clean_file), allow_unverified=True, upload=False,
                  runs_dir=tmp_path / "runs", config=config, topic_cfg=prostate_cfg)
    for name in ["model.joblib", "model_card.json", "metrics.json", "run_metadata.yaml", "train.log", "calibration.png"]:
        assert (run_dir / name).exists(), name

    metadata = yaml.safe_load((run_dir / "run_metadata.yaml").read_text())
    assert metadata["seed"] == 510
    assert {"commit", "dirty"} <= set(metadata["git"])
    assert metadata["packages"]["scikit-learn"]
    assert len(metadata["data"]["sha256"]) == 64

    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["split"] == "val"
    assert metrics["selected_C"] in prostate_cfg["model_params"]["C_grid"]

    model = joblib.load(run_dir / "model.joblib")  # what the API will load
    request = pd.DataFrame({"age": [56.0], "race_eth": ["non_hispanic_white"], "bmi": [27.5]})
    assert 0 < model.predict_proba(request)[0, 1] < 1


def test_train_logs_the_run_to_mlflow(tmp_path, config, prostate_cfg, clean_file):
    from mlflow.tracking import MlflowClient

    run_dir = run("prostate", data_uri=str(clean_file), allow_unverified=True, upload=False,
                  runs_dir=tmp_path / "runs", config=config, topic_cfg=prostate_cfg)
    client = MlflowClient()
    logged = client.get_run(run_dir.name)
    assert logged.info.status == "FINISHED"
    assert logged.info.run_name == "prostate-validation"
    assert logged.data.params["topic"] == "prostate"
    assert len(logged.data.params["data_sha256"]) == 64
    assert 0 <= logged.data.metrics["val/auc"] <= 1
    files = {f.path for f in client.list_artifacts(run_dir.name)}
    assert {"model.joblib", "model_card.json", "metrics.json", "run_metadata.yaml", "train.log", "calibration.png"} <= files
    assert {f.path for f in client.list_artifacts(run_dir.name, "tables")} >= {"tables/calibration.json"}


def test_failed_run_is_marked_failed(tmp_path, config, prostate_cfg, clean_file):
    from mlflow.tracking import MlflowClient

    with pytest.raises(Exception):
        run("prostate", data_uri=str(clean_file), upload=False, runs_dir=tmp_path / "runs",
            config=config, topic_cfg=prostate_cfg)  # no recorded hash, so ingest refuses the data
    runs = MlflowClient().search_runs([MlflowClient().get_experiment_by_name("screening-talk").experiment_id])
    assert runs[0].info.status == "FAILED"


def test_final_run_scores_test_set(tmp_path, config, prostate_cfg, clean_file):
    run_dir = run("prostate", final=True, data_uri=str(clean_file), allow_unverified=True, upload=False,
                  runs_dir=tmp_path / "runs", config=config, topic_cfg=prostate_cfg)
    card = json.loads((run_dir / "model_card.json").read_text())
    assert card["evaluated_on"] == "test"
    assert card["trained_on_cycles"] == CYCLES[:4]


def test_train_refuses_unverified_data_by_default(tmp_path, config, prostate_cfg, clean_file):
    from src.data.ingest import DataIntegrityError

    with pytest.raises(DataIntegrityError):
        run("prostate", data_uri=str(clean_file), upload=False, runs_dir=tmp_path / "runs",
            config=config, topic_cfg=prostate_cfg)
