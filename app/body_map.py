"""Anatomical body map with clickable organs (inline SVG + CSS animation).

Artwork (see app/assets/LICENSES.md):
- body: front-view male and female figures from react-native-body-highlighter (MIT)
- organs: Health Icons (CC0)

Each organ links to ?organ=<topic>. The map is shown in a components.html
iframe, so a small script replays each click as a link in the parent page.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from catalog import Topic

ASSETS = Path(__file__).resolve().parent / "assets"

# Organ glyph, colour, centre (x, y) and size in each figure's coordinates.
ORGANS = {
    "heart": {"icon": "heart-organ", "color": "#e11d48",
              "male": (392, 398, 92), "female": (346, 402, 86)},
    "colorectal": {"icon": "intestine", "color": "#d97706",
                   "male": (364, 562, 168), "female": (320, 560, 160)},
    "prostate": {"icon": "prostate", "color": "#7c3aed",
                 "male": (364, 712, 58)},
}

# Visible area per figure (room on the right for the callout labels).
VIEW = {"male": (20, 110, 1060, 1260), "female": (-30, 70, 1060, 1400)}
LABEL_X = {"male": 720, "female": 690}

CSS = """
<style>
:root { --ink:#0f172a; --muted:#64748b; }
body { margin:0; font-family: "Source Sans Pro", -apple-system, "Segoe UI", sans-serif; }
.map { display:flex; justify-content:center; }
.map svg { width:100%; max-width:560px; height:auto; overflow:visible; }
.figure { opacity:0; transform: translateY(24px); animation: rise .9s cubic-bezier(.2,.7,.2,1) forwards; }
.silhouette { fill:#f4e7dd; stroke:#d8c3b4; stroke-width:3; }
.muscle { fill:#ecd9cb; stroke:#fbf6f2; stroke-width:4; stroke-linejoin:round; }
.muscle.hair { fill:#8a7464; stroke:none; }
.organ-link { cursor:pointer; outline:none; }
.organ { opacity:0; animation: pop .55s cubic-bezier(.3,1.6,.5,1) forwards; transform-box: fill-box; transform-origin:center; }
.glyph { transition: transform .2s ease; transform-box: fill-box; transform-origin:center; filter: drop-shadow(0 6px 10px rgba(15,23,42,.18)); }
.halo { transform-box: fill-box; transform-origin:center; animation: ring 2.6s ease-out infinite; }
.organ-link:hover .glyph, .organ-link:focus .glyph { transform: scale(1.12); }
.organ-link:hover .pill, .organ-link:focus .pill { stroke-width:4; }
.leader { stroke:#94a3b8; stroke-width:2.5; stroke-dasharray:6 6; fill:none; }
.pill { fill:#fff; stroke:#e2e8f0; stroke-width:2.5; filter: drop-shadow(0 4px 10px rgba(15,23,42,.08)); transition: stroke-width .15s; }
.label { font-weight:700; font-size:34px; fill:var(--ink); }
.sub { font-size:23px; fill:var(--muted); }
.callout { opacity:0; animation: fade .5s ease-out forwards; }
.off .glyph { fill:#cbd5e1 !important; filter:none; }
.off .halo { display:none; }
.off .label { fill:#94a3b8; }
@keyframes rise { to { opacity:1; transform:none; } }
@keyframes pop { from { opacity:0; transform:scale(.4); } to { opacity:1; transform:scale(1); } }
@keyframes fade { to { opacity:1; } }
@keyframes ring { 0% { transform:scale(.7); opacity:.35; } 80%,100% { transform:scale(1.45); opacity:0; } }
@media (prefers-reduced-motion: reduce) {
  .figure, .organ, .callout { animation:none; opacity:1; transform:none; }
  .halo { animation:none; opacity:.25; }
}
</style>
"""

CLICK_SCRIPT = (
    "<script>for (const a of document.querySelectorAll('a[data-q]')) {"
    "a.addEventListener('click', (ev) => { try {"
    "const d = window.parent.document, link = d.createElement('a');"
    "link.href = window.parent.location.pathname + a.dataset.q; link.target = '_self';"
    "d.body.appendChild(link); link.click(); ev.preventDefault(); } catch (e) {} }); }</script>"
)


@lru_cache(maxsize=None)
def figure(sex: str) -> dict:
    return json.loads((ASSETS / f"body_{sex}_front.json").read_text())


@lru_cache(maxsize=None)
def glyph_paths(icon: str) -> str:
    """Inner <path> elements of a Health Icons SVG (24 x 24)."""
    svg = (ASSETS / "organs" / f"{icon}.svg").read_text()
    paths = re.findall(r"<path[^>]*/>", svg)
    return "".join(p.replace('fill="currentColor"', "") for p in paths)


def organ_link(params: dict, topic_id: str) -> str:
    return "?" + urlencode({**params, "organ": topic_id})


def _body(sex: str) -> str:
    fig = figure(sex)
    parts = [f'<path class="silhouette" d="{fig["outline"]}"/>']
    for part in fig["parts"]:
        cls = "muscle hair" if part["slug"] == "hair" else "muscle"
        parts += [f'<path class="{cls}" d="{d}"/>' for d in part["paths"]]
    return f'<g class="figure">{"".join(parts)}</g>'


def _organ(sex: str, t: Topic, i: int, off: bool, params: dict | None) -> str:
    """One organ glyph and callout. params=None: no link, the page's script handles the click."""
    spec = ORGANS[t.id]
    cx, cy, size = spec[sex]
    color = spec["color"]
    delay = 0.7 + 0.18 * i
    scale = size / 24
    lx = LABEL_X[sex]
    note = "Not covered for you" if off else t.tool
    if params is None:
        target = f'data-organ="{t.id}" tabindex="0" role="button"'
    else:
        q = escape(organ_link(params, t.id))
        target = f'href="{q}" data-q="{q}" target="_top"'
    pill_w = max(len(t.organ) * 21, len(note) * 12.5) + 85
    return (
        f'<a class="organ-link{" off" if off else ""}" {target} '
        f'aria-label="{escape(t.organ)}: {escape(note)}"><title>{escape(t.organ)}: {escape(note)}</title>'
        f'<g class="organ" style="animation-delay:{delay:.2f}s">'
        f'<circle class="halo" cx="{cx}" cy="{cy}" r="{size * 0.62:.0f}" fill="{color}" '
        f'style="animation-delay:{delay + 0.6:.2f}s"/>'
        f'<g class="glyph" fill="{color}"><g transform="translate({cx - size / 2:.1f} {cy - size / 2:.1f}) scale({scale:.3f})">'
        f'{glyph_paths(spec["icon"])}</g></g></g>'
        f'<g class="callout" style="animation-delay:{delay + 0.25:.2f}s">'
        f'<path class="leader" d="M{cx + size * 0.55:.0f} {cy} H{lx}"/>'
        f'<rect class="pill" x="{lx}" y="{cy - 46}" rx="22" width="{pill_w:.0f}" height="92"/>'
        f'<circle cx="{lx + 30}" cy="{cy}" r="9" fill="{"#cbd5e1" if off else color}"/>'
        f'<text class="label" x="{lx + 52}" y="{cy - 4}">{escape(t.organ)}</text>'
        f'<text class="sub" x="{lx + 52}" y="{cy + 28}">{escape(note)}</text></g></a>'
    )


def render(sex: str, topics: list[Topic], params: dict, ineligible: frozenset[str] = frozenset()) -> str:
    """HTML for components.html(): anatomical figure plus one link per organ.

    Organs in `ineligible` are greyed out; clicking still opens the page that
    explains why there is no number.
    """
    x, y, w, h = VIEW[sex]
    organs = "".join(_organ(sex, t, i, t.id in ineligible, params) for i, t in enumerate(topics))
    who = "man" if sex == "male" else "woman"
    return (
        CSS
        + f'<div class="map"><svg viewBox="{x} {y} {w} {h}" role="img" '
        f'aria-label="Front view of a {who}; click an organ to see results">'
        + _body(sex) + organs + "</svg></div>" + CLICK_SCRIPT
    )


def inline(sex: str, topics: list[Topic], ineligible: frozenset[str] = frozenset()) -> str:
    """CSS + SVG of the figure with organs marked data-organ=<topic>, for the one-page explorer."""
    x, y, w, h = VIEW[sex]
    organs = "".join(_organ(sex, t, i, t.id in ineligible, None) for i, t in enumerate(topics))
    who = "man" if sex == "male" else "woman"
    return (CSS + f'<div class="map"><svg viewBox="{x} {y} {w} {h}" role="img" '
            f'aria-label="Front view of a {who}; click an organ">' + _body(sex) + organs + "</svg></div>")
