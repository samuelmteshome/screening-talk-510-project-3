# Heart model

Logistic regression on age, sex, total_chol, hdl, sbp, on_bp_meds, diabetes, current_smoker. Target: death from heart disease or stroke within 10 years of the NHANES exam (linked death records).

Trained on 1999-2000, 2001-2002, 2003-2004 (6,776 people, 173 deaths).

| Model | Split | People | Deaths | AUC | Brier | Predicted per 1,000 | Observed per 1,000 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_age_sex | val | 2,165 | 46 | 0.745 | 0.0205 | 24.4 | 21.2 |
| model | val | 2,165 | 46 | 0.779 | 0.0203 | 23.2 | 21.2 |

![Calibration](heart_calibration_val.png)

## Odds ratios (per SD for numbers, yes vs no for yes/no answers)

| Term | Odds ratio |
| --- | --- |
| age | 1.86 |
| total_chol | 1.13 |
| hdl | 0.92 |
| sbp | 1.44 |
| missingindicator_total_chol | 1.06 |
| missingindicator_hdl | 1.06 |
| missingindicator_sbp | 0.78 |
| on_bp_meds | 1.61 |
| diabetes | 2.01 |
| current_smoker | 2.07 |
| sex_male | 2.06 |
