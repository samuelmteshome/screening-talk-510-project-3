# Screening Talk

A reproducible decision aid for preventive screening conversations (AIPI 5100 Module 3).
A person answers a few questions, taps an organ, and sees how a screening test or medicine would change their own chances,
next to what the trials found. Topics: heart disease and stroke (statin, blood pressure medicine, aspirin, checkups),
prostate cancer (PSA test) and colorectal cancer (colonoscopy).

> Educational demo. Not medical advice. Nothing entered in the app is stored.

## Links
- **Dataset:** NHANES public files (see `topics/*.yaml`); cleaned data: `gs://<bucket>/clean/v1/` _(placeholder)_
- **Deployed API:** https://<service>.run.app _(placeholder until the Cloud Run deploy runs)_
- **Public app:** https://screening-talk.streamlit.app
- **Demo video:** `docs/demo.mp4` _(85 seconds: questionnaire, heart, prostate, colonoscopy)_
- **Experiment tracking:** MLflow, see [Experiment tracking](#experiment-tracking)

## Setup
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values locally; never commit .env
```

## Reproduce the data
```bash
make data TOPIC=prostate    # runs the three steps below
python -m src.data.download --topic prostate --snapshot   # CDC files -> data/raw/, dated raw copy in GCS, MANIFEST.json
python -m src.data.clean    --topic prostate              # schema.yaml check + cleaning rules -> data/clean/, docs/cleaning/prostate.md
python -m src.data.upload   --topic prostate --write-hash # clean parquet -> GCS, SHA-256 written to topics/prostate.yaml
```
Training loads the data with `src.data.ingest`, which stops if the file's SHA-256 differs from `clean_sha256`.
Row counts after each cleaning rule are in `docs/cleaning/<topic>.md`.

The same steps work for `TOPIC=heart` and `TOPIC=colorectal`. The CDC site is the only download source; each
topic's files and NHANES variable names are listed in `topics/<topic>.yaml`.

## Train
```bash
python -m src.train --topic prostate          # validation run: picks C, writes runs/<run_id>/
python -m src.train --topic prostate --final  # refit on train+validation, score the test cycles once
python -m src.train --topic colorectal        # same shared trainer
python -m src.train_heart [--final]           # heart: 10-year death from linked mortality files
```
Without a bucket, add `--data-uri data/clean/<topic>/clean.parquet --allow-unverified --no-upload`.
Each run folder holds `model.joblib`, `model_card.json`, `metrics.json`, `calibration.png`, `run_metadata.yaml`
(git commit, image, Python and package versions, seed, data hash) and `train.log`, all logged to MLflow.

All three at once on GitHub: Actions tab, **train all models (final test-set run)**. It downloads, cleans, trains,
scores each test set once and commits `models/<topic>/` and `docs/models/results.md`.

## Experiment tracking
Every training run (`src.train` and `src.train_heart`) is an MLflow run: parameters (topic, features, chosen C, C grid,
training cycles, data URI and SHA-256), metrics (AUC with 95% CI, Brier score, baseline AUC and Brier, Brier skill,
validation Brier for each C), the calibration and subgroup tables, and every run file as an artifact
(model, model card, metrics, calibration chart, run metadata, log). Runs are stored locally in `mlflow.db` and `mlruns/`.
```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db   # then open http://127.0.0.1:5000
```
Set `MLFLOW_TRACKING_URI` to log to another MLflow server instead.

## Test the API locally
```bash
pytest tests/
docker build -t screening-talk .
docker run -p 8080:8080 screening-talk                 # serve; models from models/<topic>/model.joblib or MODEL_URI_<TOPIC>
curl -s -X POST localhost:8080/predict -H 'Content-Type: application/json' -d @tests/example_request.json
python scripts/smoke_test.py http://localhost:8080
```
Endpoints: `GET /health`, `GET /topics`, `POST /predict` (risk for one person plus the trial evidence; `/docs` has the schema).
A topic without a trained model still answers with the trial results. People outside the ages or history the data covers get no number and a reason.

## Deploy
1. One-time Google Cloud setup: open Cloud Shell and run `scripts/gcp_setup.sh`. It creates the bucket, image registry,
   a deploy service account that GitHub Actions uses through Workload Identity Federation (no key file), and a runtime
   service account, then prints six values to set as GitHub repository **variables**.
2. Actions tab, "deploy API to Cloud Run", Run workflow. It trains the models from the public NHANES files, builds
   the image with them inside, deploys `screening-talk-api` and smoke-tests the live URL (output in the run summary).
3. Streamlit Community Cloud: new app from this repo, main file `app/streamlit_app.py`, and in the app's secrets
   `API_URL = "https://<service>.run.app"`.

## Evidence
Every number shown in the app comes from `evidence/*.json`, with a source URL and table or page reference.

## Tasks

Alberto owns the early pipeline work so sam can build serving on top of it.

### Alberto (early: data and training)
- [x] Data pipeline: `src/data/download.py`, `clean.py`, `upload.py`, `ingest.py` (versioned parquet in GCS, hash check), following `docs/data_contract.md`
- [x] Raw snapshot: dated copy in `gs://<bucket>/raw/<date>/`, URL, time and hash per file in `data/raw/MANIFEST.json`
- [x] Schema check: fill `schema.yaml`, make `clean.py` fail on missing or renamed columns; fill `feature_sources` in `topics/*.yaml`
- [x] Evidence files: check every number in `evidence/*.json` against the papers, fill `verified_by`
- [x] Training + tracking: `src/features.py`, `src/train.py`, `src/evaluate.py`, MLflow tracking, calibration bar chart
- [x] Run metadata: `runs/<run_id>/run_metadata.yaml` (git commit, Docker image, Python and package versions, seed, data hash) and a run log file logged to MLflow
- [x] Prostate model: `topics/prostate.yaml`, PSA >= 4.0 target, logged MLflow run

### sam (later: models on top, serving, deployment)
- [x] Heart model: `topics/heart.yaml`, NHANES 1999-2008 linked mortality, 10-year CVD death target, `src/train_heart.py`
- [x] API + Docker: `src/api/` (`POST /predict`, `GET /health`, `GET /topics`), `Dockerfile`, `entrypoint.sh`, `tests/test_api.py`
- [x] CI: `.github/workflows/ci.yml` runs pytest on every pull request (keep it green)
- [ ] Deployment: Cloud Run service, `scripts/smoke_test.py`, paste output below
- [ ] Front end: `app/streamlit_app.py` calling the live API, deployed on Streamlit Community Cloud

### Both
- [ ] Review each other's pull requests (branches `sam/...` and `alberto/...`, no direct pushes to `main`)
- [x] Tests for your own steps in `tests/test_pipeline_steps.py`, using small files in `tests/fixtures/`
- [ ] Swap test: each partner reproduces the other's run from a fresh clone using only this README, and notes any gaps
- [x] Final test-set run per model, metrics table below
- [x] Demo

## Results
Final test-set run, one per model, on survey cycles never used for training or tuning
(details: `docs/models/results.md`, calibration charts in `models/<topic>/`, heart report in `docs/models/heart.md`).

One run per model on survey cycles it never saw during training or tuning. Baseline = age and sex only (heart) or 5-year age bands (prostate, colorectal).

| Model | Predicts | Test people | AUC (95% CI) | Baseline AUC | Brier: model vs baseline | Per 1,000: predicted vs actual |
|---|---|---|---|---|---|---|
| prostate | PSA of 4.0 or higher at the visit (men 50–69) | 864 | 0.663 (0.61–0.72) | 0.686 | 0.0663 vs 0.0657 | 72.2 vs 72.9 |
| heart | Death from heart disease or stroke within 10 years (adults 40–79) | 2,877 | 0.782 | 0.702 | 0.0234 vs 0.0233 | 24.1 vs 24.3 |
| colorectal | Ever told they had colon or rectal cancer (adults 45–79) | 5,958 | 0.632 (0.57–0.69) | 0.633 | 0.0113 vs 0.0113 | 9.1 vs 11.4 |

AUC: 0.5 is a coin flip, 1.0 is perfect. Brier: lower is better. The last column checks calibration.

What this means:
- **Heart** is the only model that beats its baseline (AUC 0.78 vs 0.70) and it is well calibrated, so the app
  uses it as each person's starting 10-year risk and applies the trial effects of each medicine to it.
- **Prostate** and **colorectal** do no better than age alone on their test cycles. Their extra features (race, BMI,
  smoking, diabetes) add little once age is known. The app still shows the prostate number because it is
  calibrated (72 predicted vs 73 actual per 1,000), and says it is a chance of a raised PSA, not of cancer.
  For colorectal the app uses US cancer-registry (SEER) rates by age and sex, raised by published relative risks,
  because the NHANES target is "ever had" cancer, not a 10-year forecast.

Smoke test against the live API: _(pasted by the deploy workflow run summary)_

## Limits
- NHANES is a snapshot. Prostate (PSA at the visit) and colorectal (ever told you had it) are cross-sectional; only
  heart follows people forward (10-year deaths from the linked mortality files).
- NHANES records deaths, not heart attacks or strokes. The heart attack and stroke chance comes from the
  American Heart Association PREVENT equations instead.
- Trial effects are averages from people who joined trials, applied to one person's risk. The app says so on every page.
- For prostate, the model's number and the trial results are shown side by side, not combined. For heart and
  colonoscopy, the trial's relative effect is applied to the person's starting risk, and each page names both sources.
- Small numbers of events (70 heart deaths, 63 raised PSAs, 68 colorectal cancers in the test sets) make the AUCs
  uncertain; the 95% intervals are in the table.
- Educational demo, not medical advice. The app stores nothing; answers live only in the page address.

## Swap test (fresh clone)
```bash
git clone https://github.com/samuelmteshome/screening-talk-510-project-3 && cd screening-talk-510-project-3
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest -q tests
for t in prostate colorectal heart; do python -m src.data.download --topic $t && python -m src.data.clean --topic $t; done
python -m src.train --topic prostate --data-uri data/clean/prostate/clean.parquet --allow-unverified --no-upload --final
python -m src.train_heart --final
streamlit run app/streamlit_app.py
```
Expected: the same row counts as `docs/cleaning/<topic>.md` and the same test metrics as the table above
(fixed seed in `config.yaml`).

Proposal: [`docs/proposal.md`](docs/proposal.md)
