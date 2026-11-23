"""Load a topic's clean data from the cloud and check it is the expected version.

Training calls ``load_clean(topic)``: it downloads ``data.clean_uri`` to
data/cache/, compares its SHA-256 with ``data.clean_sha256`` in the topic YAML,
and checks the columns in docs/data_contract.md. Any mismatch stops the run.

Usage (quick check):
    python -m src.data.ingest --topic prostate
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import REPO_ROOT, load_config, load_topic, resolve_uri
from src.data import storage

log = logging.getLogger(__name__)
CONTRACT_COLUMNS = ["SEQN", "cycle", "target", "exam_weight"]


class DataIntegrityError(RuntimeError):
    """The data does not match the recorded hash or the data contract."""


def _hash_is_set(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and not value.startswith("<")


def check_contract(df: pd.DataFrame, features: list[str]) -> None:
    """Raise if columns from the data contract or the topic's features are missing."""
    missing = [c for c in CONTRACT_COLUMNS + list(features) if c not in df.columns]
    if missing:
        raise DataIntegrityError(f"Clean data is missing columns {missing} (see docs/data_contract.md)")
    if not set(df["target"].unique()) <= {0, 1}:
        raise DataIntegrityError("target must be 0 or 1")
    if df["SEQN"].duplicated().any():
        raise DataIntegrityError("SEQN must be unique (one row per participant)")


def load_clean(
    topic: str,
    config: dict[str, Any] | None = None,
    topic_cfg: dict[str, Any] | None = None,
    cache_dir: Path | None = None,
    uri: str | None = None,
    allow_unverified: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return (data, info) for ``topic``; info holds the URI, SHA-256 and row count.

    ``uri`` overrides data.clean_uri (e.g. a local file during development).
    ``allow_unverified`` lets a run continue when no hash is recorded yet; it
    never allows a hash mismatch.
    """
    config = config or load_config()
    topic_cfg = topic_cfg or load_topic(topic)
    data_cfg = topic_cfg["data"]
    uri = uri or resolve_uri(data_cfg["clean_uri"], config)
    cache_dir = Path(cache_dir or REPO_ROOT / config["data"]["cache_dir"])
    local = storage.get(uri, cache_dir / topic / data_cfg.get("version", "v1") / "clean.parquet")

    actual = storage.sha256_file(local)
    expected = data_cfg.get("clean_sha256")
    if _hash_is_set(expected):
        if actual != expected:
            raise DataIntegrityError(
                f"{uri} has SHA-256 {actual}, but topics/{topic}.yaml expects {expected}. "
                "The data changed: re-run the data pipeline or update the hash on purpose."
            )
    elif not allow_unverified:
        raise DataIntegrityError(
            f"No clean_sha256 recorded in topics/{topic}.yaml. "
            f"Run `python -m src.data.upload --topic {topic} --write-hash` first."
        )
    else:
        log.warning("No recorded hash for %s; using unverified data (sha256 %s)", topic, actual)

    df = pd.read_parquet(local)
    check_contract(df, topic_cfg["features"])
    info = {"uri": uri, "sha256": actual, "rows": len(df), "verified": _hash_is_set(expected)}
    log.info("Loaded %s: %d rows, sha256 %s", uri, len(df), actual)
    return df, info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df, info = load_clean(args.topic)
    print(info)
    print(df.groupby("cycle")["target"].agg(["count", "mean"]))


if __name__ == "__main__":
    main()
