"""Request and response shapes for the prediction API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PredictRequest(BaseModel):
    """One person's answers from the intake form. Unknown numbers can be left out (or sent as 0)."""

    model_config = ConfigDict(extra="ignore")

    topic: str = Field(examples=["prostate"])
    age_years: int = Field(ge=18, le=100)
    sex: Literal["male", "female"] | None = None
    race_eth: str | None = None
    bmi_kg_m2: float | None = Field(default=None, ge=10, le=80)
    total_chol: float | None = Field(default=None, ge=0, le=600)
    hdl: float | None = Field(default=None, ge=0, le=250)
    sbp: float | None = Field(default=None, ge=0, le=300)
    on_bp_meds: bool | None = None
    diabetes: bool | None = None
    current_smoker: bool | None = None
    ever_smoked: bool | None = None
    prior_prostate_cancer: bool = False
    prior_cvd: bool = False
    prior_crc: bool = False

    @field_validator("total_chol", "hdl", "sbp", "bmi_kg_m2", mode="before")
    @classmethod
    def zero_means_unknown(cls, v: Any) -> Any:
        # The Streamlit form uses 0 for "I don't know".
        return None if v in (0, 0.0, "0", "") else v


class Prediction(BaseModel):
    outcome: str                      # what the number is the chance of, in plain words
    probability: float                # 0 to 1
    per_100: int                      # people out of 100 like you
    per_1000: int
    risk_cv_death_10y: float | None = None  # heart only, same as probability (name the app uses)


class PredictResponse(BaseModel):
    topic: str
    in_supported_range: bool          # False: outside the people the data covers, so no number
    message: str = ""                 # why there is no number, or a caveat
    prediction: Prediction | None = None
    model: dict[str, Any] | None = None   # source and version of the model used
    evidence: list[dict[str, Any]]    # published trial results, shown side by side with the prediction
    disclaimer: str = "Averages from research, not medical advice. Use this to start a conversation with your doctor."


class TopicInfo(BaseModel):
    id: str
    age_min: int
    age_max: int
    sexes: list[str]
    inputs: list[str]                 # request fields the model uses
    model_loaded: bool
    outcome: str
    evidence_files: list[str]
