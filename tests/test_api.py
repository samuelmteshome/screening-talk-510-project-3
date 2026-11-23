"""API tests on small made-up models (no cloud, no real data)."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.api import main
from src.config import load_config, load_topic

EXAMPLE = json.loads((Path(__file__).parent / "example_request.json").read_text())


def fake_model(features: list[str], cat: list[str]) -> Pipeline:
    rng = np.random.default_rng(0)
    n = 400
    X = pd.DataFrame({f: rng.normal(50, 10, n) for f in features if f not in cat})
    for c in cat:
        X[c] = rng.choice(["male", "female"] if c == "sex" else ["non_hispanic_white", "non_hispanic_black"], n)
    y = (rng.random(n) < 0.1).astype(int)
    num = [f for f in features if f not in cat]
    pre = ColumnTransformer([("num", SimpleImputer(strategy="median"), num),
                             ("cat", Pipeline([("i", SimpleImputer(strategy="most_frequent")),
                                               ("o", OneHotEncoder(handle_unknown="ignore"))]), cat)])
    return Pipeline([("pre", pre), ("lr", LogisticRegression(max_iter=2000))]).fit(X[features], y)


@pytest.fixture()
def client():
    cfg = load_config()
    cfgs = {t: load_topic(t) for t in cfg["serve"]["topics"]}
    heart_feats = cfgs["heart"]["model_features"]
    main.app.state.config = cfg
    main.app.state.topic_cfgs = cfgs
    main.app.state.models = {
        "prostate": main.LoadedModel(fake_model(["age", "race_eth", "bmi"], ["race_eth"]), ["age", "race_eth", "bmi"], "test"),
        "heart": main.LoadedModel(fake_model(heart_feats, ["sex"]), heart_feats, "test", "v1"),
    }
    main.app.state.errors = {}
    with TestClient(main.app) as c:
        yield c
    for k in ("models", "topic_cfgs", "errors", "config"):
        delattr(main.app.state, k)


def test_health_and_topics(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["models_loaded"] == ["heart", "prostate"]
    topics = {t["id"]: t for t in client.get("/topics").json()}
    assert set(topics) == {"prostate", "heart", "colorectal"}
    assert topics["prostate"]["sexes"] == ["male"] and "age_years" in topics["prostate"]["inputs"]
    assert topics["colorectal"]["model_loaded"] is False


def test_predict_example_returns_risk_and_evidence(client):
    r = client.post("/predict", json=EXAMPLE)
    assert r.status_code == 200
    body = r.json()
    assert body["in_supported_range"] and 0 < body["prediction"]["probability"] < 1
    assert body["prediction"]["per_100"] == round(body["prediction"]["probability"] * 100)
    assert {e["file"] for e in body["evidence"]} >= {"erspc_2025.json"}


def test_heart_zero_means_unknown(client):
    body = {"topic": "heart", "age_years": 60, "sex": "female", "bmi_kg_m2": 28,
            "total_chol": 0, "hdl": 0, "sbp": 140, "diabetes": True, "current_smoker": False, "on_bp_meds": False}
    out = client.post("/predict", json=body).json()
    assert out["prediction"]["risk_cv_death_10y"] == out["prediction"]["probability"]
    assert "total_chol" in out["message"] and "hdl" in out["message"]


@pytest.mark.parametrize("change, words", [
    ({"age_years": 30}, "ages 50 to 69"),
    ({"prior_prostate_cancer": True}, "already had prostate cancer"),
    ({"sex": "female"}, "male only"),
])
def test_out_of_range_gives_no_number(client, change, words):
    out = client.post("/predict", json={**EXAMPLE, **change}).json()
    assert out["in_supported_range"] is False and out["prediction"] is None and words in out["message"]
    assert out["evidence"]  # the trial results are still shown


def test_topic_without_model_still_shows_evidence(client):
    lo = client.get("/topics").json()
    age = next(t["age_min"] for t in lo if t["id"] == "colorectal")
    out = client.post("/predict", json={"topic": "colorectal", "age_years": age, "sex": "male"}).json()
    assert out["prediction"] is None and "isn't trained yet" in out["message"]
    assert out["evidence"][0]["file"] == "nordicc_2022.json"


def test_unknown_topic_and_bad_input(client):
    assert client.post("/predict", json={"topic": "lung", "age_years": 60}).status_code == 404
    assert client.post("/predict", json={"topic": "heart", "age_years": 7}).status_code == 422


def test_saved_heart_dict_and_bare_pipeline_both_load(tmp_path, monkeypatch):
    cfg = load_config()
    feats = ["age", "race_eth", "bmi"]
    joblib.dump(fake_model(feats, ["race_eth"]), tmp_path / "p.joblib")
    joblib.dump({"model": fake_model(feats, ["race_eth"]), "features": feats, "version": "v9"}, tmp_path / "h.joblib")
    monkeypatch.setenv("MODEL_URI_PROSTATE", str(tmp_path / "p.joblib"))
    m = main.load_model("prostate", load_topic("prostate"), cfg)
    assert m.features == feats and 0 < m.predict({"age": 60, "race_eth": "non_hispanic_white", "bmi": 27}) < 1
    monkeypatch.setenv("MODEL_URI_PROSTATE", str(tmp_path / "h.joblib"))
    assert main.load_model("prostate", load_topic("prostate"), cfg).version == "v9"
