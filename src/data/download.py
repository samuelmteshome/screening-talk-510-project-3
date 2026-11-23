"""Download the raw NHANES files for a topic and record them in MANIFEST.json.

Usage:
    python -m src.data.download --topic prostate [--snapshot] [--force]

Each file listed under ``data.files`` in topics/<topic>.yaml is fetched from the
CDC (URL pattern in config.yaml), saved to data/raw/<topic>/<cycle>/, and logged
in data/raw/MANIFEST.json with its URL, download time, size and SHA-256.
``--snapshot`` also copies the raw files to a dated folder in the bucket.
An entry can be a full URL instead of a file name (e.g. linked mortality files).
"""
from __future__ import annotations

import argparse
import json
import logging
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import REPO_ROOT, load_config, load_topic, resolve_uri
from src.data import storage

log = logging.getLogger(__name__)
MANIFEST_PATH = REPO_ROOT / "data" / "raw" / "MANIFEST.json"
USER_AGENT = "screening-talk/0.1 (AIPI 510 course project)"


def file_url(entry: str, cycle: str, base_url: str) -> str:
    """URL for a file entry: a full URL is used as-is, a name uses the NHANES pattern."""
    if "://" in entry:
        return entry
    return base_url.format(start_year=cycle.split("-")[0], file=entry)


def local_name(entry: str) -> str:
    """File name on disk for a file entry."""
    return entry.rsplit("/", 1)[-1] if "://" in entry else f"{entry}.xpt"


def ssl_context() -> ssl.SSLContext:
    """Verify HTTPS with certifi's CA bundle when available.

    Some Python builds on macOS do not trust the certificate chain of
    ftp.cdc.gov (linked mortality files) with their default store.
    """
    try:
        import certifi
    except ImportError:  # pragma: no cover
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def fetch(url: str, dest: Path, retries: int = 3) -> None:
    """Download ``url`` to ``dest``, retrying on network errors."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response, open(tmp, "wb") as fh:
                fh.write(response.read())
            tmp.replace(dest)
            return
        except OSError as err:  # URLError and HTTPError are OSErrors
            log.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, err)
            if attempt == retries:
                raise
            time.sleep(2 * attempt)


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def save_manifest(manifest: dict[str, Any], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + "\n")


def download_topic(
    topic: str,
    config: dict[str, Any] | None = None,
    topic_cfg: dict[str, Any] | None = None,
    raw_dir: Path | None = None,
    manifest_path: Path = MANIFEST_PATH,
    force: bool = False,
    snapshot: bool = False,
) -> dict[str, Any]:
    """Download every raw file for ``topic``. Returns the updated manifest."""
    config = config or load_config()
    topic_cfg = topic_cfg or load_topic(topic)
    files = (topic_cfg.get("data") or {}).get("files")
    if not files:
        raise ValueError(f"topics/{topic}.yaml has no data.files: list the NHANES files per cycle")
    raw_dir = Path(raw_dir or REPO_ROOT / config["data"]["raw_dir"])
    base_url = config["data"]["nhanes_base_url"]
    manifest = load_manifest(manifest_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for cycle in topic_cfg["data"]["cycles"]:
        for entry in files[cycle]:
            url = file_url(entry, cycle, base_url)
            dest = raw_dir / topic / cycle / local_name(entry)
            key = f"{topic}/{cycle}/{local_name(entry)}"
            if dest.exists() and not force:
                log.info("Already downloaded: %s", dest)
            else:
                log.info("Downloading %s", url)
                fetch(url, dest)
                manifest[key] = {
                    "url": url,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "bytes": dest.stat().st_size,
                    "sha256": storage.sha256_file(dest),
                }
            if snapshot:
                uri = resolve_uri(config["data"]["raw_snapshot_uri"], config).format(
                    date=today, topic=topic, cycle=cycle, file=local_name(entry)
                )
                storage.put(dest, uri)
                manifest.setdefault(key, {})["snapshot_uri"] = uri
                log.info("Snapshot: %s", uri)

    save_manifest(manifest, manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", required=True)
    parser.add_argument("--force", action="store_true", help="re-download files already on disk")
    parser.add_argument("--snapshot", action="store_true", help="copy raw files to a dated bucket folder")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    download_topic(args.topic, force=args.force, snapshot=args.snapshot)


if __name__ == "__main__":
    main()
