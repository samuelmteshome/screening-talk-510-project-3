"""Mind-map style flowchart for one organ: organ -> Medications / Screening -> options.

Only options we have data for are listed. Each node is a link that adds
?branch= and ?action= to the URL, so the search box can open the chart at
any option and the browser back button still works.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import urlencode

from body_map import CLICK_SCRIPT, ORGANS
from catalog import TOPICS, topics_for

BRANCHES = {"medications": "Medications", "lifestyle": "Lifestyle", "screening": "Screening"}


@dataclass(frozen=True)
class Option:
    id: str            # matches ?action= (and heart_actions.ACTIONS for heart)
    topic: str
    branch: str        # key of BRANCHES
    label: str
    aliases: tuple[str, ...] = ()


OPTIONS: tuple[Option, ...] = (
    Option("statin", "heart", "medications", "Statin (cholesterol medicine)",
           ("statin", "cholesterol", "atorvastatin", "rosuvastatin", "simvastatin", "lipitor", "crestor")),
    Option("bp", "heart", "medications", "Blood pressure medicine",
           ("blood pressure", "hypertension", "lisinopril", "amlodipine", "bp")),
    Option("aspirin", "heart", "medications", "Low-dose aspirin", ("aspirin", "baby aspirin")),
    Option("quit_smoking", "heart", "lifestyle", "Quit smoking",
           ("quit smoking", "smoking", "stop smoking", "cigarettes", "smoking cessation", "nicotine")),
    Option("exercise", "heart", "lifestyle", "Regular exercise",
           ("exercise", "physical activity", "walking", "running", "workout", "weights", "strength training")),
    Option("weight_loss", "heart", "lifestyle", "Weight loss",
           ("weight loss", "lose weight", "diet", "obesity", "bmi")),
    Option("checkups", "heart", "screening", "Regular checkups",
           ("checkup", "check-up", "primary care", "physical", "annual exam", "heart screening")),
    Option("psa", "prostate", "screening", "PSA blood test",
           ("psa", "prostate exam", "prostate specific antigen", "prostate cancer screening")),
    Option("colonoscopy", "colorectal", "screening", "Colonoscopy",
           ("colonoscopy", "colon cancer screening", "bowel screening", "colorectal screening")),
)


def options_for(topic_id: str) -> dict[str, list[Option]]:
    """Branches with at least one option, in display order."""
    out: dict[str, list[Option]] = {}
    for b in BRANCHES:
        opts = [o for o in OPTIONS if o.topic == topic_id and o.branch == b]
        if opts:
            out[b] = opts
    return out


def find_option(topic_id: str, option_id: str | None) -> Option | None:
    return next((o for o in OPTIONS if o.topic == topic_id and o.id == option_id), None)


@dataclass(frozen=True)
class Match:
    label: str         # shown under the search box
    topic: str
    branch: str | None = None
    action: str | None = None


def search(query: str, sex: str) -> list[Match]:
    """Options and organs matching the query, best first (exact name, then starts-with, then contains)."""
    q = query.strip().lower()
    if len(q) < 2:
        return []
    allowed = {t.id for t in topics_for(sex)}
    scored: list[tuple[int, Match]] = []
    for o in OPTIONS:
        if o.topic not in allowed:
            continue
        names = (o.label.lower(), o.id, *o.aliases)
        score = min((0 if n == q else 1 if n.startswith(q) else 2 if q in n else 9) for n in names)
        if score < 9:
            organ = TOPICS[o.topic].organ
            scored.append((score, Match(f"{o.label}  ·  {organ} › {BRANCHES[o.branch]}", o.topic, o.branch, o.id)))
    for t in topics_for(sex):
        names = (t.id, t.organ.lower())
        score = min((0 if n == q else 1 if n.startswith(q) else 9) for n in names)
        if score < 9:
            scored.append((score, Match(f"{t.organ}  ·  all options", t.id)))
    for b, name in BRANCHES.items():
        if name.lower().startswith(q):
            for t in topics_for(sex):
                if b in options_for(t.id):
                    scored.append((3, Match(f"{name}  ·  {t.organ}", t.id, b)))
    seen, out = set(), []
    for _, m in sorted(scored, key=lambda s: s[0]):
        key = (m.topic, m.branch, m.action)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


# ---------- drawing ----------
W = 940
COL = {"root": (20, 190), "branch": (290, 210), "leaf": (590, 330)}   # x, width
NODE_H = 56
LEAF_GAP = 72
BRANCH_GAP = 96

CSS = """
<style>
body { margin:0; font-family: "Source Sans Pro", -apple-system, "Segoe UI", sans-serif; }
svg { width:100%; height:auto; overflow:visible; }
a { cursor:pointer; outline:none; }
.node rect.box { stroke-width:2; transition: filter .15s, stroke-width .15s; }
a:hover rect.box, a:focus rect.box { stroke-width:3.5; filter: drop-shadow(0 4px 10px rgba(15,23,42,.15)); }
.node text { font-size:18px; fill:#0f172a; dominant-baseline:middle; }
.root text { font-size:22px; font-weight:700; fill:#fff; }
.branch text { font-weight:700; }
.leaf.sel rect.box { stroke-width:3.5; }
.leaf.sel text { font-weight:700; }
.chev circle { fill:#fff; stroke-width:2; }
.node .chev text { font-size:18px; font-weight:700; text-anchor:middle; dominant-baseline:central; }
.edge { fill:none; stroke:#cbd5e1; stroke-width:2.5; }
.grow { opacity:0; animation: grow .45s ease-out forwards; }
@keyframes grow { from { opacity:0; transform: translateX(-14px); } to { opacity:1; transform:none; } }
</style>
"""


def _link(params: dict, **change) -> str:
    q = {k: v for k, v in params.items() if k not in ("branch", "action")}
    q.update({k: v for k, v in change.items() if v})
    return "?" + urlencode(q)


def _edge(x1: float, y1: float, x2: float, y2: float, delay: float = 0) -> str:
    mx = (x1 + x2) / 2
    cls = ' class="edge grow"' if delay else ' class="edge"'
    style = f' style="animation-delay:{delay:.2f}s"' if delay else ""
    return f'<path{cls}{style} d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}"/>'


def _node(kind: str, x: float, y: float, w: float, label: str, href: str, color: str, *,
          fill: str, stroke: str, chevron: str = "", selected: bool = False, delay: float = 0) -> str:
    cls = f"node {kind}" + (" sel" if selected else "")
    grow = f' class="grow" style="animation-delay:{delay:.2f}s"' if delay else ""
    chev = ""
    if chevron:
        cx = x + w
        chev = (f'<g class="chev"><circle cx="{cx}" cy="{y}" r="15" stroke="{color}"/>'
                f'<text x="{cx}" y="{y + 1}" fill="{color}">{chevron}</text></g>')
    return (f'<g{grow}><a data-q="{escape(href)}" href="{escape(href)}" tabindex="0" aria-label="{escape(label)}">'
            f'<g class="{cls}"><rect class="box" x="{x}" y="{y - NODE_H / 2}" width="{w}" height="{NODE_H}" '
            f'rx="16" fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{x + 20}" y="{y + 1}">{escape(label)}</text>{chev}</g></a></g>')


def render(topic_id: str, params: dict, branch: str | None, action: str | None) -> tuple[str, int]:
    """HTML for the chart and the iframe height it needs."""
    topic = TOPICS[topic_id]
    color = ORGANS.get(topic_id, {}).get("color", "#0f766e")
    tint = color + "1a"          # ~10% alpha
    tree = options_for(topic_id)
    open_leaves = tree.get(branch, []) if branch else []

    n_rows = max(len(tree) * BRANCH_GAP, len(open_leaves) * LEAF_GAP)
    h = max(n_rows, 120) + 40
    mid = h / 2

    rx, rw = COL["root"]
    bx, bw = COL["branch"]
    lx, lw = COL["leaf"]
    parts = []

    b_ys = {b: mid + (i - (len(tree) - 1) / 2) * BRANCH_GAP for i, b in enumerate(tree)}
    for b, y in b_ys.items():
        parts.append(_edge(rx + rw, mid, bx, y))
    parts.append(_node("root", rx, mid, rw, topic.organ, _link(params), color,
                       fill=color, stroke=color))

    for b, y in b_ys.items():
        is_open = b == branch
        href = _link(params) if is_open else _link(params, branch=b)
        parts.append(_node("branch", bx, y, bw, BRANCHES[b], href, color, fill=tint if is_open else "#fff",
                           stroke=color, chevron="‹" if is_open else "›"))

    if open_leaves:
        y0 = b_ys[branch]
        for i, o in enumerate(open_leaves):
            y = mid + (i - (len(open_leaves) - 1) / 2) * LEAF_GAP
            delay = 0.05 + i * 0.07
            parts.append(_edge(bx + bw + 15, y0, lx, y, delay))
            parts.append(_node("leaf", lx, y, lw, o.label, _link(params, branch=branch, action=o.id), color,
                               fill=tint if o.id == action else "#fff", stroke=color if o.id == action else "#cbd5e1",
                               selected=o.id == action, delay=delay))

    svg = (f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{escape(topic.organ)} options">'
           + "".join(parts) + "</svg>")
    height = int(h * 700 / W) + 30   # iframe is ~700 px wide in Streamlit's centered layout
    return CSS + svg + CLICK_SCRIPT, height
