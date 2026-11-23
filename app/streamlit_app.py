"""Screening Talk front end.

Flow: a short intake, one question at a time -> one page with the body map and a
flowchart that grows in place (organ -> Medications / Screening -> option -> your
numbers). Clicks inside the flowchart don't reload the page: every number for this
person is worked out up front (app/explorer.py) and the page just reveals it.
Answers live in the URL query string, so a link reopens the same view; ?organ=,
?branch= and ?action= open the chart at that spot.

Run locally:  streamlit run app/streamlit_app.py
Set API_URL (env var or Streamlit secret) to the Cloud Run URL to show model predictions.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explorer  # noqa: E402
import intake  # noqa: E402
from catalog import HISTORY_QUESTIONS, TOPICS, eligibility, topics_for  # noqa: E402

TITLE = "Understand the Impact of Preventative Care"
SUBTITLE = "Find out how a screening or medication would change your own chances."
# Optional answers the heart numbers use.
HEART_FIELDS = ("total_chol", "hdl", "sbp", "on_bp_meds", "diabetes", "current_smoker")
VIEW_KEYS = ("organ", "branch", "action")

st.set_page_config(page_title="Screening Talk", page_icon="🩺", layout="wide")
st.markdown("""<style>
h1 { font-size: 2.1rem !important; line-height: 1.2 !important; letter-spacing: -0.01em; }
.eyebrow { color:#e11d48; font-weight:700; letter-spacing:.08em; text-transform:uppercase; font-size:.8rem; margin-bottom:-.6rem; }
</style>""", unsafe_allow_html=True)
qp = st.query_params


def api_url() -> str | None:
    try:
        url = st.secrets.get("API_URL")
    except Exception:  # no secrets file
        url = None
    return url or os.getenv("API_URL")


def history() -> set[str]:
    return {k for k in HISTORY_QUESTIONS if qp.get(k) == "1"}


def profile() -> dict:
    """Answers from the intake, kept in the URL."""
    return {k: v for k, v in qp.to_dict().items() if k not in VIEW_KEYS}


# ---------- Step 1: welcome, questions one at a time, review (app/intake.py) ----------
def finish(answers: dict) -> None:
    qp.from_dict(intake.to_params(answers))
    for k in ("step", "answers", "editing"):
        st.session_state.pop(k, None)
    st.rerun()


# ---------- Step 2: one page, body map + growing flowchart ----------
@st.cache_data(ttl=600, show_spinner=False)
def prediction(url: str, body: tuple) -> dict | None:
    try:
        r = requests.post(f"{url.rstrip('/')}/predict", json=dict(body), timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def predictions(p: dict, age: int) -> dict[str, dict | None]:
    """Model results for each topic that has a model and covers this person."""
    url, out = api_url(), {}
    if not url:
        return out
    body = {"age_years": age, "sex": p["sex"]}
    if p.get("bmi"):
        body["bmi_kg_m2"] = float(p["bmi"])
    if p.get("race_eth"):
        body["race_eth"] = p["race_eth"]
    body.update({k: float(p[k]) for k in HEART_FIELDS if k in p})
    if p.get("ever_smoked"):
        body["ever_smoked"] = True
    for t in topics_for(p["sex"]):
        if t.has_model and eligibility(t, age, history())[0]:
            out[t.id] = prediction(url, tuple(sorted({**body, "topic": t.id}.items())))
            if t.id == "heart" and out[t.id] and body.get("current_smoker"):
                # Same person as a non-smoker, for the "Quit smoking" option.
                out[t.id] = {**out[t.id], "if_quit": prediction(url, tuple(sorted({**body, "topic": t.id, "current_smoker": 0.0}.items())))}
    return out


def explore_page(p: dict) -> None:
    age = int(float(p["age"]))
    who = "man" if p["sex"] == "male" else "woman"
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown('<p class="eyebrow">Screening Talk</p>', unsafe_allow_html=True)
        st.title(TITLE)
        st.caption(f"Showing results for a {age}-year-old {who}. Tap an organ, then pick what you want to know.")
    with c2:
        st.write("")
        if st.button("Edit my answers", use_container_width=True):
            st.session_state.answers = intake.from_params(p, history())
            st.session_state.step = intake.REVIEW
            st.session_state.editing = True
            qp.clear()
            st.rerun()
    start = {"organ": qp.get("organ"), "branch": qp.get("branch"), "option": qp.get("action")}
    if start["organ"] not in TOPICS:
        start = {}
    api = predictions(p, age)
    components.html(explorer.render(p, history(), api, start), height=1050, scrolling=True)
    if api_url() and any(v is None for v in api.values()):
        st.caption("Could not reach the prediction service, so model numbers are missing for now.")


# ---------- Router ----------
p = profile()
if "sex" not in p or "age" not in p:
    intake.run(finish)
else:
    explore_page(p)
