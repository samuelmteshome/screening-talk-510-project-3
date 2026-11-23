"""Published trial results for each topic, read from evidence/*.json.

These numbers are shown next to the model's prediction, never multiplied into it.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from src.config import REPO_ROOT

EVIDENCE_DIR = REPO_ROOT / "evidence"
FILES: dict[str, tuple[str, ...]] = {
    "prostate": ("erspc_2025.json", "erspc_metastatic_2012.json", "heijnsdijk_lifeyears_2012.json"),
    "heart": ("hope3_2016.json", "heart_actions.json"),
    "colorectal": ("nordicc_2022.json",),
}


@lru_cache(maxsize=None)
def load(topic: str) -> tuple[dict[str, Any], ...]:
    """Evidence entries for a topic, each tagged with its file name. Missing files are skipped."""
    out = []
    for name in FILES.get(topic, ()):
        path = EVIDENCE_DIR / name
        if path.exists():
            out.append({"file": name, **json.loads(path.read_text())})
    return tuple(out)
