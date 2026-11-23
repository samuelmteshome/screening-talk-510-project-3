"""One test per pipeline step, run on tests/fixtures. Owners fill these in."""
import pytest


@pytest.mark.skip(reason="TODO sam: /predict returns risk plus trial evidence for tests/example_request.json")
def test_predict():
    pass
