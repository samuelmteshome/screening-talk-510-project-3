"""One test per pipeline step, run on tests/fixtures. Owners fill these in."""
import pytest


@pytest.mark.skip(reason="TODO Alberto: clean.py on fixture passes schema.yaml check")
def test_clean_schema():
    pass


@pytest.mark.skip(reason="TODO Alberto: features.py builds the columns listed in topics/*.yaml")
def test_features():
    pass


@pytest.mark.skip(reason="TODO Alberto: train.py writes model.joblib and runs/<run_id>/run_metadata.yaml")
def test_train_writes_metadata():
    pass


@pytest.mark.skip(reason="TODO sam: /predict returns risk plus trial evidence for tests/example_request.json")
def test_predict():
    pass
