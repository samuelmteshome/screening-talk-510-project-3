"""Which organs and screening tools the app covers, and how search finds them.

Pure Python (no Streamlit) so it can be tested in CI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "evidence"


@dataclass(frozen=True)
class Topic:
    id: str                      # matches topics/<id>.yaml and the API "topic" field
    organ: str                   # label on the body map
    tool: str                    # the screening test or medicine
    sexes: tuple[str, ...]       # who the topic applies to
    age_min: int                 # range covered by the model or trial
    age_max: int
    has_model: bool              # False = trial evidence only
    evidence_files: tuple[str, ...]
    aliases: tuple[str, ...] = field(default_factory=tuple)
    excluded_history: str = ""   # intake flag that puts a person outside the data
    excluded_reason: str = ""    # shown instead of a number when that flag is set


TOPICS: dict[str, Topic] = {
    "prostate": Topic(
        id="prostate",
        organ="Prostate",
        tool="PSA blood test",
        sexes=("male",),
        age_min=55,
        age_max=69,
        has_model=True,
        evidence_files=(
            "erspc_2025.json",
            "erspc_metastatic_2012.json",
            "heijnsdijk_lifeyears_2012.json",
        ),
        aliases=("psa", "prostate exam", "prostate cancer", "prostate specific antigen"),
        excluded_history="prior_prostate_cancer",
        excluded_reason=("This tool is about screening men who have never had prostate cancer. "
                         "The data left out men with prostate cancer or a recent prostate procedure, "
                         "so it can't describe your situation. Your urologist can tell you about follow-up testing."),
    ),
    "heart": Topic(
        id="heart",
        organ="Heart",
        tool="Statin, blood pressure, aspirin",
        sexes=("male", "female"),
        age_min=40,
        age_max=75,
        has_model=True,
        evidence_files=("hope3_2016.json",),
        aliases=("statin", "cholesterol", "rosuvastatin", "heart attack", "stroke", "cardiac", "cardiology",
                 "aspirin", "blood pressure", "hypertension", "checkup", "primary care"),
        excluded_history="prior_cvd",
        excluded_reason=("This tool predicts a first heart attack or stroke. The data left out anyone who already "
                         "had a heart attack, stroke, angina, or heart failure, so it can't give you a number. "
                         "Statins are usually recommended after these events; ask your doctor or cardiologist."),
    ),
    "colorectal": Topic(
        id="colorectal",
        organ="Colon",
        tool="Colonoscopy",
        sexes=("male", "female"),
        age_min=55,
        age_max=64,
        has_model=False,
        evidence_files=("nordicc_2022.json",),
        aliases=("colonoscopy", "colon", "colorectal", "bowel", "colon cancer", "rectum"),
        excluded_history="prior_crc",
        excluded_reason=("This tool is about screening people who have never had colorectal cancer. "
                         "If you have had it, your follow-up colonoscopies are set by your doctor."),
    ),
}


def topics_for(sex: str) -> list[Topic]:
    """Topics shown on the body map for this sex."""
    return [t for t in TOPICS.values() if sex in t.sexes]


def in_range(topic: Topic, age: int) -> bool:
    return topic.age_min <= age <= topic.age_max


HISTORY_QUESTIONS = {
    "prior_cvd": "Heart attack, stroke, angina (chest pain from the heart), or heart failure",
    "prior_prostate_cancer": "Prostate cancer",
    "prior_crc": "Colorectal (colon or rectal) cancer",
}


def eligibility(topic: Topic, age: int, history: set[str]) -> tuple[bool, str]:
    """Whether this person is inside the group the data covers, and why not if they aren't."""
    if topic.excluded_history and topic.excluded_history in history:
        return False, topic.excluded_reason
    if not in_range(topic, age):
        return False, (f"The data for {topic.organ.lower()} covers ages {topic.age_min} to {topic.age_max}, "
                       f"so we can't give a {age}-year-old a number.")
    return True, ""


def search(query: str, sex: str) -> list[Topic]:
    """Match an organ, test, or medicine name. Case-insensitive, partial words allowed."""
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for t in topics_for(sex):
        names = (t.id, t.organ.lower(), t.tool.lower(), *t.aliases)
        if any(q in n or n in q for n in names):
            hits.append(t)
    return hits


def search_options(sex: str) -> list[str]:
    """Every name a user can pick in the search box, mapped back by search()."""
    opts = []
    for t in topics_for(sex):
        opts += [t.organ, t.tool, *(a.title() for a in t.aliases)]
    return sorted(set(opts))


def load_evidence(topic: Topic) -> list[dict]:
    """Evidence files for a topic. Files not in the repo yet are skipped."""
    out = []
    for name in topic.evidence_files:
        path = EVIDENCE_DIR / name
        if path.exists():
            out.append({**json.loads(path.read_text()), "_file": name})
    return out


# Per-1,000 results to draw as "with vs without" bars, by evidence file.
# (label, key in the treated/screened group, key in the comparison group, group names)
CHART_PAIRS = {
    "hope3_2016.json": (("Statin", "Placebo"), [
        ("Heart attack, stroke, or heart death", "cv_death_mi_stroke_statin", "cv_death_mi_stroke_placebo"),
        ("New diabetes", "new_diabetes_statin", "new_diabetes_placebo"),
    ]),
    "nordicc_2022.json": (("Invited to colonoscopy", "Usual care"), [
        ("Colorectal cancer", "crc_invited", "crc_usual_care"),
        ("Death from colorectal cancer", "crc_death_invited", "crc_death_usual_care"),
    ]),
}


def chart_rows(file_name: str, evidence: dict) -> list[dict]:
    """Rows for a grouped bar chart (per 1,000 people), skipping numbers not filled in."""
    if file_name not in CHART_PAIRS:
        return []
    (group_a, group_b), pairs = CHART_PAIRS[file_name]
    nums = evidence.get("numbers", {})
    rows = []
    for label, key_a, key_b in pairs:
        a, b = (nums.get(k, {}).get("value") for k in (key_a, key_b))
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            rows += [{"Result": label, "Group": group_a, "Per 1,000": a},
                     {"Result": label, "Group": group_b, "Per 1,000": b}]
    return rows


def number_rows(evidence: dict) -> list[tuple[str, float]]:
    """(label, value) for every number the file has filled in."""
    rows = []
    for key, item in evidence.get("numbers", {}).items():
        value = item.get("value") if isinstance(item, dict) else item
        if isinstance(value, (int, float)):
            rows.append((key.replace("_", " "), value))
    return rows
