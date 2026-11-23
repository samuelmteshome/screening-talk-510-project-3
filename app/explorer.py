"""One-page explorer: body map plus a flowchart that grows in place.

Click an organ and its node appears with Medications / Screening; click a branch
and its options appear; click an option and its numbers appear underneath. Every
earlier step stays on screen, and nothing reloads: all the numbers for this person
are worked out here in Python and handed to the page as JSON.

Pure Python (no Streamlit) so it can be tested in CI.
"""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

import body_map
import colon_risk
import flowchart
import heart_actions as ha
import prevent
from catalog import TOPICS, Topic, chart_rows, eligibility, load_evidence, number_rows, topics_for

TEMPLATE = Path(__file__).resolve().parent / "assets" / "explorer.html"
DEFAULT_SBP = 145


def md(text: str) -> str:
    """Escape, then turn **bold** into <b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text))


def compare_block(base: float, rr: float, outcome: str, certain: bool = True) -> dict:
    line = ha.compare(base, rr, outcome, certain)
    return {"type": "compare", "html": md(ha.sentence(line)), "denom": line.denom,
            "without": line.without, "with": line.with_, "outcome": ha.OUTCOME_WORDS[outcome]}


def checked_note(ev: dict) -> str:
    """Says what a source's numbers were checked against, or that they weren't yet."""
    if ev.get("verified_by") is None:
        return "Numbers not yet checked against the source."
    return f"Numbers checked against the {escape(ev.get('verified_against', 'source'))}."


def evidence_blocks(topic: Topic) -> list[dict]:
    """The topic's trial results: grouped bars where we have pairs, else a list of numbers."""
    out = []
    for ev in load_evidence(topic):
        meta = ev.get("comparison", "")
        if ev.get("horizon_years"):
            meta += f", followed for {ev['horizon_years']} years"
        out.append({"type": "source", "html": f'<a href="{escape(ev["url"])}" target="_blank">{escape(ev["source"])}</a>',
                    "caption": meta.strip(", ")})
        rows = chart_rows(ev["_file"], ev)
        if rows:
            groups = list(dict.fromkeys(r["Group"] for r in rows))
            labels = list(dict.fromkeys(r["Result"] for r in rows))
            vals = {(r["Result"], r["Group"]): r["Per 1,000"] for r in rows}
            out.append({"type": "bars", "unit": "per 1,000 people", "groups": groups,
                        "rows": [{"label": lab, "values": [vals[(lab, g)] for g in groups]} for lab in labels]})
        else:
            out.append({"type": "numbers", "rows": [[k.capitalize(), f"{v:g}"] for k, v in number_rows(ev)]})
        out.append({"type": "caption", "html": checked_note(ev)})
    return out


def heart_detail(action: str, p: dict, api: dict | None) -> list[dict]:
    """Numbers for one heart option, applied to this person's own 10-year risk."""
    eff = ha.load_effects()[action]
    e = eff["effects"]
    blocks: list[dict] = []
    pred = (api or {}).get("prediction") or {}
    death = pred.get("risk_cv_death_10y")
    event = None
    if prevent.in_range(float(p["age"])):
        event, missing = prevent.from_profile(p)
        note = "Your chance of a heart attack or stroke comes from the American Heart Association's PREVENT equations."
        if missing:
            names = {"total_chol": "cholesterol", "hdl": "HDL", "sbp": "blood pressure"}
            note += (" You skipped " + ", ".join(names[m] for m in missing) + ", so typical values were used. "
                     "Edit your answers for a closer estimate.")
        blocks.append({"type": "caption", "html": md(note)})

    if action == "checkups":
        blocks.append({"type": "text", "html": md(
            "In 11 large trials, people offered regular general checkups **did not live longer** and were **not less "
            "likely to die of heart disease** than people who weren't. Checkups can still catch high blood pressure "
            "or cholesterol, which you can then treat with the medicines in this chart.")})
    elif event is None and death is None:
        blocks.append({"type": "text", "html": "Your own numbers will appear here once the heart model is connected."})
    elif action == "bp":
        current = float(p.get("sbp") or 0) or DEFAULT_SBP
        outs = [{"outcome": ha.OUTCOME_WORDS[k], "base": b, "per5": e[k]["rr"], "certain": e[k].get("significant", True)}
                for k, b in (("event", event), ("cv_death", death)) if k in e and b is not None]
        blocks.append({"type": "bp", "current": current, "known": bool(float(p.get("sbp") or 0)), "outcomes": outs})
    else:
        for k, base in (("event", event), ("cv_death", death)):
            if k in e and base is not None:
                blocks.append(compare_block(base, e[k]["rr"], k, e[k].get("significant", True)))
    if action != "checkups" and "any_death" in e:
        a = e["any_death"]
        blocks.append({"type": "text", "html": md(
            f"Deaths from any cause were about **{ha.pct_change(a['rr'])}** in the studies."
            if a.get("significant", True) else "The studies found **no clear change** in deaths from any cause.")})
    if "major_bleeding" in e:
        blocks.append({"type": "text", "html": md(
            f"**Downside:** serious bleeding was about **{ha.pct_change(e['major_bleeding']['rr'])}** common "
            "(stomach bleeding and, rarely, bleeding in the brain).")})
    blocks.append({"type": "caption", "html": f'Source: <a href="{escape(eff["url"])}" target="_blank">'
                   f'{escape(eff["source"])}</a>. Applies to people who have never had a heart attack or stroke. '
                   "Numbers not yet checked against the full paper."})
    return blocks


def colon_detail(p: dict) -> list[dict]:
    d = colon_risk.data()
    eff = d["colonoscopy"]["if_screened"]
    blocks = [compare_block(colon_risk.risk(p, "incidence"), eff["crc"]["rr"], "crc"),
              compare_block(colon_risk.risk(p, "mortality"), eff["crc_death"]["rr"], "crc_death"),
              {"type": "text", "html": md("The trial found **no clear change** in deaths from any cause.")}]
    names = {k: v["label"] for k, v in d["risk_factors"].items()}
    raised = [names[k] for k in colon_risk.factors(p)]
    who = f"a {int(float(p['age']))}-year-old {'man' if p['sex'] == 'male' else 'woman'}"
    blocks.append({"type": "caption", "html": escape(
        f"Your starting chance is the US average for {who}" + (f", raised because you said: {'; '.join(raised)}."
                                                              if raised else ".")
        + " Colonoscopy numbers are for people who actually had one in the NordICC trial (ages 55 to 64, 10 years). "
        "Among everyone invited, only 42% went, so the benefit for the whole invited group was smaller.")})
    srcs = [d["baseline"], *d["risk_factors"].values(), d["colonoscopy"]]
    blocks.append({"type": "caption", "html": "Sources: " + "; ".join(
        f'<a href="{escape(s["url"])}" target="_blank">{escape(s["source"].split("(")[0].strip())}</a>' for s in srcs)})
    return blocks


def prediction_blocks(topic: Topic, api: dict | None) -> list[dict]:
    pred = (api or {}).get("prediction")
    if not pred:
        return [{"type": "text", "html": "The prediction service isn't connected yet, so here is what the trials found."}]
    out = [{"type": "stat", "big": f"about {pred['per_100']}", "label": "out of 100 people like you"}]
    if topic.id == "prostate":
        out.append({"type": "caption", "html": "Chance of a PSA of 4.0 or higher, the level that usually leads to a "
                    "biopsy. This is a test result, not a cancer diagnosis."})
    return out


def option_detail(topic: Topic, option: flowchart.Option, p: dict, api: dict | None) -> list[dict]:
    if topic.id == "heart":
        return heart_detail(option.id, p, api)
    if topic.id == "colorectal" and colon_risk.in_range(float(p["age"])):
        return colon_detail(p) + [{"type": "heading", "html": "What the trial found"}] + evidence_blocks(topic)
    blocks = prediction_blocks(topic, api) if topic.has_model else []
    return blocks + [{"type": "heading", "html": "What the research found"}] + evidence_blocks(topic)


def payload(p: dict, history: set[str], api: dict[str, dict | None], start: dict | None = None) -> dict:
    """Everything the page needs for this person: organs, branches, options and each option's numbers."""
    sex, age = p["sex"], int(float(p["age"]))
    organs = []
    for t in topics_for(sex):
        ok, why = eligibility(t, age, history)
        branches = [{"id": b, "label": flowchart.BRANCHES[b],
                     "options": [{"id": o.id, "label": o.label,
                                  "detail": option_detail(t, o, p, api.get(t.id)) if ok else []} for o in opts]}
                    for b, opts in flowchart.options_for(t.id).items()]
        organs.append({"id": t.id, "label": t.organ, "tool": t.tool, "color": body_map.ORGANS[t.id]["color"],
                       "eligible": ok, "note": why, "branches": branches,
                       "evidence": [] if ok else evidence_blocks(t)})
    search = []
    for o in flowchart.OPTIONS:
        if any(x["id"] == o.topic for x in organs):
            search.append({"label": o.label, "where": f"{TOPICS[o.topic].organ} › {flowchart.BRANCHES[o.branch]}",
                           "names": [o.label.lower(), o.id, *o.aliases], "organ": o.topic, "branch": o.branch,
                           "option": o.id})
    for x in organs:
        search.append({"label": x["label"], "where": "all options", "names": [x["id"], x["label"].lower(), x["tool"].lower()],
                       "organ": x["id"], "branch": None, "option": None})
    return {"sex": sex, "organs": organs, "search": search, "start": start or {}}


def render(p: dict, history: set[str], api: dict[str, dict | None], start: dict | None = None) -> str:
    """Full HTML for components.html()."""
    data = payload(p, history, api, start)
    off = frozenset(o["id"] for o in data["organs"] if not o["eligible"])
    figure = body_map.inline(p["sex"], topics_for(p["sex"]), off)
    blob = json.dumps(data).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("{{FIGURE}}", figure).replace("{{DATA}}", blob)
