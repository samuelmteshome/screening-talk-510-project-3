"""Shared test setup: configs that point the pipeline at the small fixture files."""
import copy
from pathlib import Path

import pytest

from src.config import load_config, load_topic

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_CYCLES = {"2003-2004": ["DEMO_C", "BMX_C", "L11PSA_C"], "2009-2010": ["DEMO_F", "BMX_F", "PSA_F"]}


@pytest.fixture
def config(tmp_path):
    cfg = copy.deepcopy(load_config())
    cfg["storage"]["bucket"] = "<bucket>"
    cfg["data"].update(
        raw_dir=str(FIXTURES / "raw"),
        clean_dir=str(tmp_path / "clean"),
        cache_dir=str(tmp_path / "cache"),
    )
    return cfg


@pytest.fixture
def prostate_cfg(tmp_path):
    """The real prostate config, limited to the two fixture cycles and a local URI."""
    cfg = copy.deepcopy(load_topic("prostate"))
    cfg["data"]["cycles"] = list(FIXTURE_CYCLES)
    cfg["data"]["files"] = dict(FIXTURE_CYCLES)
    cfg["data"]["clean_uri"] = str(tmp_path / "bucket" / "clean" / "prostate" / "v1" / "clean.parquet")
    return cfg


HEART_FIXTURE_FILES = {
    "2001-2002": ["DEMO_B", "BMX_B", "L13_B", "BPX_B", "BPQ_B", "DIQ_B", "SMQ_B", "MCQ_B",
                  "https://ftp.cdc.gov/x/NHANES_2001_2002_MORT_2019_PUBLIC.dat"],
    "2005-2006": ["DEMO_D", "BMX_D", "TCHOL_D", "HDL_D", "BPX_D", "BPQ_D", "DIQ_D", "SMQ_D", "MCQ_D",
                  "https://ftp.cdc.gov/x/NHANES_2005_2006_MORT_2019_PUBLIC.dat"],
}


@pytest.fixture
def heart_cfg(tmp_path):
    """The real heart config, limited to the two fixture cycles."""
    cfg = copy.deepcopy(load_topic("heart"))
    cfg["data"]["cycles"] = list(HEART_FIXTURE_FILES)
    cfg["data"]["files"] = dict(HEART_FIXTURE_FILES)
    cfg["data"]["clean_uri"] = str(tmp_path / "bucket" / "clean" / "heart" / "v1" / "clean.parquet")
    return cfg


COLORECTAL_FIXTURE_FILES = {
    "2003-2004": ["DEMO_C", "BMX_C", "SMQ_C", "DIQ_C", "MCQ_C"],
    "2013-2014": ["DEMO_H", "BMX_H", "SMQ_H", "DIQ_H", "MCQ_H"],
}


@pytest.fixture
def colorectal_cfg(tmp_path):
    """The real colorectal config, limited to the two fixture cycles."""
    cfg = copy.deepcopy(load_topic("colorectal"))
    cfg["data"]["cycles"] = list(COLORECTAL_FIXTURE_FILES)
    cfg["data"]["files"] = dict(COLORECTAL_FIXTURE_FILES)
    cfg["data"]["clean_uri"] = str(tmp_path / "bucket" / "clean" / "colorectal" / "v1" / "clean.parquet")
    return cfg
