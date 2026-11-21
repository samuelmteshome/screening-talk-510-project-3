# AIPI 5100 Module 3 Proposal: Screening Talk

Nov 21, 2026 · @sam

**Due:** Nov 24, 2026. **Team:** sam and Alberto.

## Project summary

Module 3 project idea: a web tool that shows a patient their predicted risk, and what a major clinical trial found, for three preventive steps: a PSA test (prostate cancer), a statin (heart disease), and a colonoscopy (colorectal cancer). It uses public CDC NHANES datasets. It trains a logistic regression model for each topic. It runs on a config-driven, structured data pipeline: raw NHANES files are cleaned, versioned in Google Cloud Storage, trained with Weights & Biases tracking, served by a FastAPI container on Cloud Run, and shown in a public Streamlit app.

## Division of labor

**sam makes:**

1. The data pipeline: scripts that download NHANES, clean it, upload versioned data to Google Cloud Storage, and load it back for training.
2. The heart model: 10-year risk of dying from heart disease or stroke.
3. The `/predict` API (FastAPI) and the Dockerfile.
4. The Cloud Run deployment and a script that tests the live API.

**Alberto makes:**

1. The training and evaluation code, with every run logged to Weights & Biases.
2. The prostate model: chance of a raised PSA result.
3. The trial evidence files (ERSPC, HOPE-3, NordICC), with each number checked against the paper.
4. The Streamlit app that calls the live API.

**Both:** review each other's pull requests, write the README, record the demo.

## Rubric coverage

| Requirement | How we meet it | Proof |
| --- | --- | --- |
| Reproducibility | Pinned `requirements.txt`, `config.yaml`, fixed seed, hash check on data | `docker run screening-talk train --topic prostate` matches the logged metrics |
| Versioned data in the cloud | Cleaned data in Google Cloud Storage with versioning; hash stored in config | GCS path in README; test fails if the file changes |
| Experiment tracking | W&B logs config, AUC, Brier score, calibration chart, and model file per run | W&B project link |
| Model and evaluation | Logistic regression vs an age-group baseline; split by survey cycle; test set used once | Metrics table in README |
| Docker | One image with `train` and `serve` entry points | `Dockerfile` |
| API | `POST /predict` and `GET /health` | `curl` example and `pytest` |
| Cloud deployment | Public Cloud Run URL | Smoke test output in README |
| Front end | Public Streamlit app that calls the API | App link |
| Collaboration | 8 pull requests (4 each), each reviewed by the other partner; protected `main` | GitHub history |
| Documentation | README covers setup, training, local API test, Docker, deployment, and links | `README.md` |

## Data and models

| Topic | Dataset | Target | Inputs | Train / validate / test |
| --- | --- | --- | --- | --- |
| Prostate | [NHANES PSA lab files](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2009/DataFiles/PSA_F.htm) 2001 to 2010; men 50 to 69 without prostate cancer | PSA 4.0 ng/mL or higher | Age, race/ethnicity, BMI | 2001-06 / 2007-08 / 2009-10 |
| Heart | NHANES 1999 to 2008 linked to [CDC death records](https://www.cdc.gov/nchs/data-linkage/mortality-public.htm) through 2019; adults 40 to 75 without heart disease or stroke | Died of heart disease or stroke within 10 years | Age, sex, race/ethnicity, total and HDL cholesterol, systolic BP, BP medicine, diabetes, smoking | 1999-2004 / 2005-06 / 2007-08 |
| Colorectal | None (no public data with colorectal outcomes) | Trial evidence only |  |  |

- **Metrics:** AUC, Brier score against the baseline, and a calibration check (predicted vs actual rate in 5 risk groups, shown as a bar chart).
- **Leakage:** values from the same blood draw (free PSA, PSA ratio) are excluded; data is split by survey cycle.
- **Why not PLCO:** it needs an NCI application and data agreement with no stated review time, which does not fit the timeline. NHANES is a free download.

## Trial evidence

Shown next to the model's prediction. The two are never multiplied, because they measure different outcomes over different time spans.

| Topic | Trial | Comparison | People | Follow-up | Result per 1,000 people |
| --- | --- | --- | --- | --- | --- |
| Prostate | [ERSPC](https://www.nejm.org/doi/full/10.1056/NEJMoa2503223), NEJM 2025 | Invited to PSA screening vs not | 160,000+ men, 8 European countries | 23 years | About 2 fewer prostate cancer deaths; 12 extra diagnoses per death prevented; no change in deaths overall |
| Heart | [HOPE-3](https://www.nejm.org/doi/full/10.1056/NEJMoa1600176), NEJM 2016 | Rosuvastatin 10 mg vs placebo | 12,705 people at intermediate risk | 5.6 years | Heart attack, stroke, or heart death: 37 vs 48; new diabetes: 39 vs 38 |
| Colorectal | [NordICC](https://pubmed.ncbi.nlm.nih.gov/36214590/), NEJM 2022 | One colonoscopy invitation vs usual care | 84,585 adults aged 55 to 64 | 10 years | Colorectal cancer: 10 vs 12; colorectal cancer deaths: about 3 vs 3 |

We are not covering the digital rectal exam, ECG screening, or heart scans, because we did not find trials that fit this design.

## What the patient sees

Example: a 56-year-old man chooses Prostate.

> Among US men like you, about **\[X\] in 100** had a PSA of 4.0 or higher, the level that usually leads to more tests. In a large European trial, over 23 years, about **2 fewer men per 1,000** invited to screening died of prostate cancer. About 12 men were diagnosed for each death prevented, and some were treated for cancers that would not have harmed them. Use this to start a conversation with your doctor.

The page also shows bar charts of both results and the sources. Ages outside the model or trial range get no number, only a note.

## API

```json
POST /predict
{"topic": "prostate", "age_years": 56, "race_eth": "non_hispanic_white", "bmi_kg_m2": 27.5}

Response
{"in_supported_range": true,
 "prediction": {"p_psa_ge_4": 0.06, "per_100": 6, "interval_95": [0.04, 0.09]},
 "evidence": {"source": "ERSPC, NEJM 2025", "horizon_years": 23, "pc_deaths_avoided_per_1000": 2.2},
 "model_version": "<wandb_run_id>"}
```

The numbers above are illustrative. Test locally with `docker run` and `curl`, then run the same request against the Cloud Run URL with `scripts/smoke_test.py`.

## Pipeline

1. `download.py`: fetch NHANES files and record their hashes.
2. `clean.py`: merge, apply exclusions, build the target.
3. `upload.py`: save versioned parquet to Google Cloud Storage.
4. `ingest.py`: load from the cloud and check the hash.
5. `train.py` and `evaluate.py`: fit the baseline and model, log to W&B, save the model to GCS.
6. `api/main.py`: FastAPI loads the model; Docker `serve` runs it on Cloud Run.
7. `app/streamlit_app.py`: calls the live API.

Each topic has its own `topics/<topic>.yaml` (data files, filters, target, features, split), so the same code trains both models.

## Timeline

| When | Step | Owner |
| --- | --- | --- |
| Week 1 | Repo setup, data pipeline | sam |
| Week 1 | Evidence files, training and W&B code | Alberto |
| Week 2 | Heart model, API, Dockerfile | sam |
| Week 2 | Prostate model, Streamlit app | Alberto |
| Week 3 | Cloud Run deployment, smoke test | sam |
| Week 3 | Final test run, README, demo | Both |

If time runs short, the heart model is cut and heart becomes evidence only.

## Ethics and limits

- **Privacy:** no names or dates of birth; the app stores nothing.
- **Subgroups:** we report results by race/ethnicity. HOPE-3 had only 2% Black participants, and the app says so.
- **False precision:** whole numbers only, with "about" and a range.
- **Individual results:** trial results are averages for the people studied, not a promise for one patient. NHANES data ends in 2010 (PSA) and lacks family history.

## To verify before submitting

- ERSPC deaths per 1,000 in each group and the age range, from the NEJM paper (current figures come from a university press release).
- HOPE-3 muscle-symptom rates, from the NEJM paper.
- NHANES cause-of-death codes and variable names in each cycle's codebook.

## Sources

- [NHANES PSA codebook, 2009-10](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2009/DataFiles/PSA_F.htm)
- [NCHS public-use linked mortality files](https://www.cdc.gov/nchs/data-linkage/mortality-public.htm)
- [NCI CDAS: PLCO access](https://cdas.cancer.gov/plco)
- [Roobol et al., ERSPC 23-year follow-up, NEJM 2025](https://www.nejm.org/doi/full/10.1056/NEJMoa2503223)
- [Yusuf et al., HOPE-3, NEJM 2016](https://www.nejm.org/doi/full/10.1056/NEJMoa1600176)
- [NordICC, NEJM 2022](https://pubmed.ncbi.nlm.nih.gov/36214590/)
- [USPSTF 2018 prostate cancer screening](https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/prostate-cancer-screening)
