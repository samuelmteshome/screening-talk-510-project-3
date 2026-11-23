"""Check the colon / rectum cancer codes in topics/colorectal.yaml against the NHANES codebooks.

Usage:
    python -m src.data.codebook_check --topic colorectal

For each cycle, downloads the MCQ codebook page (.htm next to the .xpt), reads
the value table for MCQ230A, and checks that the codes for "Colon" and "Rectum"
match ``data.cancer_type_codes``. Writes docs/cleaning/colorectal_codes.md and
exits non-zero on any mismatch, so the workflow stops before cleaning.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from html import unescape

from src.config import REPO_ROOT, load_config, load_topic
from src.data.download import USER_AGENT, file_url

ROW = re.compile(r"<td[^>]*>\s*(\d+)\s*</td>\s*<td[^>]*>\s*([^<]+?)\s*</td>", re.I)


def codes_from_codebook(html: str, variable: str = "MCQ230A") -> dict[str, int]:
    """Value description (lower case) -> code, from the variable's value table."""
    start = html.find(f'id="{variable}"')
    if start < 0:
        start = html.find(variable)
    if start < 0:
        raise ValueError(f"{variable} not found in codebook")
    nxt = re.search(r'<div[^>]+id="MCQ\w+"', html[start + 10:])
    section = html[start: start + 10 + nxt.start()] if nxt else html[start:]
    return {unescape(desc).strip().lower(): int(code) for code, desc in ROW.findall(section)}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", default="colorectal")
    args = parser.parse_args()
    cfg, base = load_topic(args.topic), load_config()["data"]["nhanes_base_url"]
    expected = cfg["data"]["cancer_type_codes"]
    lines = ["# Cancer type codes checked against the NHANES codebooks", "",
             "| Cycle | File | " + " | ".join(n.title() for n in expected) + " | OK |", "| --- " * (len(expected) + 3) + "|"]
    bad = 0
    for cycle in cfg["data"]["cycles"]:
        mcq = next(f for f in cfg["data"]["files"][cycle] if f.startswith("MCQ"))
        url = file_url(mcq, cycle, base).replace(".xpt", ".htm").replace(".XPT", ".htm")
        found = codes_from_codebook(fetch(url))
        got = {name: found.get(name) for name in expected}
        ok = got == expected
        bad += not ok
        lines.append(f"| {cycle} | [{mcq}]({url}) | " + " | ".join(str(got[n]) for n in expected) + f" | {'yes' if ok else 'NO'} |")
    out = REPO_ROOT / "docs" / "cleaning" / f"{args.topic}_codes.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
