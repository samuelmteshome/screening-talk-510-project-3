"""Colorectal data step on made-up fixtures: cohort rules, target, codebook parsing, EDA."""
import pandas as pd

from src.config import load_topic
from src.data.clean import clean_topic
from src.data.codebook_check import codes_from_codebook, match_codes


def test_clean_applies_colorectal_rules(tmp_path, config, colorectal_cfg):
    path = clean_topic("colorectal", config, colorectal_cfg, docs_dir=tmp_path / "docs")
    df = pd.read_parquet(path)
    assert df["age"].between(45, 79).all()
    assert set(df["target"].unique()) <= {0, 1}
    # target is colon (16) or rectum (31) in any of the three type slots
    assert df["target"].sum() > 0
    assert {"ever_smoked", "current_smoker", "diabetes", "sex", "race_eth", "bmi"} <= set(df.columns)
    assert (tmp_path / "docs" / "colorectal.md").read_text().count("Target") == 1


def test_codebook_parser_finds_colon_and_rectum():
    html = """<div id="MCQ230A"><table><tr><td>14</td><td>Breast</td></tr>
    <tr><td>16</td><td>Colon</td></tr><tr><td>31</td><td>Rectum (rectal)</td></tr></table></div>
    <div id="MCQ230B"><tr><td>16</td><td>Something else</td></tr></div>"""
    codes = codes_from_codebook(html)
    assert codes["colon"] == 16 and codes["breast"] == 14
    assert "something else" not in codes
    assert match_codes(codes, {"colon": 16, "rectum": 31}) == {"colon": 16, "rectum": 31}


def test_colorectal_config_matches_shared_trainer_layout():
    cfg = load_topic("colorectal")
    assert set(cfg["feature_types"]) == set(cfg["features"])
    assert {"train_cycles", "val_cycles", "test_cycles"} <= set(cfg["split"])
    all_cycles = sum((cfg["split"][k] for k in ("train_cycles", "val_cycles", "test_cycles")), [])
    assert sorted(all_cycles) == sorted(cfg["data"]["cycles"])


def test_eda_report_on_colorectal_fixtures(tmp_path, config, colorectal_cfg, monkeypatch):
    from src import eda
    path = clean_topic("colorectal", config, colorectal_cfg, docs_dir=tmp_path / "docs")
    cfg = dict(load_topic("colorectal"))
    cfg["split"] = {"train_cycles": ["2003-2004"], "val_cycles": ["2013-2014"], "test_cycles": []}
    monkeypatch.setattr(eda, "load_topic", lambda topic: cfg)
    text = eda.run("colorectal", path, tmp_path / "eda").read_text()
    assert "colon or rectal cancer" in text
