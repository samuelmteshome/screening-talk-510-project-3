# Data contract (agree by end of week 1)

One parquet per topic, one row per NHANES participant (`SEQN`).

| Column | Type | Notes |
| --- | --- | --- |
| SEQN | int | NHANES respondent id |
| cycle | str | e.g. "2009-2010" |
| target | int 0/1 | `raised_psa` or `cvd_death_10y` |
| exam_weight | float | `WTMEC2YR` (verify per cycle) |
| feature columns | per `topics/<topic>.yaml` | names match the config exactly |
