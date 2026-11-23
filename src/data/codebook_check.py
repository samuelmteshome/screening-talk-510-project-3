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
    low = html.lower()
    start = low.find(f'id="{variable.lower()}"')
    if start < 0:
        start = low.find(variable.lower())
    if start < 0:
        raise ValueError(f"{variable} not found in codebook")
    nxt = re.search(r'<div[^>]+id="MCQ\w+"', html[start + 10:], re.I)
    section = html[start: start + 10 + nxt.start()] if nxt else html[start:]
    return {unescape(desc).strip().lower(): int(code) for code, desc in ROW.findall(section)}


def match_codes(found: dict[str, int], expected: dict[str, int]) -> dict[str, int | None]:
    """Code for each expected name. Labels can carry extra words, e.g. "Rectum (rectal)"."""
    return {name: next((c for d, c in found.items() if d == name or d.startswith(name + " ")), None)
            for name in expected}


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
    bad = unreadable = 0
    for cycle in cfg["data"]["cycles"]:
        mcq = next(f for f in cfg["data"]["files"][cycle] if f.startswith("MCQ"))
        url = file_url(mcq, cycle, base).replace(".xpt", ".htm").replace(".XPT", ".htm")
        html = ""
        try:
            html = fetch(url)
            found = codes_from_codebook(html)
        except (ValueError, OSError) as e:
            print(f"{cycle}: {e}")
            # Page did not hold the variable table (moved or rendered differently): report it, don't guess.
            title = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            print(f"{cycle}: MCQ230A table not found at {url} (page {len(html):,} chars, "
                  f"title {title.group(1).strip() if title else 'none'!r})")
            lines.append(f"| {cycle} | [{mcq}]({url}) | " + " | ".join("?" for _ in expected) + " | page not readable |")
            unreadable += 1
            continue
        got = match_codes(found, expected)
        ok = got == expected
        if not ok:
            print(f"{cycle}: labels near the expected ones: "
                  f"{ {d: c for d, c in found.items() if any(n[:4] in d for n in expected)} }")
        bad += not ok
        lines.append(f"| {cycle} | [{mcq}]({url}) | " + " | ".join(str(got[n]) for n in expected) + f" | {'yes' if ok else 'NO'} |")
    out = REPO_ROOT / "docs" / "cleaning" / f"{args.topic}_codes.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    # Fail on any real mismatch, or if no cycle could be checked at all.
    sys.exit(1 if bad or unreadable == len(cfg["data"]["cycles"]) else 0)


if __name__ == "__main__":
    main()
