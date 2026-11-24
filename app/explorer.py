"""One-page explorer: body map plus a flowchart that grows in place.

Click an organ and its node appears with Medications / Screening; click a branch
and its options appear; click an option and its numbers appear underneath. Every
earlier step stays on screen, and nothing reloads: all the numbers for this person
are worked out here in Python and handed to the page as JSON.

Pure Python (no Streamlit) so it can be tested in CI.
"""
from __future__ import annotations

import json
import math
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


# ---------- Headline sentence + "See more" ----------
# Every option opens with one plain sentence (risk change, then years of life), then a "See more" button
# with the details and a table saying where each number came from.
MODEL = "Our model"            # trained in this project on NHANES (src/train_heart.py, src/train.py)
PREVENT_SRC = "PREVENT equations"
STUDY = "Published study"
CALC = "Our calculation"
GOMPERTZ_B = 0.085             # yearly rise in adult death rates (about 8.5% a year): turns a lower death rate into years


def pct(x: float) -> str:
    """0.0283 -> '2.8%'."""
    return f"{100 * x:.1f}%" if x < 0.1 else f"{100 * x:.0f}%"


def rel(rr: float) -> int:
    return round(abs(1 - rr) * 100)


def years_from_rr(rr: float) -> float:
    """Rule of thumb: a death rate lower by a fixed share for life is worth about ln(1/rr)/b years."""
    return math.log(1 / rr) / GOMPERTZ_B


def years_text(y: float) -> str:
    if y < 0.75:
        months = round(y * 12)
        return f"about {months} months" if months > 1 else "about a month"
    half = round(y * 2) / 2
    return f"about {half:g} year" + ("" if half == 1 else "s")


def src_link(name: str, url: str) -> str:
    return f'<a href="{escape(url)}" target="_blank">{escape(name.split("(")[0].strip().rstrip(","))}</a>'


def row(number: str, kind: str, how: str) -> list[str]:
    return [escape(number), kind, how]


def points(lead: str, items: list[str]) -> str:
    """Headline as a short lead-in and one bullet per effect."""
    return (f'<span class="lead">{md(lead)}</span><ul class="points">'
            + "".join(f"<li>{md(i)}</li>" for i in items if i) + "</ul>")


def wrap(headline: str | tuple[str, list[str]], more: list[dict], sources: list[list[str]], note: str = "") -> list[dict]:
    html = points(*headline) if isinstance(headline, tuple) else md(headline)
    out = [{"type": "headline", "html": html}]
    if note:
        out.append({"type": "caption", "html": md(note)})
    more = more + [{"type": "heading", "html": "Where each number comes from"}, {"type": "sources", "rows": sources}]
    return out + [{"type": "more", "blocks": more}]


def heart_bases(p: dict, api: dict | None) -> tuple[float | None, float | None, list[dict], list[list[str]]]:
    """10-year chance of a heart attack or stroke (PREVENT) and of dying of heart disease or stroke (our model)."""
    pred = (api or {}).get("prediction") or {}
    death = pred.get("risk_cv_death_10y")
    event, blocks, rows = None, [], []
    if prevent.in_range(float(p["age"])):
        event, missing = prevent.from_profile(p)
        note = "Your chance of a heart attack or stroke comes from the American Heart Association's PREVENT equations."
        if missing:
            names = {"total_chol": "cholesterol", "hdl": "HDL", "sbp": "blood pressure"}
            note += (" You skipped " + " and ".join(names[m] for m in missing) + ", so typical values were used. "
                     "Edit your answers for a closer estimate.")
        blocks.append({"type": "caption", "html": md(note)})
        rows.append(row(f"Your 10-year chance of a heart attack or stroke: {pct(event)}", PREVENT_SRC,
                        "Published AHA formula, run on your answers (age, sex, cholesterol, HDL, blood pressure, "
                        "BP medicine, diabetes, smoking)."))
    if death is not None:
        rows.append(row(f"Your 10-year chance of dying of heart disease or stroke: {pct(death)}", MODEL,
                        "Logistic regression trained on NHANES 1999–2008 with deaths up to 2019 (test AUC 0.78)."))
    return event, death, blocks, rows


def effect_rows(eff: dict, e: dict, keys: dict[str, str]) -> list[list[str]]:
    link = src_link(eff["source"], eff["url"])
    out = []
    for k, words in keys.items():
        if k in e:
            x = e[k]
            ci = f" (95% CI {x['ci'][0]}–{x['ci'][1]})" if x.get("ci") else ""
            out.append(row(f"{words}: {rel(x['rr'])}% {'lower' if x['rr'] < 1 else 'higher'}{ci}", STUDY, link))
    return out


def life_clause(any_death: dict | None) -> tuple[str, list[list[str]]]:
    """'May add about 1 year to your life' when trials showed fewer deaths from any cause; else say it wasn't shown."""
    if any_death and any_death.get("significant", True) and any_death["rr"] < 1:
        y = years_from_rr(any_death["rr"])
        return (f"May add **{years_text(y)}** to your life",
                [row(f"Years of life: {years_text(y)}", CALC,
                     f"The studies' {rel(any_death['rr'])}% fewer deaths from any cause, turned into years with a "
                     "standard rule of thumb (death rates rise about 8.5% a year with age). Assumes the effect lasts.")])
    return ("Has **not been shown to add years** of life", [])


def compare_more(event, death, e, base_blocks) -> list[dict]:
    blocks = list(base_blocks)
    for k, base in (("event", event), ("cv_death", death)):
        if k in e and base is not None:
            blocks.append(compare_block(base, e[k]["rr"], k, e[k].get("significant", True)))
    return blocks


def bp_target(current: float) -> int:
    return max(110, min(130, int((current - 10) // 5 * 5)))


def heart_detail(action: str, p: dict, api: dict | None) -> list[dict]:
    """One heart option: headline, then the details applied to this person's own 10-year risk."""
    if action in LIFESTYLE:
        return lifestyle_detail(action, p, api)
    eff = ha.load_effects()[action]
    e = eff["effects"]
    event, death, base_blocks, rows = heart_bases(p, api)
    caveat = {"type": "caption", "html": f"Source: {src_link(eff['source'], eff['url'])}. Applies to people who have "
              "never had a heart attack or stroke. " + checked_note(eff)}
    rows = rows + effect_rows(eff, e, {"event": "Heart attacks and strokes", "cv_death": "Deaths from heart disease or stroke",
                                       "any_death": "Deaths from any cause", "major_bleeding": "Serious bleeding"})
    base = event if event is not None else death
    what = "a heart attack or stroke" if event is not None else "dying of heart disease or stroke"
    k = "event" if event is not None else "cv_death"

    if action == "checkups":
        more = [{"type": "text", "html": md(
            "In 11 large trials, people offered regular general checkups **did not live longer** and were **not less "
            "likely to die of heart disease** than people who weren't. Checkups can still catch high blood pressure "
            "or cholesterol, which you can then treat with the medicines in this chart.")}, caveat]
        return wrap(("Regular general checkups:", [
            "Have **not been shown** to lower heart attacks, strokes or deaths from heart disease",
            "Have **not been shown to add years** of life"]), more, rows)
    if base is None:
        return wrap("Your own numbers will appear here once the heart model is connected.", [caveat], rows)

    if action == "bp":
        current = float(p.get("sbp") or 0) or DEFAULT_SBP
        known = bool(float(p.get("sbp") or 0))
        target = bp_target(current)
        outs = [{"outcome": ha.OUTCOME_WORDS[kk], "base": b, "per5": e[kk]["rr"], "certain": e[kk].get("significant", True)}
                for kk, b in (("event", event), ("cv_death", death)) if kk in e and b is not None]
        more = base_blocks + [{"type": "bp", "current": current, "known": known, "outcomes": outs}]
        any_d = e.get("any_death")
        life, life_rows = life_clause(any_d)
        if current - target <= 0:
            head = (f"Your top blood pressure number ({current:.0f}) is already at a healthy level, so blood pressure "
                    "medicine is unlikely to help you much.")
        else:
            rr = ha.bp_rr(e[k]["rr"], current, target)
            head = (f"Lowering your top blood pressure number from {current:.0f} to {target} with medicine:", [
                f"Lowers your chance of {what} by about **{rel(rr)}%** (from {pct(base)} to {pct(base * rr)} over 10 years)",
                life])
            rows.append(row(f"With treatment: {pct(base * rr)}", CALC,
                            f"Your chance × the studies' effect per 5 points, for a {current - target:.0f}-point drop."))
        note = "" if known else f"You skipped your blood pressure, so {current:.0f} was used. Change it under See more."
        return wrap(head, more + [caveat], rows + life_rows, note)

    rr = e[k]["rr"]
    life, life_rows = life_clause(e.get("any_death"))
    name = {"statin": "Starting a statin", "aspirin": "Taking a daily low-dose aspirin"}.get(action, ha.ACTIONS[action])
    items = [f"Lowers your chance of {what} by about **{rel(rr)}%** (from {pct(base)} to {pct(base * rr)} over 10 years)"]
    if "major_bleeding" in e:
        items.append(f"Raises your chance of serious bleeding by about **{rel(e['major_bleeding']['rr'])}%**")
    head = (f"{name}:", items + [life])
    rows.append(row(f"With it: {pct(base * rr)}", CALC, "Your chance × the studies' relative effect."))
    more = compare_more(event, death, e, base_blocks)
    if "major_bleeding" in e:
        more.append({"type": "text", "html": md(
            f"**Downside:** serious bleeding was about **{ha.pct_change(e['major_bleeding']['rr'])}** common "
            "(stomach bleeding and, rarely, bleeding in the brain).")})
    return wrap(head, more + [caveat], rows + life_rows)


# ---------- Lifestyle ----------
LIFESTYLE = ("quit_smoking", "exercise", "weight_loss")


def lifestyle_data() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "evidence" / "lifestyle.json").read_text())["actions"]


def quit_years(age: float, table: dict[str, int]) -> tuple[int, str]:
    for band, y in table.items():
        lo, hi = (int(x) for x in band.split("-"))
        if lo <= age <= hi:
            return y, band
    if age > 64:
        return table["55-64"], "55-64"
    return table["25-34"], "25-34"


def lifestyle_detail(action: str, p: dict, api: dict | None) -> list[dict]:
    d = lifestyle_data()[action]
    age = float(p["age"])
    event, death, base_blocks, rows = heart_bases(p, api)
    link = src_link(d["source"], d["url"])

    if action == "quit_smoking":
        years, band = quit_years(age, d["life_years_by_quit_age"])
        yr_row = row(f"Years of life from quitting: about {years}", STUDY,
                     f"{link}: people who quit at ages {band.replace('-', ' to ')} gained about {years} years"
                     + (" (the study's oldest group; you are older)" if age > 64 else "") + ".")
        if p.get("current_smoker") != "1":
            head = ("You don't smoke now, so there is nothing to gain here. For people who do smoke:", [
                f"Smoking takes about **{d['smoker_life_years_lost']} years** off their life",
                "Quitting at any age wins most of that back"])
            more = [{"type": "text", "html": md(f"People who quit at ages {band.replace('-', ' to ')} gained about "
                                                f"**{years} years** of life compared with those who kept smoking.")},
                    {"type": "caption", "html": f"Source: {link}. {escape(d['verified_against'])}."}]
            return wrap(head, more, [yr_row])
        more = list(base_blocks)
        clauses = []
        if event is not None:
            after = prevent.from_profile({**p, "current_smoker": "0"})[0]
            clauses.append(f"Lowers your chance of a heart attack or stroke by about **{rel(after / event)}%** "
                           f"(from {pct(event)} to {pct(after)} over 10 years)")
            more.append(pair_block(event, after, "event"))
            rows.append(row(f"If you quit: {pct(after)}", PREVENT_SRC, "Same formula, run with smoking set to no."))
        quit_pred = ((api or {}).get("if_quit") or {}).get("prediction") or {}
        if death is not None and quit_pred.get("risk_cv_death_10y") is not None:
            after_d = quit_pred["risk_cv_death_10y"]
            more.append(pair_block(death, after_d, "cv_death"))
            rows.append(row(f"Chance of dying of heart disease or stroke if you quit: {pct(after_d)}", MODEL,
                            "Same model, run with smoking set to no."))
            if after_d < death:
                clauses.append(f"Lowers your chance of dying of heart disease or stroke by about **{rel(after_d / death)}%** "
                               f"(from {pct(death)} to {pct(after_d)} over 10 years)")
        head = ("Quitting smoking:", clauses + [f"Adds about **{years} years** to your life (on average, for people who quit at your age)"])
        more.append({"type": "caption", "html": f"Years of life: {link}. {escape(d['verified_against'])}."})
        return wrap(head, more, rows + [yr_row])

    if action == "exercise":
        e, ly, st = d["effects"], d["life_years"], d["strength"]
        rr = e["cv_death"]["rr"]
        if death is not None:
            head = ("Regular exercise is linked to:", [
                f"About **{rel(rr)}%** lower chance of dying of heart disease or stroke (from {pct(death)} to "
                f"{pct(death * rr)} over 10 years)",
                f"Up to **{ly['value']:g} more years** of life"])
            rows.append(row(f"With exercise: {pct(death * rr)}", CALC, "Your chance from our model × the study's effect."))
        else:
            head = ("Regular exercise is linked to:", [
                f"About **{rel(rr)}%** fewer deaths from heart disease and stroke",
                f"Up to **{ly['value']:g} more years** of life"])
        more = list(base_blocks)
        if death is not None:
            more.append(pair_block(death, death * rr, "cv_death"))
        more += [
            {"type": "heading", "html": "What kind, and how much"},
            {"type": "text", "html": md(d["recommendation"])},
            {"type": "text", "html": md(f"Doing both aerobic exercise and muscle strengthening was linked to **{st['combined_cvd_pct']}% "
                                        f"lower** heart disease and **{st['combined_death_pct']}% fewer** deaths from any cause. "
                                        f"Muscle strengthening alone: {st['strength_alone']}.")},
            {"type": "text", "html": md(f"Even a little helps: up to 75 minutes a week of brisk walking was linked to about "
                                        f"**{ly['low_dose']['value']:g} more years** of life.")},
            {"type": "caption", "html": md("These are from studies that followed people over time, not randomized trials, "
                                           "so they show a strong link but can't prove exercise is the only cause.")},
        ]
        rows += [row(f"Deaths from heart disease or stroke: {rel(rr)}% lower (95% CI {e['cv_death']['ci'][0]}–{e['cv_death']['ci'][1]})",
                     STUDY, link + " (vigorous exercise at the guideline amount vs none)"),
                 row(f"Years of life: up to {ly['value']:g}", STUDY, src_link(ly["source"], ly["url"]) + f" ({escape(ly['label'])})"),
                 row(f"Aerobic + strength: {st['combined_cvd_pct']}% lower heart disease", STUDY, src_link(st["source"], st["url"]))]
        return wrap(head, more, rows)

    # weight loss
    kg = d["example_kg"]
    drop = -d["sbp_per_kg"]["value"] * kg
    t = d["trial"]
    bp = ha.load_effects()["bp"]["effects"]["event"]["rr"]
    rr = bp ** (drop / 5)
    lbs = round(kg * 2.2046)
    if event is not None:
        mid = (f"In blood pressure trials, a drop that size meant about **{rel(rr)}%** fewer heart attacks and strokes "
               f"(from {pct(event)} to {pct(event * rr)} over 10 years for you)")
        rows.append(row(f"After losing {lbs} lb: {pct(event * rr)}", CALC,
                        "Your chance × the blood pressure trials' effect for the expected drop in blood pressure."))
    else:
        mid = f"In blood pressure trials, a drop that size meant about **{rel(rr)}%** fewer heart attacks and strokes"
    head = (f"Losing {lbs} pounds:", [
        f"Lowers your top blood pressure number by about **{drop:.0f} points**", mid,
        "Did **not lower** heart attacks or strokes in a large weight-loss trial of adults with type 2 diabetes",
        "Has **not been shown to add years** of life"])
    more = list(base_blocks)
    if event is not None:
        more.append(pair_block(event, event * rr, "event"))
    more += [{"type": "text", "html": md(
        f"In the Look AHEAD trial, adults with type 2 diabetes who lost about {t['weight_loss_pct_1y']['intervention']:g}% "
        f"of their weight had about the same rate of heart attacks and strokes as those who didn't "
        f"({t['events_per_100_person_years']['intervention']:g} vs {t['events_per_100_person_years']['control']:g} "
        "per 100 people per year). Weight loss still lowers blood pressure, blood sugar and joint pain.")}]
    rows += [row(f"Blood pressure: about {-d['sbp_per_kg']['value']:g} points lower per kg (2.2 lb) lost", STUDY, link),
             row(f"Heart attacks and strokes per 5 points lower: {rel(bp)}% fewer", STUDY,
                 src_link(ha.load_effects()["bp"]["source"], ha.load_effects()["bp"]["url"])),
             row("No clear change in heart attacks or strokes", STUDY, src_link(t["source"], t["url"]))]
    return wrap(head, more, rows)


def pair_block(base: float, after: float, outcome: str) -> dict:
    """Without/with bars for two absolute risks (no trial ratio involved)."""
    return compare_block(base, after / base if base else 1.0, outcome)


def colon_detail(p: dict, topic: Topic) -> list[dict]:
    d = colon_risk.data()
    eff = d["colonoscopy"]["if_screened"]
    inc, mort = colon_risk.risk(p, "incidence"), colon_risk.risk(p, "mortality")
    more = [compare_block(inc, eff["crc"]["rr"], "crc"),
            compare_block(mort, eff["crc_death"]["rr"], "crc_death"),
            {"type": "text", "html": md("The trial found **no clear change** in deaths from any cause.")}]
    names = {k: v["label"] for k, v in d["risk_factors"].items()}
    raised = [names[k] for k in colon_risk.factors(p)]
    who = f"a {int(float(p['age']))}-year-old {'man' if p['sex'] == 'male' else 'woman'}"
    more.append({"type": "caption", "html": escape(
        f"Your starting chance is the US average for {who}" + (f", raised because you said: {'; '.join(raised)}."
                                                              if raised else ".")
        + " Colonoscopy numbers are for people who actually had one in the NordICC trial (ages 55 to 64, 10 years). "
        "Among everyone invited, only 42% went, so the benefit for the whole invited group was smaller.")})
    srcs = [d["baseline"], *d["risk_factors"].values(), d["colonoscopy"]]
    rows = [row(f"Your 10-year chance of getting colorectal cancer: {pct(inc)}", CALC,
                f"US cancer registry rates for your age and sex ({src_link(d['baseline']['source'], d['baseline']['url'])})"
                + (", raised by published relative risks for: " + "; ".join(escape(r) for r in raised) if raised else "") + "."),
            row(f"Colorectal cancer: {rel(eff['crc']['rr'])}% lower; deaths from it: {rel(eff['crc_death']['rr'])}% lower",
                STUDY, src_link(d["colonoscopy"]["source"], d["colonoscopy"]["url"])),
            row(f"With colonoscopy: {pct(inc * eff['crc']['rr'])}", CALC, "Your chance × the trial's effect.")]
    head = ("Getting a colonoscopy:", [
        f"Lowers your chance of being diagnosed with colorectal cancer by about **{rel(eff['crc']['rr'])}%** "
        f"(from {pct(inc)} to {pct(inc * eff['crc']['rr'])} over 10 years)",
        f"Lowers your chance of dying of colorectal cancer by about **{rel(eff['crc_death']['rr'])}%** "
        f"(from {pct(mort)} to {pct(mort * eff['crc_death']['rr'])} over 10 years)",
        "Has **not been shown to add years** of life overall"])
    more += [{"type": "caption", "html": "Sources: " + "; ".join(src_link(s["source"], s["url"]) for s in srcs)},
             {"type": "heading", "html": "What the trial found"}, *evidence_blocks(topic)]
    return wrap(head, more, rows)


def colon_test_detail(p: dict, test: str) -> list[dict]:
    """Stool test (FOBT) or sigmoidoscopy: the trials' effect for people invited, on this person's own chance."""
    d = colon_risk.data()
    t = d[test]
    eff = t["if_invited"]
    link = src_link(t["source"], t["url"])
    in_range = colon_risk.in_range(float(p["age"]))
    inc = colon_risk.risk(p, "incidence") if in_range else None
    mort = colon_risk.risk(p, "mortality") if in_range else None
    name = {"fobt": f"Doing a stool test {t['how_often']}", "sigmoidoscopy": "Getting a sigmoidoscopy"}[test]
    parts, rows, more = [], [], []
    if mort is not None:
        rows.append(row(f"Your 10-year chance of dying of colorectal cancer: {pct(mort)}", CALC,
                        f"US cancer registry rates for your age and sex ({src_link(d['baseline']['source'], d['baseline']['url'])})."))
    if "crc" in eff:
        r = eff["crc"]["rr"]
        parts.append(f"Lowers your chance of being diagnosed with colorectal cancer by about **{rel(r)}%**"
                     + (f" (from {pct(inc)} to {pct(inc * r)} over 10 years)" if inc is not None else ""))
        if inc is not None:
            more.append(compare_block(inc, r, "crc"))
            rows.insert(0, row(f"Your 10-year chance of getting colorectal cancer: {pct(inc)}", CALC, "Same registry rates."))
        rows.append(row(f"Colorectal cancer: {rel(r)}% lower (95% CI {eff['crc']['ci'][0]}–{eff['crc']['ci'][1]})", STUDY, link))
    r = eff["crc_death"]["rr"]
    parts.append(f"Lowers your chance of dying of colorectal cancer by about **{rel(r)}%**"
                 + (f" (from {pct(mort)} to {pct(mort * r)} over 10 years)" if mort is not None else ""))
    if mort is not None:
        more.append(compare_block(mort, r, "crc_death"))
        rows.append(row(f"With the test: {pct(mort * r)} chance of dying of it", CALC, "Your chance × the trial's effect."))
    rows.append(row(f"Deaths from colorectal cancer: {rel(r)}% lower (95% CI {eff['crc_death']['ci'][0]}–{eff['crc_death']['ci'][1]})",
                    STUDY, link))
    head = (f"{name}:", parts + ["Has **not been shown to add years** of life overall"])
    if test == "fobt":
        a = t["all_cause"]
        more += [{"type": "text", "html": md(f"Deaths from any cause were **unchanged** in the trial (relative risk {a['rr']:.2f}). "
                                             f"Testing every other year instead of every year gave a smaller benefit "
                                             f"({rel(t['biennial_crc_death']['rr'])}% fewer colorectal cancer deaths).")},
                 {"type": "text", "html": md(t["fit_note"])},
                 {"type": "caption", "html": md("A positive stool test is followed by a colonoscopy. Numbers are for everyone "
                                                "invited to screening, including people who never did the test, followed for "
                                                "30 years; here the effect is applied to your next 10.")}]
    else:
        more += [{"type": "text", "html": md("Sigmoidoscopy looks at the lower third of the colon with a short scope, usually "
                                             "without sedation. Anything suspicious is followed by a full colonoscopy.")},
                 {"type": "caption", "html": md(f"Numbers are for everyone invited to screening ({t['attendance']}), followed "
                                                "for 15 years; the benefit for people who actually went is larger.")}]
    if not in_range:
        more.insert(0, {"type": "caption", "html": md("Your own starting chance isn't shown because the registry rates we use "
                                                      "cover ages 45 to 75.")})
    more.append({"type": "caption", "html": f"Source: {link}. {checked_note(t)}"})
    return wrap(head, more, rows)


def prediction_blocks(topic: Topic, api: dict | None) -> list[dict]:
    pred = (api or {}).get("prediction")
    if not pred:
        return [{"type": "text", "html": "The prediction service isn't connected yet, so here is what the trials found."}]
    out = [{"type": "stat", "big": f"about {pred['per_100']}", "label": "out of 100 people like you"}]
    if topic.id == "prostate":
        out.append({"type": "caption", "html": "Chance of a PSA of 4.0 or higher, the level that usually leads to a "
                    "biopsy. This is a test result, not a cancer diagnosis."})
    return out


def psa_detail(topic: Topic, api: dict | None) -> list[dict]:
    ev = {str(e["_file"]): e for e in load_evidence(topic)}
    erspc = next(e for f, e in ev.items() if "erspc_2025" in f)
    life = next(e for f, e in ev.items() if "heijnsdijk" in f)
    red = erspc["numbers"]["relative_reduction_pct"]["value"]
    ly = life["numbers"]["life_years_gained_per_1000"]["value"]
    weeks = round(ly / 1000 * 52)
    head = ("Getting regular PSA tests:", [
        f"Lowers your chance of dying of prostate cancer by about **{red}%**",
        f"Adds about **{weeks} weeks** of life on average ({ly} years of life per 1,000 men screened)",
        f"Downside: for each death prevented, about **{erspc['numbers']['number_needed_to_diagnose']['value']}** more men "
        "are diagnosed with prostate cancer, and some of those cancers would never have harmed them"])
    pred = (api or {}).get("prediction")
    rows = [row(f"Prostate cancer deaths: {red}% lower", STUDY, src_link(erspc["source"], erspc["url"])),
            row(f"Years of life: {ly} per 1,000 men", STUDY, src_link(life["source"], life["url"]) + " (a model fitted to the trial)")]
    if pred:
        rows.insert(0, row(f"Your chance of a PSA of 4.0 or higher: about {pred['per_100']} in 100", MODEL,
                           "Logistic regression trained on NHANES 2001–2008 (test AUC 0.66, no better than age alone)."))
    more = prediction_blocks(topic, api) + [{"type": "heading", "html": "What the research found"}] + evidence_blocks(topic)
    return wrap(head, more, rows)


def option_detail(topic: Topic, option: flowchart.Option, p: dict, api: dict | None) -> list[dict]:
    if topic.id == "heart":
        return heart_detail(option.id, p, api)
    if topic.id == "colorectal" and option.id in ("fobt", "sigmoidoscopy"):
        return colon_test_detail(p, option.id)
    if topic.id == "colorectal" and colon_risk.in_range(float(p["age"])):
        return colon_detail(p, topic)
    if topic.id == "prostate":
        return psa_detail(topic, api)
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
