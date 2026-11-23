# Data contract (agree by end of week 1)

One parquet per topic, one row per NHANES participant (`SEQN`), written by
`src/data/clean.py` and checked by `src/data/ingest.py` before training.

| Column | Type | Notes |
| --- | --- | --- |
| SEQN | int | NHANES respondent id, unique |
| cycle | str | e.g. "2009-2010"; used for the train/validation/test split |
| target | int 0/1 | `raised_psa` or `cvd_death_10y` |
| exam_weight | float | `WTMEC2YR` (exam sample weight) |
| feature columns | per `topics/<topic>.yaml` | names match `features` exactly |

`race_eth` (from `RIDRETH1`) is stored as one of: `mexican_american`,
`other_hispanic`, `non_hispanic_white`, `non_hispanic_black`,
`other_or_multiracial`. The API uses the same values.

Missing feature values (for example BMI) are kept as missing; the model
pipeline imputes them, so training and the API handle them the same way.
