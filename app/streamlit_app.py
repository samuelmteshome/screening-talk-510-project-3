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
from catalog import HISTORY_QUESTIONS, TOPICS, eligibility, topics_for  # noqa: E402

TITLE = "Understand the Impact of Preventative Care"
SUBTITLE = "Find out how a screening or medication would change your own chances."
RACE_OPTIONS = {
    "Non-Hispanic White": "non_hispanic_white",
    "Non-Hispanic Black": "non_hispanic_black",
    "Mexican American": "mexican_american",
    "Other Hispanic": "other_hispanic",
    "Other or multiracial": "other_or_multiracial",
    "Prefer not to say": None,
}
# Optional answers the heart numbers use.
HEART_FIELDS = ("total_chol", "hdl", "sbp", "on_bp_meds", "diabetes", "current_smoker")
VIEW_KEYS = ("organ", "branch", "action")

st.set_page_config(page_title="Screening Talk", page_icon="🩺", layout="wide")
st.markdown("""<style>
h1 { font-size: 2.1rem !important; line-height: 1.2 !important; letter-spacing: -0.01em; }
.eyebrow { color:#e11d48; font-weight:700; letter-spacing:.08em; text-transform:uppercase; font-size:.8rem; margin-bottom:-.6rem; }
div[data-testid="stMarkdownContainer"] p.q { font-size:1.75rem; font-weight:700; line-height:1.25; margin:1rem 0 .1rem; }
div[data-testid="stMarkdownContainer"] p.qhelp { color:#64748b; font-size:1.05rem; margin-bottom:.6rem; }
div[data-testid="stButton"] button p { font-size:1.05rem; }
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


# ---------- Step 1: intake, one question at a time ----------
# Each step: (key, question, help, kind, extra). kind: choice | number | yesno | history
STEPS = [
    ("sex", "Are you a man or a woman?", "Some screening tests are only for men or only for women.",
     "choice", {"Man": "male", "Woman": "female"}),
    ("age", "How old are you?", "", "number", dict(min_value=18, max_value=100, value=56, step=1)),
    ("bmi", "What is your BMI (body mass index)?", "Not sure? Enter your height and weight instead.",
     "bmi", {}),
    ("race_eth", "Which best describes you?", "The data our model learned from differs by group.",
     "choice", RACE_OPTIONS),
    ("history", "Has a doctor ever told you that you had any of these?", "Pick all that apply.", "history", {}),
    ("family_crc", "Has a parent, brother, sister, or child had colorectal (colon) cancer?", "", "yesno", {}),
    ("ever_smoked", "Have you ever smoked regularly?", "At least 100 cigarettes in your life.", "yesno", {}),
    ("current_smoker", "Do you smoke now?", "", "yesno", {}),
    ("diabetes", "Do you have diabetes?", "", "yesno", {}),
    ("on_bp_meds", "Do you take blood pressure medicine?", "", "yesno", {}),
    ("sbp", "What is your top blood pressure number?", "The first number, e.g. the 130 in 130/80. Skip if you don't know.",
     "number", dict(min_value=70, max_value=260, value=130, step=1)),
    ("total_chol", "What is your total cholesterol?", "In mg/dL, from a recent blood test. Skip if you don't know.",
     "number", dict(min_value=80, max_value=500, value=200, step=1)),
    ("hdl", "What is your HDL (\"good\") cholesterol?", "In mg/dL. Skip if you don't know.",
     "number", dict(min_value=10, max_value=200, value=50, step=1)),
]
REQUIRED = {"sex", "age"}
FIRST_OPTIONAL = next(i for i, s in enumerate(STEPS) if s[0] == "family_crc")


def answer(key: str, value) -> None:
    st.session_state.answers[key] = value
    st.session_state.step += 1
    st.rerun()


def finish() -> None:
    a = st.session_state.answers
    out = {k: v for k, v in a.items() if v not in (None, 0, False) and k != "history"}
    if "ever_smoked" not in out and a.get("current_smoker"):
        out["ever_smoked"] = 1
    out.update({k: 1 for k in a.get("history", [])})
    qp.from_dict({k: str(int(v) if isinstance(v, bool) else v) for k, v in out.items()})
    for k in ("step", "answers"):
        st.session_state.pop(k, None)
    st.rerun()


def intake() -> None:
    ss = st.session_state
    ss.setdefault("step", 0)
    ss.setdefault("answers", {})
    if ss.step >= len(STEPS):
        finish()
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown('<p class="eyebrow">Screening Talk</p>', unsafe_allow_html=True)
        st.title(TITLE)
        st.caption(SUBTITLE + " Nothing you enter is stored.")
        st.progress((ss.step + 1) / len(STEPS), text=f"Question {ss.step + 1} of {len(STEPS)}")
        key, question, help_, kind, extra = STEPS[ss.step]
        st.markdown(f'<p class="q">{question}</p>', unsafe_allow_html=True)
        if help_:
            st.markdown(f'<p class="qhelp">{help_}</p>', unsafe_allow_html=True)
        prev = ss.answers.get(key)

        if kind == "choice":
            for label, value in extra.items():
                if st.button(label, key=f"{key}_{label}", use_container_width=True,
                             type="primary" if prev == value and prev is not None else "secondary"):
                    answer(key, value)
        elif kind == "yesno":
            c1, c2 = st.columns(2)
            if c1.button("Yes", use_container_width=True, type="primary" if prev is True else "secondary"):
                answer(key, True)
            if c2.button("No", use_container_width=True, type="primary" if prev is False else "secondary"):
                answer(key, False)
        elif kind == "number":
            v = st.number_input(question, label_visibility="collapsed", key=f"in_{key}",
                                **{**extra, "value": prev if prev else extra["value"]})
            c1, c2 = st.columns(2)
            if c1.button("Next", type="primary", use_container_width=True):
                answer(key, int(v))
            if key not in REQUIRED and c2.button("Skip", use_container_width=True):
                answer(key, None)
        elif kind == "bmi":
            v = st.number_input("BMI", label_visibility="collapsed", min_value=12.0, max_value=70.0,
                                value=float(prev or 27.0), step=0.1, key="in_bmi")
            with st.expander("Work it out from height and weight"):
                c1, c2 = st.columns(2)
                ft = c1.number_input("Height (feet)", 3, 7, 5)
                inch = c1.number_input("and inches", 0, 11, 8)
                lb = c2.number_input("Weight (pounds)", 60, 600, 170)
                calc = round(703 * lb / (ft * 12 + inch) ** 2, 1)
                st.write(f"Your BMI is about **{calc}**.")
                if st.button("Use this BMI"):
                    answer("bmi", calc)
            c1, c2 = st.columns(2)
            if c1.button("Next", type="primary", use_container_width=True):
                answer("bmi", round(float(v), 1))
            if c2.button("Skip", use_container_width=True):
                answer("bmi", None)
        elif kind == "history":
            picked = [k for k, label in HISTORY_QUESTIONS.items()
                      if st.checkbox(label, value=k in (prev or []), key=f"hx_{k}")]
            c1, c2 = st.columns(2)
            if c1.button("Next", type="primary", use_container_width=True):
                answer("history", picked)
            if c2.button("None of these", use_container_width=True):
                answer("history", [])

        c1, c2 = st.columns(2)
        if ss.step > 0 and c1.button("← Back", type="tertiary"):
            ss.step -= 1
            st.rerun()
        if ss.step >= FIRST_OPTIONAL and c2.button("Skip the rest and see my options →", type="tertiary"):
            finish()


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
    return out


def editable(p: dict) -> dict:
    """URL answers back into the intake's types, so Edit starts from what was entered."""
    kinds = {s[0]: s[3] for s in STEPS}
    out = {"history": sorted(history())}
    for k, kind in kinds.items():
        if kind == "yesno":
            out[k] = p.get(k) == "1"
        elif k in p and kind in ("number", "bmi"):
            out[k] = float(p[k]) if k == "bmi" else int(float(p[k]))
        elif k in p:
            out[k] = p[k]
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
            st.session_state.answers = editable(p)
            st.session_state.step = 0
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
    intake()
else:
    explore_page(p)
