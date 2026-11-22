"""Tests for the data steps (download, clean, upload, ingest) on fixture files."""
import json

import pandas as pd
import pytest

from src.config import cycle_in_range, source_variable
from src.data import download, storage
from src.data.clean import SchemaError, clean_topic, load_cycle
from src.data.ingest import DataIntegrityError, load_clean
from src.data.upload import upload_topic, write_hash
from tests.conftest import FIXTURES


def test_cycle_ranges_pick_the_right_biopsy_variable(prostate_cfg):
    sources = prostate_cfg["feature_sources"]
    assert cycle_in_range("2003-2004", "2001-2004")
    assert not cycle_in_range("2005-2006", "2001-2004")
    assert source_variable(sources, "biopsy_4wk", "2003-2004") == "KIQ190"
    assert source_variable(sources, "biopsy_4wk", "2009-2010") == "KIQ191"


def test_download_writes_manifest(tmp_path, config, prostate_cfg, monkeypatch):
    def fake_fetch(url, dest, retries=3):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(url.encode())

    monkeypatch.setattr(download, "fetch", fake_fetch)
    manifest_path = tmp_path / "MANIFEST.json"
    download.download_topic(
        "prostate", config, prostate_cfg, raw_dir=tmp_path / "raw", manifest_path=manifest_path
    )
    manifest = json.loads(manifest_path.read_text())
    entry = manifest["prostate/2009-2010/PSA_F.xpt"]
    assert entry["url"] == "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2009/DataFiles/PSA_F.xpt"
    assert entry["sha256"] == storage.sha256_file(tmp_path / "raw/prostate/2009-2010/PSA_F.xpt")
    assert len(manifest) == 6


def test_clean_applies_prostate_rules(tmp_path, config, prostate_cfg):
    path = clean_topic("prostate", config, prostate_cfg, docs_dir=tmp_path / "docs")
    df = pd.read_parquet(path)

    assert list(df.columns[:4]) == ["SEQN", "cycle", "target", "exam_weight"]
    assert df["age"].between(50, 69).all()
    assert df["SEQN"].is_unique
    assert set(df["race_eth"]) <= {
        "mexican_american", "other_hispanic", "non_hispanic_white", "non_hispanic_black", "other_or_multiracial",
    }
    raw = pd.concat(
        load_cycle("prostate", c, prostate_cfg, FIXTURES / "raw") for c in prostate_cfg["data"]["cycles"]
    )
    kept = raw.set_index("SEQN").loc[df["SEQN"]]
    exclusions = prostate_cfg["data"]["exclude_if_yes"]
    assert not (kept[exclusions] == 1).any().any(), "excluded men must not be in the clean data"
    assert (df["target"].to_numpy() == (kept["psa"] >= 4.0).astype(int).to_numpy()).all()
    assert "SHA-256" in (tmp_path / "docs" / "prostate.md").read_text()


def test_clean_fails_on_renamed_column(config, prostate_cfg):
    prostate_cfg["feature_sources"]["biopsy_4wk"] = {"all": "KIQ191"}  # wrong for 2003-2004
    with pytest.raises(SchemaError, match="KIQ191"):
        clean_topic("prostate", config, prostate_cfg)


def test_clean_fails_on_out_of_range_values(config, prostate_cfg):
    schema = {"prostate": {"age": {"min": 0, "max": 40}}}
    with pytest.raises(SchemaError, match="age: values above 40"):
        clean_topic("prostate", config, prostate_cfg, schema=schema)


def test_upload_then_ingest_round_trip(tmp_path, config, prostate_cfg):
    clean_topic("prostate", config, prostate_cfg, docs_dir=tmp_path / "docs")
    uri, sha = upload_topic("prostate", config, prostate_cfg)
    prostate_cfg["data"]["clean_sha256"] = sha
    df, info = load_clean("prostate", config, prostate_cfg)
    assert info == {"uri": uri, "sha256": sha, "rows": len(df), "verified": True}


def test_ingest_rejects_tampered_data(tmp_path, config, prostate_cfg):
    clean_topic("prostate", config, prostate_cfg, docs_dir=tmp_path / "docs")
    uri, sha = upload_topic("prostate", config, prostate_cfg)
    prostate_cfg["data"]["clean_sha256"] = sha
    df = pd.read_parquet(uri)
    df.loc[0, "target"] = 1 - df.loc[0, "target"]
    df.to_parquet(uri, index=False)
    with pytest.raises(DataIntegrityError, match="data changed"):
        load_clean("prostate", config, prostate_cfg)


def test_ingest_requires_a_recorded_hash(tmp_path, config, prostate_cfg):
    clean_topic("prostate", config, prostate_cfg, docs_dir=tmp_path / "docs")
    upload_topic("prostate", config, prostate_cfg)
    with pytest.raises(DataIntegrityError, match="No clean_sha256"):
        load_clean("prostate", config, prostate_cfg)
    _, info = load_clean("prostate", config, prostate_cfg, allow_unverified=True)
    assert info["verified"] is False


def test_write_hash_keeps_comments(tmp_path):
    topic_yaml = tmp_path / "t.yaml"
    topic_yaml.write_text("data:\n  clean_sha256: <hash>        # printed by upload\n")
    write_hash(topic_yaml, "a" * 64)
    assert topic_yaml.read_text() == f"data:\n  clean_sha256: {'a' * 64}        # printed by upload\n"
