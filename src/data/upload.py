"""Upload a topic's clean parquet to the bucket and record its SHA-256.

Usage:
    python -m src.data.upload --topic prostate [--write-hash]

Uploads data/clean/<topic>/clean.parquet to ``data.clean_uri`` in
topics/<topic>.yaml. ``--write-hash`` also writes the new SHA-256 into that
file, so ingest.py can refuse any other version of the data.
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any

from src.config import REPO_ROOT, load_config, load_topic, resolve_uri
from src.data import storage

log = logging.getLogger(__name__)


def write_hash(topic_yaml: Path, sha256: str) -> None:
    """Replace the clean_sha256 value in a topic YAML, keeping its comments."""
    text = topic_yaml.read_text()
    new, n = re.subn(r"(?m)^(\s*clean_sha256:\s*)\S+", rf"\g<1>{sha256}", text, count=1)
    if n != 1:
        raise ValueError(f"No clean_sha256 line in {topic_yaml}")
    topic_yaml.write_text(new)


def upload_topic(
    topic: str,
    config: dict[str, Any] | None = None,
    topic_cfg: dict[str, Any] | None = None,
    clean_dir: Path | None = None,
) -> tuple[str, str]:
    """Upload the clean file for ``topic``. Returns (uri, sha256)."""
    config = config or load_config()
    topic_cfg = topic_cfg or load_topic(topic)
    clean_dir = Path(clean_dir or REPO_ROOT / config["data"]["clean_dir"])
    local = clean_dir / topic / "clean.parquet"
    if not local.exists():
        raise FileNotFoundError(f"{local} not found: run `python -m src.data.clean --topic {topic}`")
    uri = resolve_uri(topic_cfg["data"]["clean_uri"], config)
    sha = storage.sha256_file(local)
    storage.put(local, uri)
    return uri, sha


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", required=True)
    parser.add_argument("--write-hash", action="store_true", help="write the SHA-256 into topics/<topic>.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uri, sha = upload_topic(args.topic)
    print(f"clean_uri: {uri}\nclean_sha256: {sha}")
    if args.write_hash:
        write_hash(REPO_ROOT / "topics" / f"{args.topic}.yaml", sha)
        log.info("Updated clean_sha256 in topics/%s.yaml: commit this change", args.topic)


if __name__ == "__main__":
    main()
