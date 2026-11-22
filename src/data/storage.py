"""Copy files to and from Google Cloud Storage.

``gs://bucket/path`` URIs go through google-cloud-storage. Any other URI is
treated as a local path, which lets tests and offline runs use the same code.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_gs(uri: str) -> tuple[str, str]:
    bucket, _, blob = uri.removeprefix("gs://").partition("/")
    if not bucket or not blob:
        raise ValueError(f"Not a full gs:// object URI: {uri}")
    return bucket, blob


def _client():
    from google.cloud import storage  # imported lazily: not needed for local runs

    return storage.Client()


def put(local_path: str | Path, uri: str) -> str:
    """Upload a local file to ``uri`` (gs:// or local). Returns the URI."""
    if uri.startswith("gs://"):
        bucket, blob = _split_gs(uri)
        _client().bucket(bucket).blob(blob).upload_from_filename(str(local_path))
    else:
        Path(uri).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, uri)
    return uri


def get(uri: str, local_path: str | Path) -> Path:
    """Download ``uri`` (gs:// or local) to ``local_path``. Returns the local path."""
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if uri.startswith("gs://"):
        bucket, blob = _split_gs(uri)
        _client().bucket(bucket).blob(blob).download_to_filename(str(local_path))
    else:
        shutil.copyfile(uri, local_path)
    return local_path
