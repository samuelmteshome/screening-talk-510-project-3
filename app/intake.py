"""The questionnaire: a welcome screen, one question per screen, then a review.

Design choices
- Continuous answers (age, height, weight, blood pressure, cholesterol) are sliders with the
  value shown large, and a plain-language reading under it (e.g. "Normal", "High").
- Ordered choices (smoking) are a dropdown; race is a dropdown too, with "Prefer not to say".
- Two- or three-way answers are big tiles that move on as soon as you tap one.
- Past conditions are tap-to-select chips, with "None of these".
- Heart numbers are optional: each has "I don't know", and the whole section can be skipped.
- A review screen at the end lets you fix any one answer before seeing results.

Answers are kept in st.session_state while answering and written to the URL at the end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import streamlit as st

from catalog import HISTORY_QUESTIONS

WELCOME_TITLE = "Welcome to the Preventative Care Screening Impact Aide"
WELCOME_TEXT = ("Enter your information to learn more about how medications and interventions "
                "will impact your life.")

RACE_OPTIONS = {
    "Non-Hispanic White": "non_hispanic_white",
    "Non-Hispanic Black": "non_hispanic_black",
    "Mexican American": "mexican_american",
    "Other Hispanic": "other_hispanic",
    "Other or multiracial": "other_or_multiracial",
    "Prefer not to say": None,
}
SMOKING = {"I have never smoked": "never", "I used to smoke, but quit": "former", "I smoke now": "current"}
HEIGHTS = [f"{i // 12}′ {i % 12}″" for i in range(54, 85)]   # 4′6″ to 7′0″


@dataclass(frozen=True)
class Step:
    key: str
    section: str
    question: str
    help: str = ""
    kind: str = "tiles"          # tiles | slider | body | dropdown | chips
    options: dict = field(default_factory=dict)
    slider: tuple = ()           # (min, max, default, step, unit)
    reading: Callable[[float, dict], tuple[str, str]] | None = None   # value -> (label, colour)
    optional: bool = False


def bmi_reading(b: float, _: dict) -> tuple[str, str]:
    if b < 18.5:
        return "Underweight", "#0284c7"
    if b < 25:
        return "Healthy weight", "#16a34a"
    if b < 30:
        return "Overweight", "#d97706"
    return "Obese range", "#dc2626"


def bp_reading(v: float, _: dict) -> tuple[str, str]:
    if v < 120:
        return "Normal", "#16a34a"
    if v < 130:
        return "Elevated", "#d97706"
    if v < 140:
        return "High (stage 1)", "#ea580c"
    return "High (stage 2)", "#dc2626"


def chol_reading(v: float, _: dict) -> tuple[str, str]:
    if v < 200:
        return "Desirable", "#16a34a"
    if v < 240:
        return "Borderline high", "#d97706"
    return "High", "#dc2626"


def hdl_reading(v: float, a: dict) -> tuple[str, str]:
    low = 40 if a.get("sex") == "male" else 50
    if v < low:
        return "Low (higher risk)", "#dc2626"
    if v >= 60:
        return "Good (protective)", "#16a34a"
    return "OK", "#d97706"


YES_NO = {"Yes": True, "No": False}
YES_NO_UNSURE = {"Yes": True, "No": False, "Not sure": None}

STEPS = [
    Step("sex", "About you", "Are you a man or a woman?", "Some screening tests are only for men or only for women.",
         options={"Man": "male", "Woman": "female"}),
    Step("age", "About you", "How old are you?", "Screening advice changes with age.",
         kind="slider", slider=(18, 100, 55, 1, "years old")),
    Step("bmi", "About you", "How tall are you, and how much do you weigh?",
         "We use these to work out your BMI (body mass index).", kind="body"),
    Step("race_eth", "About you", "Which best describes you?",
         "The health surveys our numbers come from report results by group.", kind="dropdown", options=RACE_OPTIONS),
    Step("history", "Your health", "Has a doctor ever told you that you had any of these?",
         "Tap all that apply. If you have, some numbers won't apply to you, and we'll say why.", kind="chips"),
    Step("family_crc", "Your health", "Has a parent, brother, sister, or child had colon or rectal cancer?",
         "This raises your own chance of colon cancer.", options=YES_NO_UNSURE),
    Step("smoking", "Your health", "Do you smoke?", "Smoking raises the chance of heart disease and colon cancer.",
         kind="dropdown", options=SMOKING),
    Step("diabetes", "Your health", "Has a doctor told you that you have diabetes?", options=YES_NO_UNSURE),
    Step("on_bp_meds", "Heart numbers", "Do you take medicine for high blood pressure?",
         "The next few questions are optional. They make your heart numbers more accurate.", options=YES_NO,
         optional=True),
    Step("sbp", "Heart numbers", "What is your top blood pressure number?",
         "The first number from your last reading, like the 130 in 130/80.", kind="slider",
         slider=(90, 200, 125, 1, "mmHg"), reading=bp_reading, optional=True),
    Step("total_chol", "Heart numbers", "What is your total cholesterol?", "From a recent blood test.",
         kind="slider", slider=(100, 350, 190, 1, "mg/dL"), reading=chol_reading, optional=True),
    Step("hdl", "Heart numbers", "What is your HDL (“good”) cholesterol?", "From the same blood test.",
         kind="slider", slider=(20, 110, 50, 1, "mg/dL"), reading=hdl_reading, optional=True),
]
FIRST_OPTIONAL = next(i for i, s in enumerate(STEPS) if s.optional)
REVIEW = len(STEPS)

CSS = """<style>
.welcome { text-align:center; padding: 3.5rem 0 1rem; }
.welcome .badge { display:inline-block; font-size:2.6rem; width:84px; height:84px; line-height:84px; border-radius:50%;
  background:linear-gradient(135deg,#ffe4e6,#e0f2fe); margin-bottom:1rem; }
.welcome h1 { font-size:2.4rem !important; line-height:1.15 !important; margin-bottom:.6rem; }
.welcome .lead { font-size:1.2rem; color:#475569; max-width:34rem; margin:0 auto 1.4rem; line-height:1.5; }
.facts { display:flex; justify-content:center; gap:.6rem; flex-wrap:wrap; margin:0 0 1.6rem; }
.facts span { background:#f1f5f9; color:#334155; border-radius:999px; padding:.35rem .9rem; font-size:.92rem; }
.fine { text-align:center; color:#94a3b8; font-size:.85rem; margin-top:1rem; }
.section { color:#e11d48; font-weight:700; letter-spacing:.08em; text-transform:uppercase; font-size:.78rem; margin:0; }
div[data-testid="stMarkdownContainer"] p.q { font-size:1.85rem; font-weight:700; line-height:1.22; margin:.2rem 0 .25rem; }
div[data-testid="stMarkdownContainer"] p.qhelp { color:#64748b; font-size:1.05rem; margin:0 0 1rem; }
.big { font-size:3rem; font-weight:800; line-height:1; margin:.6rem 0 .1rem; color:#0f172a; }
.big small { font-size:1.1rem; font-weight:500; color:#64748b; margin-left:.4rem; }
.chip { display:inline-block; border-radius:999px; padding:.2rem .75rem; font-size:.9rem; font-weight:600; color:#fff; margin-bottom:.4rem; }
.steps { height:6px; background:#f1f5f9; border-radius:999px; overflow:hidden; margin:.2rem 0 1.6rem; }
.steps div { height:100%; background:linear-gradient(90deg,#e11d48,#f97316); border-radius:999px; transition:width .4s; }
.count { color:#94a3b8; font-size:.85rem; float:right; }
div[data-testid="stButton"] button { min-height:3rem; border-radius:12px; }
div[data-testid="stButton"] button p { font-size:1.08rem; }
button[data-testid="stBaseButton-tertiary"] { min-height:0 !important; padding:.1rem .3rem; }
button[data-testid="stBaseButton-tertiary"] p { color:#2563eb; font-size:1rem !important; }
.st-key-review div[data-testid="stHorizontalBlock"] { border-bottom:1px solid #f1f5f9; padding:.15rem 0; align-items:center; }
.st-key-review div[data-testid="stMarkdownContainer"] p { margin:0; }
.review td { padding:.45rem .8rem .45rem 0; border-bottom:1px solid #f1f5f9; font-size:1rem; }
.review td:first-child { color:#64748b; }
</style>"""


def go(step: int) -> None:
    st.session_state.step = step
    st.rerun()


def answer(key: str, value: Any, nxt: int | None = None) -> None:
    st.session_state.answers[key] = value
    go(nxt if nxt is not None else (REVIEW if st.session_state.get("editing") else st.session_state.step + 1))


def header(i: int) -> None:
    s = STEPS[i]
    pct = (i + 1) / (len(STEPS) + 1) * 100
    st.markdown(f'<p class="section">{s.section}<span class="count">{i + 1} of {len(STEPS)}</span></p>'
                f'<div class="steps"><div style="width:{pct:.0f}%"></div></div>'
                f'<p class="q">{s.question}</p>' + (f'<p class="qhelp">{s.help}</p>' if s.help else ""),
                unsafe_allow_html=True)


def big(value: str, unit: str, reading: tuple[str, str] | None = None) -> None:
    chip = f'<span class="chip" style="background:{reading[1]}">{reading[0]}</span>' if reading else ""
    st.markdown(f'<div class="big">{value}<small>{unit}</small></div>{chip}', unsafe_allow_html=True)


def nav(i: int, on_next: Callable[[], None] | None, skip_label: str | None = None) -> None:
    """Continue / skip on one row, then Back and 'skip the rest' as quiet links."""
    if on_next or skip_label:
        c1, c2 = st.columns(2)
        if on_next and c1.button("Continue", type="primary", use_container_width=True, key=f"next{i}"):
            on_next()
        if skip_label and c2.button(skip_label, use_container_width=True, key=f"skip{i}"):
            answer(STEPS[i].key, None)
    c1, c2 = st.columns(2)
    if c1.button("← Back", type="tertiary", key=f"back{i}"):
        go(REVIEW if st.session_state.get("editing") else i - 1)
    if i >= FIRST_OPTIONAL and not st.session_state.get("editing") and \
            c2.button("Skip the heart numbers →", type="tertiary", key=f"rest{i}"):
        go(REVIEW)


def ask(i: int) -> None:
    s, a = STEPS[i], st.session_state.answers
    prev = a.get(s.key)
    header(i)

    if s.kind == "tiles":
        cols = st.columns(len(s.options))
        for col, (label, value) in zip(cols, s.options.items()):
            chosen = s.key in a and prev == value
            if col.button(label, key=f"{s.key}_{label}", use_container_width=True,
                          type="primary" if chosen else "secondary"):
                answer(s.key, value)
        nav(i, None)

    elif s.kind == "slider":
        lo, hi, default, step, unit = s.slider
        v = st.slider(s.question, lo, hi, int(prev) if prev else default, step, key=f"sl_{s.key}",
                      label_visibility="collapsed")
        big(f"{v}", unit, s.reading(v, a) if s.reading else None)
        nav(i, lambda: answer(s.key, int(v)), "I don't know" if s.optional else None)

    elif s.kind == "body":
        know = st.toggle("I know my BMI", key="know_bmi", value=bool(a.get("_bmi_direct")))
        if know:
            b = st.slider("BMI", 15.0, 60.0, float(prev or 27.0), 0.5, key="sl_bmi_direct", label_visibility="collapsed")
        else:
            h = st.select_slider("Height", HEIGHTS, value=a.get("_height", "5′ 8″"), key="sl_height")
            w = st.slider("Weight (pounds)", 80, 400, int(a.get("_weight", 170)), 1, key="sl_weight")
            inches = 54 + HEIGHTS.index(h)
            b = round(703 * w / inches ** 2, 1)
        big(f"{b:.1f}", "BMI", bmi_reading(b, a))

        def save() -> None:
            a["_bmi_direct"] = know
            if not know:
                a["_height"], a["_weight"] = h, w
            answer("bmi", round(float(b), 1))
        nav(i, save, "Skip")

    elif s.kind == "dropdown":
        labels = list(s.options)
        current = next((lab for lab, val in s.options.items() if s.key in a and val == prev), None)
        choice = st.selectbox(s.question, labels, index=labels.index(current) if current else None,
                              placeholder="Choose one", key=f"dd_{s.key}", label_visibility="collapsed")
        if st.button("Continue", type="primary", use_container_width=True, disabled=choice is None, key=f"dd_next{i}"):
            answer(s.key, s.options[choice])
        nav(i, None)

    elif s.kind == "chips":
        labels = {v: k for k, v in HISTORY_QUESTIONS.items()}
        picked = st.pills(s.question, list(labels), selection_mode="multi", key="pills_history",
                          default=[HISTORY_QUESTIONS[k] for k in (prev or [])], label_visibility="collapsed")
        c1, c2 = st.columns(2)
        if c1.button("Continue", type="primary", use_container_width=True, disabled=not picked, key="hx_next"):
            answer("history", [labels[p] for p in picked])
        if c2.button("None of these", use_container_width=True, key="hx_none"):
            answer("history", [])
        nav(i, None)


def describe(a: dict) -> list[tuple[str, str, int]]:
    """(label, answer in words, step) for the review screen."""
    name = {v: k for k, v in RACE_OPTIONS.items()}
    yn = {True: "Yes", False: "No", None: "Not sure"}
    smoke = {v: k for k, v in SMOKING.items()}
    idx = {s.key: n for n, s in enumerate(STEPS)}
    hx = ", ".join(HISTORY_QUESTIONS[k].split("(")[0].split(",")[0].strip() for k in a.get("history", [])) or "None"
    rows = [("Sex", {"male": "Man", "female": "Woman"}.get(a.get("sex"), "—"), idx["sex"]),
            ("Age", f"{a['age']}" if a.get("age") else "—", idx["age"]),
            ("BMI", f"{a['bmi']}" if a.get("bmi") else "Skipped", idx["bmi"]),
            ("Race / ethnicity", name.get(a.get("race_eth"), "Prefer not to say") if "race_eth" in a else "—", idx["race_eth"]),
            ("Past conditions", hx, idx["history"]),
            ("Family history of colon cancer", yn.get(a.get("family_crc"), "—") if "family_crc" in a else "—", idx["family_crc"]),
            ("Smoking", smoke.get(a.get("smoking"), "—"), idx["smoking"]),
            ("Diabetes", yn.get(a.get("diabetes"), "—") if "diabetes" in a else "—", idx["diabetes"]),
            ("Blood pressure medicine", yn.get(a.get("on_bp_meds"), "—") if "on_bp_meds" in a else "Skipped", idx["on_bp_meds"])]
    for k, label, unit in (("sbp", "Top blood pressure number", "mmHg"), ("total_chol", "Total cholesterol", "mg/dL"),
                           ("hdl", "HDL cholesterol", "mg/dL")):
        rows.append((label, f"{a[k]} {unit}" if a.get(k) else "Don't know", idx[k]))
    return rows


def review(on_done: Callable[[dict], None]) -> None:
    a = st.session_state.answers
    st.markdown('<p class="section">Almost done</p><div class="steps"><div style="width:100%"></div></div>'
                '<p class="q">Check your answers</p><p class="qhelp">Tap Edit to change one.</p>', unsafe_allow_html=True)
    box = st.container(key="review")
    for label, value, step in describe(a):
        c1, c2, c3 = box.columns([5, 5, 2], vertical_alignment="center")
        c1.markdown(f"<span style='color:#64748b'>{label}</span>", unsafe_allow_html=True)
        c2.markdown(f"**{value}**")
        if c3.button("Edit", key=f"edit{step}", type="tertiary"):
            st.session_state.editing = True
            go(step)
    st.write("")
    if st.button("See my options →", type="primary", use_container_width=True,
                 disabled=not (a.get("sex") and a.get("age"))):
        on_done(a)


def to_params(a: dict) -> dict[str, str]:
    """Answers -> URL parameters the rest of the app reads."""
    out: dict[str, Any] = {k: a[k] for k in ("sex", "age", "bmi", "race_eth", "sbp", "total_chol", "hdl") if a.get(k)}
    for k in ("family_crc", "diabetes", "on_bp_meds"):
        if a.get(k) is True:
            out[k] = 1
    if a.get("smoking") in ("former", "current"):
        out["ever_smoked"] = 1
    if a.get("smoking") == "current":
        out["current_smoker"] = 1
    out.update({k: 1 for k in a.get("history", [])})
    return {k: str(v) for k, v in out.items()}


def from_params(p: dict, history: set[str]) -> dict:
    """URL parameters -> answers, so 'Edit my answers' starts from what was entered."""
    a: dict[str, Any] = {"history": sorted(history)}
    for k in ("sex", "race_eth"):
        if k in p:
            a[k] = p[k]
    if "race_eth" not in p:
        a["race_eth"] = None
    for k in ("age", "sbp", "total_chol", "hdl"):
        if p.get(k):
            a[k] = int(float(p[k]))
    if p.get("bmi"):
        a["bmi"], a["_bmi_direct"] = float(p["bmi"]), True
    for k in ("family_crc", "diabetes", "on_bp_meds"):
        a[k] = p.get(k) == "1"
    a["smoking"] = "current" if p.get("current_smoker") == "1" else "former" if p.get("ever_smoked") == "1" else "never"
    return a


def welcome() -> None:
    st.markdown(
        f'<div class="welcome"><div class="badge">🩺</div><h1>{WELCOME_TITLE}</h1>'
        f'<p class="lead">{WELCOME_TEXT}</p>'
        '<div class="facts"><span>⏱ About 2 minutes</span><span>12 short questions</span>'
        '<span>🔒 Nothing is stored</span></div></div>', unsafe_allow_html=True)
    _, c, _ = st.columns([1, 2, 1])
    if c.button("Get started", type="primary", use_container_width=True):
        go(0)
    st.markdown('<p class="fine">For learning and for talking with your doctor. Not medical advice.</p>',
                unsafe_allow_html=True)


def run(on_done: Callable[[dict], None]) -> None:
    """Draw the current screen. on_done(answers) is called from the review screen."""
    ss = st.session_state
    ss.setdefault("step", -1)
    ss.setdefault("answers", {})
    st.markdown(CSS, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        if ss.step < 0:
            welcome()
        elif ss.step >= REVIEW:
            review(on_done)
        else:
            ask(ss.step)
