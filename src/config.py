"""Load config.yaml and topics/<topic>.yaml, and resolve placeholders.

Placeholders such as ``<bucket>`` in URIs are filled from the GCS_BUCKET
environment variable (or ``storage.bucket`` in config.yaml), so the YAML files
can stay in Git without project-specific values.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

try:  # .env is optional; values already in the environment win.
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Read a YAML file into a dict."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Return the project-wide config (config.yaml)."""
    return load_yaml(path or REPO_ROOT / "config.yaml")


def load_topic(topic: str, topics_dir: str | Path | None = None) -> dict[str, Any]:
    """Return the config for one topic (topics/<topic>.yaml)."""
    path = Path(topics_dir or REPO_ROOT / "topics") / f"{topic}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No topic config at {path}")
    return load_yaml(path)


def bucket_name(config: dict[str, Any]) -> str | None:
    """GCS bucket from the environment, else config.yaml; None if unset."""
    value = os.environ.get("GCS_BUCKET") or (config.get("storage") or {}).get("bucket")
    if not value or value.startswith("<"):
        return None
    return value


def resolve_uri(uri: str, config: dict[str, Any]) -> str:
    """Fill ``<bucket>`` in a URI. Raises if a gs:// URI still has no bucket."""
    if "<bucket>" in uri:
        bucket = bucket_name(config)
        if bucket is None:
            raise ValueError(
                f"{uri} needs a bucket: set GCS_BUCKET in .env or storage.bucket in config.yaml"
            )
        uri = uri.replace("<bucket>", bucket)
    return uri


def cycle_in_range(cycle: str, key: str) -> bool:
    """True if a survey cycle such as '2003-2004' falls inside a key.

    A key is 'all', a single cycle ('2003-2004'), or a span of years
    ('2001-2004' covers 2001-2002 and 2003-2004).
    """
    if key == "all":
        return True
    start, end = (int(x) for x in cycle.split("-"))
    key_start, key_end = (int(x) for x in key.split("-"))
    return key_start <= start and end <= key_end


def source_variable(feature_sources: dict[str, dict[str, str]], column: str, cycle: str) -> str:
    """NHANES variable name for a column in a given cycle (from feature_sources)."""
    options = feature_sources.get(column)
    if not options:
        raise KeyError(f"'{column}' has no entry in feature_sources")
    matches = [var for key, var in options.items() if cycle_in_range(cycle, key)]
    if len(matches) != 1:
        raise KeyError(
            f"'{column}' needs exactly one NHANES variable for {cycle}, found {matches}"
        )
    return matches[0]
