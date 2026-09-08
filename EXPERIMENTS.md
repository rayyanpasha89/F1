# Experiment registry

Metrics are produced by executable scripts; timestamps in JSON record actual execution. Seed is 42. Final test years 2022–2024 are reserved until validation-based selection is frozen.

## EXP-001 — Grid-only baseline

Command: `python -m scripts.train_baseline`. Training 2010–2018; validation 2019–2021 (60 races, 1,200 driver entries). Model: standardized grid position + logistic regression. Grid zero maps to fixed position 25. Validation log loss 0.246224, Brier 0.069488, ROC-AUC 0.917154, precision 0.758333, recall 0.505556, F1 0.606667, top-three hit rate 0.716667, exact podium set 0.333333, ten-bin ECE 0.034835. Full metrics and coefficient: `reports/baseline_metrics.json`.

H1 is supported descriptively by the fitted negative grid coefficient: worse starting position lowers fitted podium probability. This is association, not a causal estimate. The baseline is useful but leaves substantial probability error. Test outcomes have not been evaluated at this milestone. This artifact is preserved as later feature sets are added.

## EXP-002 through EXP-009 — Validation experiments

Executed `python -m scripts.compare_models`; detailed metrics and timestamps are in `reports/validation_experiments.json`, with flat comparisons in `reports/model_comparison.csv`.

| ID | Model / inputs | Train years | Validation log loss |
|---|---|---|---:|
| EXP-002 | Logistic / grid + recent driver | 2010–2018 | 0.227574 |
| EXP-003 | Logistic / preceding + constructor | 2010–2018 | 0.226373 |
| EXP-004 | Logistic / full including circuit + career | 2010–2018 | 0.223892 |
| EXP-005 | Logistic / grid + career | 2010–2018 | 0.228719 |
| EXP-006 | Random forest / full | 2010–2018 | 0.214612 |
| EXP-007 | Gradient boosting / full | 2010–2018 | 0.209820 |
| EXP-008 | Logistic / full | 2014–2018 | 0.224788 |
| EXP-009 | Gradient boosting / full | 2014–2018 | 0.211740 |

All use validation 2019–2021. H2: adding constructor form reduced log loss slightly (EXP-002 → 003). H3: recent-driver features beat grid + career on log loss, but not on Brier; evidence depends on the metric and is not a clean single-feature comparison. H4: full features add both circuit and career, so EXP-003 → 004 does not isolate circuit alone; a circuit-only ablation remains necessary. Modern shorter training did not improve the tested full models. EXP-007 is selected before final-test evaluation; calibration checks may still select a transformed version using validation only. No hypothesis significance test or causal conclusion is claimed.
