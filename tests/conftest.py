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
