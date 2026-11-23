"""Build the model pipeline and the age-group baseline from a topic config.

The preprocessing lives inside one scikit-learn Pipeline with the model, so the
API applies exactly the same transforms as training.

Feature types come from ``feature_types`` in topics/<topic>.yaml:
``spline`` (age, with ``model_params.age_spline_knots``), ``numeric`` or
``categorical``. A feature without a type is treated as categorical if its
column holds text, numeric otherwise. Missing values are imputed in the pipeline.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler


def feature_types(topic_cfg: dict[str, Any], df: pd.DataFrame | None = None) -> dict[str, str]:
    """Type of each feature: from the config, else inferred from the column dtype."""
    declared = topic_cfg.get("feature_types") or {}
    types = {}
    for feature in topic_cfg["features"]:
        if feature in declared:
            types[feature] = declared[feature]
        elif df is not None and not pd.api.types.is_numeric_dtype(df[feature]):
            types[feature] = "categorical"
        else:
            types[feature] = "numeric"
    return types


def build_preprocessor(topic_cfg: dict[str, Any], df: pd.DataFrame | None = None) -> ColumnTransformer:
    """ColumnTransformer for the topic's features."""
    params = topic_cfg.get("model_params") or {}
    steps = {
        "spline": lambda: Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("spline", SplineTransformer(n_knots=params.get("age_spline_knots", 3), degree=3)),
            ]
        ),
        "numeric": lambda: Pipeline(
            [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
        ),
        "categorical": lambda: Pipeline(
            [
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]
        ),
    }
    transformers = []
    for feature, kind in feature_types(topic_cfg, df).items():
        if kind not in steps:
            raise ValueError(f"Unknown feature type '{kind}' for '{feature}'")
        transformers.append((feature, steps[kind](), [feature]))
    return ColumnTransformer(transformers)


def build_model(topic_cfg: dict[str, Any], C: float, seed: int, df: pd.DataFrame | None = None) -> Pipeline:
    """Preprocessing + logistic regression in one Pipeline."""
    return Pipeline(
        [
            ("preprocess", build_preprocessor(topic_cfg, df)),
            ("model", LogisticRegression(C=C, max_iter=2000, random_state=seed)),
        ]
    )


class AgeGroupBaseline(BaseEstimator, ClassifierMixin):
    """Predicts the training rate of the outcome in each age band.

    The comparison the model has to beat: "men your age" with no other inputs.
    """

    def __init__(self, column: str = "age", width: int = 5):
        self.column = column
        self.width = width

    def _band(self, X: pd.DataFrame) -> np.ndarray:
        return (np.floor(X[self.column].to_numpy(dtype=float) / self.width) * self.width).astype(int)

    def fit(self, X: pd.DataFrame, y, sample_weight=None):
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        frame = pd.DataFrame({"band": self._band(X), "y": np.asarray(y) * w, "w": w})
        sums = frame.groupby("band")[["y", "w"]].sum()
        self.rates_ = (sums["y"] / sums["w"]).to_dict()
        self.overall_ = float(frame["y"].sum() / frame["w"].sum())
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        p = np.array([self.rates_.get(b, self.overall_) for b in self._band(X)])
        return np.column_stack([1 - p, p])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
