"""Heart data step on made-up fixtures: mortality reader, cohort rules, target."""
import pandas as pd

from src.config import load_topic, source_variable
from src.data.clean import clean_topic, load_cycle, read_mortality
from tests.conftest import FIXTURES


def test_mortality_reader_parses_fixed_width(tmp_path):
    line = " " * 48
    def put(s, start, val):
        return s[: start - 1] + val + s[start - 1 + len(val):]
    alive = put(put(put(put(line, 1, "  1234"), 15, "1"), 16, "0"), 46, "215")
    alive = put(alive, 17, "  .")
    died = put(put(put(put(put(line, 1, "  1235"), 15, "1"), 16, "1"), 17, "001"), 46, " 37")
    path = tmp_path / "m.dat"
    path.write_text(alive + "\n" + died + "\n")
    df = read_mortality(path)
    assert df.loc[0, "SEQN"] == 1234 and df.loc[0, "MORTSTAT"] == 0 and pd.isna(df.loc[0, "UCOD_LEADING"])
    assert df.loc[1, "UCOD_LEADING"] == 1 and df.loc[1, "PERMTH_EXM"] == 37


def test_hdl_variable_changes_by_cycle():
    sources = load_topic("heart")["feature_sources"]
    assert source_variable(sources, "hdl", "2001-2002") == "LBDHDL"
    assert source_variable(sources, "hdl", "2003-2004") == "LBXHDD"
    assert source_variable(sources, "hdl", "2007-2008") == "LBDHDD"


def test_every_real_cycle_lists_a_mortality_file():
    cfg = load_topic("heart")
    for cycle in cfg["data"]["cycles"]:
        files = cfg["data"]["files"][cycle]
        assert files[0].startswith("DEMO") and files[-1].endswith("_MORT_2019_PUBLIC.dat")


def test_clean_applies_heart_rules(tmp_path, config, heart_cfg):
    path = clean_topic("heart", config, heart_cfg, docs_dir=tmp_path / "docs")
    df = pd.read_parquet(path)
    raw = pd.concat(load_cycle("heart", c, heart_cfg, FIXTURES / "raw") for c in heart_cfg["data"]["cycles"])
    kept = raw.set_index("SEQN").loc[df["SEQN"]]

    assert df["age"].between(40, 75).all()
    assert (kept["eligstat"] == 1).all()
    assert not (kept[["chf", "chd", "angina", "heart_attack", "stroke"]] == 1).any().any()
    expected = (kept["mortstat"] == 1) & kept["ucod_leading"].isin([1, 5]) & (kept["permth_exm"] <= 120)
    assert (df["target"].to_numpy() == expected.astype(int).to_numpy()).all()
    assert df["target"].sum() > 0
    # a person with no BP reading 1 still gets the mean of readings 2 and 3
    assert df["sbp"].notna().all()
    assert set(df["sex"]) <= {"male", "female"}
    assert "SHA-256" in (tmp_path / "docs" / "heart.md").read_text()


def test_eda_report_on_fixtures(tmp_path, config, heart_cfg, monkeypatch):
    from src import eda
    path = clean_topic("heart", config, heart_cfg, docs_dir=tmp_path / "docs")
    cfg = dict(load_topic("heart"))
    cfg["split"] = {"train_cycles": ["2001-2002"], "val_cycles": ["2005-2006"], "test_cycles": []}
    monkeypatch.setattr(eda, "load_topic", lambda topic: cfg)
    report = eda.run("heart", path, tmp_path / "eda")
    text = report.read_text()
    assert "## Outcome" in text and "AUC alone" in text
    assert (tmp_path / "eda" / "event_rate_by_feature.png").exists()
