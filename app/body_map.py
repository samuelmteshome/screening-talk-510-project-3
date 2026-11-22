"""Animated body outline with clickable organs, drawn as inline SVG.

Each organ is a link that adds ?organ=<topic> to the app's URL. The map is shown
in a components.html iframe, so a small script replays each click as a link in
the parent page.
"""
from __future__ import annotations

from urllib.parse import urlencode

from catalog import Topic

# Organ outlines in a 300 x 600 drawing.
ORGAN_SHAPES = {
    "heart": '<path d="M162 175 c10-14 32-6 28 12 c-3 14-18 24-28 32 c-10-8-25-18-28-32 c-4-18 18-26 28-12z"/>',
    "colorectal": (
        '<path d="M112 270 h76 a14 14 0 0 1 14 14 v52 a14 14 0 0 1 -14 14 h-30 v14" '
        'fill="none" stroke-width="10" stroke-linecap="round"/>'
        '<path d="M112 270 a14 14 0 0 0 -14 14 v52 a14 14 0 0 0 14 14 h20" '
        'fill="none" stroke-width="10" stroke-linecap="round"/>'
    ),
    "prostate": '<ellipse cx="150" cy="388" rx="13" ry="9"/>',
}

LABEL_POS = {"heart": (222, 175), "colorectal": (232, 300), "prostate": (182, 395)}

BODY = {
    "male": (
        '<circle cx="150" cy="60" r="34"/>'
        '<path d="M150 96 v12 M108 120 q42-18 84 0 l22 10 q14 6 16 22 l10 150 q2 14-10 16 '
        'l-8-150 -12 8 v150 q2 20-10 30 l-8 190 h-28 l-6-170 h-8 l-6 170 h-28 l-8-190 '
        'q-12-10-10-30 v-150 l-12-8 -8 150 q-12-2-10-16 l10-150 q2-16 16-22z"/>'
    ),
    "female": (
        '<circle cx="150" cy="60" r="32"/>'
        '<path d="M150 94 v12 M114 118 q36-16 72 0 l20 10 q12 6 14 22 l10 150 q2 14-10 16 '
        'l-8-150 -10 8 q-4 40 4 70 q14 40 6 80 l-10 180 h-28 l-6-170 h-8 l-6 170 h-28 l-10-180 '
        'q-8-40 6-80 q8-30 4-70 l-10-8 -8 150 q-12-2-10-16 l10-150 q2-16 14-22z"/>'
    ),
}

CSS = """
<style>
.st-body {display:flex; justify-content:center;}
.st-body svg {max-width: 400px; width: 100%; height: auto;}
.st-body .outline {fill: none; stroke: #6b7280; stroke-width: 3;
  stroke-dasharray: 2400; stroke-dashoffset: 2400; animation: st-draw 1.6s ease-out forwards;}
.st-body .organ {fill: #fca5a5; stroke: #b91c1c; stroke-width: 3; opacity: 0;
  animation: st-fade .6s ease-out forwards, st-pulse 2.4s ease-in-out 2.2s infinite;
  transform-box: fill-box; transform-origin: center; cursor: pointer;}
.st-body .organ.colorectal path {stroke: #b45309;}
.st-body .organ.colorectal {fill: none;}
.st-body .organ.off {fill: #e5e7eb; stroke: #9ca3af; stroke-dasharray: 6 4;}
.st-body .organ.colorectal.off path {stroke: #9ca3af;}
.st-body a:hover .organ {fill: #ef4444; stroke-width: 5;}
.st-body a:focus .organ {outline: none; stroke: #1d4ed8; stroke-width: 5;}
.st-body text {font: 600 15px sans-serif; fill: #111827; opacity: 0;
  animation: st-fade .6s ease-out 1.6s forwards;}
.st-body text .note {font-weight: 400; font-size: 13px; fill: #6b7280;}
@keyframes st-draw {to {stroke-dashoffset: 0;}}
@keyframes st-fade {to {opacity: 1;}}
@keyframes st-pulse {0%,100% {transform: scale(1);} 50% {transform: scale(1.08);}}
@media (prefers-reduced-motion: reduce) {
  .st-body .outline, .st-body .organ, .st-body text {animation: none; opacity: 1; stroke-dashoffset: 0;}
}
</style>
"""


def organ_link(params: dict, topic_id: str) -> str:
    return "?" + urlencode({**params, "organ": topic_id})


def render(sex: str, topics: list[Topic], params: dict, ineligible: frozenset[str] = frozenset()) -> str:
    """HTML for components.html(): body outline plus one link per organ.

    Organs in `ineligible` are drawn grey and dashed; clicking still opens the
    page that explains why there is no number.
    """
    parts = [CSS, '<div class="st-body"><svg viewBox="-30 0 400 600" role="img" '
             f'aria-label="Body map, {sex}">']
    parts.append(f'<g class="outline">{BODY[sex]}</g>')
    for i, t in enumerate(topics):
        delay = 1.2 + 0.25 * i
        x, y = LABEL_POS[t.id]
        parts.append(
            f'<a href="{organ_link(params, t.id)}" data-q="{organ_link(params, t.id)}" target="_top" '
            f'aria-label="{t.organ}: {t.tool}">'
            f'<title>{t.organ}: {t.tool}</title>'
            f'<g class="organ {t.id}{" off" if t.id in ineligible else ""}" style="animation-delay:{delay}s, {delay + 1}s">{ORGAN_SHAPES[t.id]}</g>'
            f'<text x="{x}" y="{y}">{t.organ}'
            + (f'<tspan x="{x}" dy="16" class="note">not for you</tspan>' if t.id in ineligible else "")
            + '</text></a>'
        )
    parts.append("</svg></div>")
    # Streamlit's iframe sandbox blocks direct top-level navigation, so the
    # click is replayed as a link click inside the parent page (same origin).
    parts.append(
        "<script>for (const a of document.querySelectorAll('a[data-q]')) {"
        "a.addEventListener('click', (ev) => { try {"
        "const d = window.parent.document, link = d.createElement('a');"
        "link.href = window.parent.location.pathname + a.dataset.q; link.target = '_self';"
        "d.body.appendChild(link); link.click(); ev.preventDefault(); } catch (e) {} }); }</script>"
    )
    return "".join(parts)
