# Final test-set results

One run per model on survey cycles it never saw during training or tuning. Baseline = age and sex only (heart) or 5-year age bands (prostate, colorectal).

| Model | Predicts | Test people | AUC (95% CI) | Baseline AUC | Brier: model vs baseline | Per 1,000: predicted vs actual |
|---|---|---|---|---|---|---|
| prostate | PSA of 4.0 or higher at the visit (men 50–69) | 864 | 0.663 (0.61–0.72) | 0.686 | 0.0663 vs 0.0657 | 72.2 vs 72.9 |
| heart | Death from heart disease or stroke within 10 years (adults 40–79) | 2,877 | 0.782 | 0.702 | 0.0234 vs 0.0233 | 24.1 vs 24.3 |
| colorectal | Ever told they had colon or rectal cancer (adults 45–79) | 5,958 | 0.632 (0.57–0.69) | 0.633 | 0.0113 vs 0.0113 | 9.1 vs 11.4 |

AUC: 0.5 is a coin flip, 1.0 is perfect. Brier: lower is better. The last column checks calibration.
