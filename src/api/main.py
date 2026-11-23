"""Prediction API: the model's risk for one person, next to the published trial results.

Run locally:
    uvicorn src.api.main:app --reload
Endpoints:
    GET  /health   which models are loaded
    GET  /topics   what each topic covers and which inputs it uses
    POST /predict  risk for one person plus the trial evidence (see tests/example_request.json)

Where models come from, per topic (first match wins):
    MODEL_URI_<TOPIC> env var, a gs:// URI or a local path (e.g. MODEL_URI_HEART=gs://bucket/models/abc/model.joblib)
    models/<topic>/model.joblib in the image or repo
A topic without a model still answers with the trial evidence and says no number is available.
"""
from __future__ import annotations

import logging
import os
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException

from src.api import evidence
from src.api.schemas import Prediction, PredictRequest, PredictResponse, TopicInfo
from src.config import REPO_ROOT, load_config, load_topic, resolve_uri

log = logging.getLogger(__name__)

# What each topic's number means, who it applies to, and which history answer rules a person out.
TOPICS: dict[str, dict[str, Any]] = {
    "prostate": {
        "sexes": ["male"],
        "outcome": "a PSA of 4.0 or higher, the level that usually leads to a biopsy (a test result, not a cancer diagnosis)",
        "excluded_by": "prior_prostate_cancer",
        "excluded_reason": "The data left out men who already had prostate cancer, so it can't give you a number.",
    },
    "heart": {
        "sexes": ["male", "female"],
        "outcome": "dying of heart disease or stroke in the next 10 years",
        "excluded_by": "prior_cvd",
        "excluded_reason": "The data left out people who already had a heart attack, stroke, angina or heart failure.",
    },
    "colorectal": {
        "sexes": ["male", "female"],
        "outcome": "having had colon or rectal cancer (how common it is in people like you, not a forecast)",
        "excluded_by": "prior_crc",
        "excluded_reason": "This is about people who have not had colorectal cancer.",
    },
}
# Request field for each model column, where the names differ.
REQUEST_FIELD = {"age": "age_years", "bmi": "bmi_kg_m2"}


@dataclass
class LoadedModel:
    pipeline: Any
    features: list[str]
    source: str
    version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def predict(self, row: dict[str, Any]) -> float:
        row = {f: row.get(f, np.nan) for f in self.features}
        for f, typical in typical_values(self.pipeline).items():
            if f in row and (row[f] is None or (isinstance(row[f], float) and np.isnan(row[f]))):
                row[f] = typical
        X = pd.DataFrame([row])
        return float(self.pipeline.predict_proba(X)[:, 1][0])


def typical_values(pipeline: Any) -> dict[str, Any]:
    """Training medians for numeric features whose imputer also adds a "was missing" flag.

    In NHANES a missing exam value marks people who are often sicker, so the flag carries risk.
    Someone who skips a question in the app is not that person: give them the typical value
    with the flag off instead of letting the imputer raise their risk.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer

    out: dict[str, Any] = {}
    steps = getattr(pipeline, "named_steps", {}) or {}
    for step in steps.values():
        if not isinstance(step, ColumnTransformer):
            continue
        for _, trans, cols in step.transformers_:
            imputers = [trans] if isinstance(trans, SimpleImputer) else list(getattr(trans, "named_steps", {}).values())
            for imp in imputers:
                if isinstance(imp, SimpleImputer) and imp.add_indicator and hasattr(imp, "statistics_"):
                    out.update(dict(zip(cols, imp.statistics_)))
    return out


def model_source(topic: str) -> str | None:
    env = os.getenv(f"MODEL_URI_{topic.upper()}")
    if env:
        return env
    local = REPO_ROOT / "models" / topic / "model.joblib"
    return str(local) if local.exists() else None


def load_model(topic: str, topic_cfg: dict[str, Any], config: dict[str, Any]) -> LoadedModel | None:
    """Model for a topic, or None when there isn't one yet."""
    source = model_source(topic)
    if not source:
        return None
    path = Path(source)
    if source.startswith("gs://"):
        from src.data import storage

        path = storage.get(resolve_uri(source, config), Path(tempfile.mkdtemp()) / "model.joblib")
    obj = joblib.load(path)
    if isinstance(obj, dict):  # heart: {"model", "features", "version", ...}
        return LoadedModel(obj["model"], list(obj["features"]), source, obj.get("version"),
                           {k: v for k, v in obj.items() if k not in ("model", "features")})
    features = topic_cfg.get("model_features") or topic_cfg["features"]  # shared trainer: a bare Pipeline
    return LoadedModel(obj, list(features), source, (topic_cfg.get("data") or {}).get("version"))


def load_all(config: dict[str, Any]) -> tuple[dict[str, dict], dict[str, LoadedModel], dict[str, str]]:
    cfgs, models, errors = {}, {}, {}
    for topic in config["serve"]["topics"]:
        cfgs[topic] = load_topic(topic)
        try:
            m = load_model(topic, cfgs[topic], config)
            if m:
                models[topic] = m
                log.info("Loaded %s model from %s", topic, m.source)
            else:
                log.warning("No model for %s yet: serving evidence only", topic)
        except Exception as e:  # keep serving the other topics
            errors[topic] = f"{e.__class__.__name__}: {e}"
            log.exception("Could not load the %s model", topic)
    return cfgs, models, errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "models"):  # tests can set these before startup
        app.state.config = load_config()
        app.state.topic_cfgs, app.state.models, app.state.errors = load_all(app.state.config)
    yield


app = FastAPI(title="Screening Talk API", version="1.0",
              description="Model risk next to published trial results. Educational, not medical advice.",
              lifespan=lifespan)


def age_range(topic_cfg: dict[str, Any]) -> tuple[int, int]:
    """Ages the model was trained on; for evidence-only topics, the ages the trial covered."""
    d = topic_cfg.get("data") or {}
    if "age_min" in d:
        return int(d["age_min"]), int(d["age_max"])
    s = topic_cfg.get("serve") or {}
    return int(s["display_age_min"]), int(s["display_age_max"])


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "models_loaded": sorted(app.state.models),
            "topics": sorted(app.state.topic_cfgs), "errors": app.state.errors}


@app.get("/topics", response_model=list[TopicInfo])
def topics() -> list[TopicInfo]:
    out = []
    for topic, cfg in app.state.topic_cfgs.items():
        lo, hi = age_range(cfg)
        m = app.state.models.get(topic)
        feats = m.features if m else (cfg.get("model_features") or cfg.get("features") or [])
        out.append(TopicInfo(id=topic, age_min=lo, age_max=hi, sexes=TOPICS[topic]["sexes"],
                             inputs=[REQUEST_FIELD.get(f, f) for f in feats], model_loaded=m is not None,
                             outcome=TOPICS[topic]["outcome"], evidence_files=list(evidence.FILES.get(topic, ()))))
    return out


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    topic = req.topic
    if topic not in app.state.topic_cfgs:
        raise HTTPException(404, f"Unknown topic '{topic}'. Try GET /topics.")
    info, cfg = TOPICS[topic], app.state.topic_cfgs[topic]
    base = dict(topic=topic, evidence=list(evidence.load(topic)))
    lo, hi = age_range(cfg)

    if getattr(req, info["excluded_by"]):
        return PredictResponse(**base, in_supported_range=False, message=info["excluded_reason"])
    if req.sex and req.sex not in info["sexes"]:
        return PredictResponse(**base, in_supported_range=False, message=f"This topic is for {' and '.join(info['sexes'])} only.")
    if not lo <= req.age_years <= hi:
        return PredictResponse(**base, in_supported_range=False,
                               message=f"The data covers ages {lo} to {hi}, so there is no number for age {req.age_years}.")
    model = app.state.models.get(topic)
    if model is None:
        return PredictResponse(**base, in_supported_range=True,
                               message="The model for this topic isn't trained yet. Showing the trial results only.")

    answers = req.model_dump()
    row = {f: answers.get(REQUEST_FIELD.get(f, f)) for f in model.features}
    row = {k: (np.nan if v is None else float(v) if isinstance(v, bool) else v) for k, v in row.items()}
    p = model.predict(row)
    pred = Prediction(outcome=info["outcome"], probability=round(p, 4), per_100=int(round(p * 100)),
                      per_1000=int(round(p * 1000)), risk_cv_death_10y=round(p, 4) if topic == "heart" else None)
    unknown = [REQUEST_FIELD.get(k, k) for k, v in row.items() if isinstance(v, float) and np.isnan(v)]
    msg = f"Typical values were used for: {', '.join(unknown)}." if unknown else ""
    return PredictResponse(**base, in_supported_range=True, message=msg, prediction=pred,
                           model={"source": model.source, "version": model.version, "features": model.features})
