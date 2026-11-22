# Screening Talk

A reproducible decision aid for preventive screening conversations (AIPI 5100 Module 3).
Topics: prostate cancer (PSA), heart disease and stroke (statin), colorectal cancer (colonoscopy, evidence only).

> Educational demo. Not medical advice. Nothing entered in the app is stored.

## Links
- **Dataset:** NHANES public files (see `topics/*.yaml`); cleaned data: `gs://<bucket>/clean/v1/` _(placeholder)_
- **Deployed API:** https://<service>.run.app _(placeholder)_
- **Public app:** https://<app>.streamlit.app _(placeholder)_
- **W&B project:** <link> _(placeholder)_

## Setup
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values locally; never commit .env
```

## Reproduce the data
```bash
python -m src.data.download --topic prostate
python -m src.data.clean    --topic prostate
python -m src.data.upload   --topic prostate   # prints the GCS URI and SHA-256 to put in topics/prostate.yaml
```

## Train
```bash
python -m src.train --topic prostate          # or: docker run --env-file .env screening-talk train --topic prostate
```

## Test the API locally
```bash
pytest tests/
docker build -t screening-talk .
docker run -p 8080:8080 --env-file .env screening-talk serve
curl -s -X POST localhost:8080/predict -H 'Content-Type: application/json' -d @tests/example_request.json
```

## Deploy
```bash
gcloud builds submit --tag <region>-docker.pkg.dev/<project>/screening/screening-talk
gcloud run deploy screening-talk --image <region>-docker.pkg.dev/<project>/screening/screening-talk --allow-unauthenticated
python scripts/smoke_test.py https://<service>.run.app
```

## Evidence
Every number shown in the app comes from `evidence/*.json`, with a source URL and table or page reference.

## Tasks

Alberto owns the early pipeline work so sam can build serving on top of it.

### Alberto (early: data and training)
- [ ] Data pipeline: `src/data/download.py`, `clean.py`, `upload.py`, `ingest.py` (versioned parquet in GCS, hash check), following `docs/data_contract.md`
- [ ] Raw snapshot: dated copy in `gs://<bucket>/raw/<date>/`, URL, time and hash per file in `data/raw/MANIFEST.json`
- [ ] Schema check: fill `schema.yaml`, make `clean.py` fail on missing or renamed columns; fill `feature_sources` in `topics/*.yaml`
- [ ] Evidence files: check every number in `evidence/*.json` against the papers, fill `verified_by`
- [ ] Training + tracking: `src/features.py`, `src/train.py`, `src/evaluate.py`, W&B logging, calibration bar chart
- [ ] Run metadata: `runs/<run_id>/run_metadata.yaml` (git commit, Docker image, Python and package versions, seed, data hash) and a run log file uploaded to W&B
- [ ] Prostate model: `topics/prostate.yaml`, PSA >= 4.0 target, logged W&B run

### sam (later: models on top, serving, deployment)
- [ ] Heart model: `topics/heart.yaml`, NHANES 1999-2008 linked mortality, 10-year CVD death target, trained with Alberto's code
- [ ] API + Docker: `src/api/` (`POST /predict`, `GET /health`, `GET /topics`), `Dockerfile`, `entrypoint.sh`, `tests/test_api.py`
- [ ] CI: `.github/workflows/ci.yml` runs pytest on every pull request (keep it green)
- [ ] Deployment: Cloud Run service, `scripts/smoke_test.py`, paste output below
- [ ] Front end: `app/streamlit_app.py` calling the live API, deployed on Streamlit Community Cloud

### Both
- [ ] Review each other's pull requests (branches `sam/...` and `alberto/...`, no direct pushes to `main`)
- [ ] Tests for your own steps in `tests/test_pipeline_steps.py`, using small files in `tests/fixtures/`
- [ ] Swap test: each partner reproduces the other's run from a fresh clone using only this README, and notes any gaps
- [ ] Final test-set run per model, metrics table below
- [ ] Demo

## Results
_(fill in: metrics table, smoke test output)_

Proposal: [`docs/proposal.md`](docs/proposal.md)
