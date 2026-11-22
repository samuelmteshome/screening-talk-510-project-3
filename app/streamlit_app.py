"""Screening Talk front end.

Flow: intake form -> animated body map (click an organ or search) -> organ flowchart
(Medications / Screening -> each option we have data for) -> option page
with the model's prediction (from the live API) next to the trial evidence.
State lives in the URL query string, so organ links and the back button work.

Run locally:  streamlit run app/streamlit_app.py
Set API_URL (env var or Streamlit secret) to the Cloud Run URL to show predictions.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent))
import body_map  # noqa: E402
import flowchart  # noqa: E402
import heart_actions as ha  # noqa: E402
from catalog import (  # noqa: E402
    HISTORY_QUESTIONS, TOPICS, chart_rows, eligibility, load_evidence, number_rows, topics_for,
)

TITLE = "Understand the Impact of Preventative Care"
SUBTITLE = "Find out how a screening or medication would change your own chances."
RACE_OPTIONS = {
    "Prefer not to say": None,
    "Non-Hispanic White": "non_hispanic_white",
    "Non-Hispanic Black": "non_hispanic_black",
    "Mexican American": "mexican_american",
    "Other Hispanic": "other_hispanic",
    "Other or multiracial": "other",
}
# Optional answers the heart model will use once it is trained.
HEART_FIELDS = ("total_chol", "hdl", "sbp", "on_bp_meds", "diabetes", "current_smoker")

st.set_page_config(page_title="Screening Talk", page_icon="🩺", layout="centered")
st.markdown("""<style>
h1 { font-size: 2.1rem !important; line-height: 1.2 !important; letter-spacing: -0.01em; }
.stButton button[kind="tertiary"] { justify-content:flex-start; padding:.15rem .5rem; color:#0f172a; }
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
    """Answers from the intake form, kept in the URL."""
    return {k: v for k, v in qp.to_dict().items() if k not in ("organ", "action")}


# ---------- Step 1: intake ----------
def intake() -> None:
    st.title(TITLE)
    st.caption(SUBTITLE)
    st.write("Answer a few questions. Nothing you enter is stored.")
    with st.form("intake"):
        sex = st.radio("Are you a man or a woman?", ["Man", "Woman"], horizontal=True)
        age = st.number_input("Age", min_value=18, max_value=100, value=56, step=1)
        bmi = st.number_input("BMI (body mass index)", min_value=12.0, max_value=70.0, value=27.0, step=0.1)
        race = st.selectbox("Race / ethnicity", list(RACE_OPTIONS))
        st.markdown("**Have you ever been told by a doctor that you had any of these?**")
        history = {k: st.checkbox(label, key=f"hx_{k}") for k, label in HISTORY_QUESTIONS.items()}
        with st.expander("Heart details (optional, used once the heart model is ready)"):
            chol = st.number_input("Total cholesterol (mg/dL)", min_value=0, max_value=500, value=0,
                                   help="Leave at 0 if you don't know")
            hdl = st.number_input("HDL cholesterol (mg/dL)", min_value=0, max_value=200, value=0)
            sbp = st.number_input("Top blood pressure number (mmHg)", min_value=0, max_value=260, value=0)
            bp_meds = st.checkbox("I take blood pressure medicine")
            diabetes = st.checkbox("I have diabetes")
            smoker = st.checkbox("I currently smoke")
        if st.form_submit_button("See what's available for me", type="primary"):
            answers = {
                "sex": "male" if sex == "Man" else "female",
                "age": int(age),
                "bmi": round(float(bmi), 1),
            }
            if RACE_OPTIONS[race]:
                answers["race_eth"] = RACE_OPTIONS[race]
            heart = {"total_chol": chol, "hdl": hdl, "sbp": sbp,
                     "on_bp_meds": int(bp_meds), "diabetes": int(diabetes), "current_smoker": int(smoker)}
            answers.update({k: v for k, v in heart.items() if v})
            answers.update({k: 1 for k, yes in history.items() if yes})
            qp.from_dict({k: str(v) for k, v in answers.items()})
            st.rerun()


# ---------- Step 2: body map ----------
def body_page(sex: str, age: int) -> None:
    st.markdown('<p class="eyebrow">Screening Talk</p>', unsafe_allow_html=True)
    st.title(TITLE)
    st.caption(SUBTITLE)
    who = "man" if sex == "male" else "woman"
    st.caption(f"Showing results for a {age}-year-old {who}. Tap an organ, or search.")
    search_box(sex, "body")
    topics = topics_for(sex)
    off = frozenset(t.id for t in topics if not eligibility(t, age, history())[0])
    components.html(body_map.render(sex, topics, profile(), off), height=760)
    if off:
        st.caption("Grey organs are outside the groups our data covers for you. Click one to see why.")

    cols = st.columns(len(topics))
    for col, t in zip(cols, topics):
        with col:
            if st.button(f"{t.organ}: {t.tool}", key=f"btn_{t.id}", use_container_width=True):
                qp["organ"] = t.id
                st.rerun()

    if st.button("Start over"):
        qp.clear()
        st.rerun()


def go(m: flowchart.Match) -> None:
    for k in ("branch", "action"):
        if k in qp:
            del qp[k]
    qp["organ"] = m.topic
    if m.branch:
        qp["branch"] = m.branch
    if m.action:
        qp["action"] = m.action
    st.rerun()


def search_box(sex: str, key: str) -> None:
    """Type a medicine, test, or organ; matches appear underneath. One clear match opens it directly."""
    q = st.text_input("Search for a medicine, screening test, or organ", key=f"q_{key}",
                      placeholder="e.g. statin, aspirin, PSA, colonoscopy")
    if not q:
        return
    hits = flowchart.search(q, sex)
    if not hits:
        st.caption("No matches yet. Try a medicine name, a test, or an organ.")
        return
    exact = [h for h in hits if h.action and q.strip().lower() in
             (flowchart.find_option(h.topic, h.action).aliases + (h.action,))]
    if len(exact) == 1 and st.session_state.get(f"opened_{key}") != q:
        st.session_state[f"opened_{key}"] = q
        go(exact[0])
    st.caption("Matches")
    for i, h in enumerate(hits[:6]):
        if st.button(h.label, key=f"hit_{key}_{i}", type="tertiary", icon=":material/arrow_forward:"):
            go(h)


# ---------- Step 3: organ flowchart and option page ----------
def prediction(topic_id: str) -> dict | None:
    url = api_url()
    if not url:
        return None
    p = profile()
    body = {"topic": topic_id, "age_years": int(p["age"]), "sex": p["sex"], "bmi_kg_m2": float(p["bmi"])}
    if "race_eth" in p:
        body["race_eth"] = p["race_eth"]
    body.update({k: float(p[k]) for k in HEART_FIELDS if k in p})
    try:
        r = requests.post(f"{url.rstrip('/')}/predict", json=body, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.warning(f"Could not reach the prediction service ({e.__class__.__name__}).")
        return None


def topic_page(topic_id: str, age: int) -> None:
    t = TOPICS[topic_id]
    st.title(t.organ)
    if st.button("← Back to body map"):
        for k in ("organ", "branch", "action"):
            if k in qp:
                del qp[k]
        st.rerun()

    ok, why = eligibility(t, age, history())
    if not ok:
        st.error(why)
        with st.expander("What the research found (for people outside your group)"):
            show_evidence(t)
        return

    branch = qp.get("branch") if qp.get("branch") in flowchart.BRANCHES else None
    option = flowchart.find_option(t.id, qp.get("action"))
    if option:
        branch = option.branch
    html, height = flowchart.render(t.id, dict(qp), branch, option.id if option else None)
    components.html(html, height=height)
    if not option:
        st.caption("Tap Medications or Screening, then pick an option. Or search:")
        search_box(str(profile()["sex"]), "topic")
        return

    result = prediction(t.id) if t.has_model else None
    if t.id == "heart":
        heart_choices(result, option.id)
    else:
        st.header(option.label)
        st.subheader("Your prediction")
        if not t.has_model:
            st.write("No prediction model for this topic. We show what the trial found.")
        elif result and result.get("in_supported_range", True) and result.get("prediction"):
            per_100 = result["prediction"].get("per_100")
            st.metric("Out of 100 people like you", f"about {per_100}")
            if t.id == "prostate":
                st.caption("Chance of a PSA of 4.0 or higher, the level that usually leads to a biopsy. "
                           "This is a test result, not a cancer diagnosis.")
        else:
            st.write("The prediction service isn't connected yet.")
        st.subheader("What the research found")
        show_evidence(t)
    st.divider()
    st.caption("Averages from research studies, not a promise for one person. "
               "Use this to start a conversation with your doctor.")


def heart_choices(result: dict | None, action: str) -> None:
    """Per-action page: what a statin, BP medicine, aspirin, or checkups would change for this person."""
    st.subheader(f"If you {ha.ACTIONS[action][0].lower()}{ha.ACTIONS[action][1:]}")
    pred = (result or {}).get("prediction", {})
    death = pred.get("risk_cv_death_10y")
    event = pred.get("risk_event_10y")
    if death is None and event is None:
        st.info("Your own numbers will appear here once the heart model is connected. "
                "Until then, this section uses an **example person**: 10 in 100 chance of a heart attack "
                "or stroke and 3 in 100 chance of dying from one in the next 10 years.")
        event, death = 0.10, 0.03

    eff = ha.load_effects()[action]
    e = eff["effects"]

    if action == "bp":
        p = profile()
        c1, c2 = st.columns(2)
        current = c1.number_input("Your top blood pressure number now", 100, 220, int(float(p.get("sbp", 145))))
        target = c2.select_slider("Lower it to", options=list(range(110, 165, 5)), value=130)
        if current <= target:
            st.write("Pick a target below your current number.")
            return
        st.caption(f"Lowering by {current - target} points.")
        rrs = {k: ha.bp_rr(v["rr"], current, target) for k, v in e.items()}
    else:
        rrs = {k: v["rr"] for k, v in e.items()}

    if action == "checkups":
        st.markdown("In 11 large trials, people offered regular general checkups **did not live longer** and "
                    "were **not less likely to die of heart disease** than people who weren't. Checkups can still "
                    "catch high blood pressure or cholesterol, which you can then treat with the options above.")
    else:
        for outcome, base in (("event", event), ("cv_death", death)):
            if outcome in rrs and base is not None:
                certain = e[outcome].get("significant", True)
                st.markdown("- " + ha.sentence(ha.compare(base, rrs[outcome], outcome, certain)))
        if "any_death" in rrs:
            any_d = e["any_death"]
            if any_d.get("significant", True):
                st.markdown(f"- Deaths from any cause were about **{ha.pct_change(rrs['any_death'])}** in the studies.")
            else:
                st.markdown("- The studies found **no clear change** in deaths from any cause.")
        if "major_bleeding" in e:
            st.markdown(f"- **Downside:** serious bleeding was about **{ha.pct_change(e['major_bleeding']['rr'])}** "
                        "common (stomach bleeding and, rarely, bleeding in the brain).")
    st.caption(f"Source: [{eff['source']}]({eff['url']}). Results apply to people who have never had a heart "
               "attack or stroke. Numbers not yet checked against the full paper.")


def show_evidence(t) -> None:
    for ev in load_evidence(t):
        st.markdown(f"**[{ev['source']}]({ev['url']})**")
        meta = [ev.get("comparison", "")]
        if ev.get("horizon_years"):
            meta.append(f"followed for {ev['horizon_years']} years")
        st.caption(", ".join(m for m in meta if m))
        bars = chart_rows(ev["_file"], ev)
        if bars:
            st.bar_chart(pd.DataFrame(bars), x="Result", y="Per 1,000", color="Group", stack=False, horizontal=True)
        else:
            for label, value in number_rows(ev):
                st.markdown(f"- {label.capitalize()}: **{value:g}**")
        if ev.get("verified_by") is None:
            st.caption("Numbers not yet checked against the full paper.")


# ---------- Router ----------
p = profile()
if "sex" not in p or "age" not in p:
    intake()
elif qp.get("organ") in TOPICS and p["sex"] in TOPICS[qp["organ"]].sexes:
    topic_page(qp["organ"], int(p["age"]))
else:
    body_page(p["sex"], int(p["age"]))
