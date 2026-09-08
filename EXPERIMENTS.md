# Experiment registry

Metrics are produced by executable scripts; timestamps in JSON record actual execution. Seed is 42. Final test years 2022–2024 are reserved until validation-based selection is frozen.

## EXP-001 — Grid-only baseline

Command: `python -m scripts.train_baseline`. Training 2010–2018; validation 2019–2021 (60 races, 1,200 driver entries). Model: standardized grid position + logistic regression. Grid zero maps to fixed position 25. Validation log loss 0.246224, Brier 0.069488, ROC-AUC 0.917154, precision 0.758333, recall 0.505556, F1 0.606667, top-three hit rate 0.716667, exact podium set 0.333333, ten-bin ECE 0.034835. Full metrics and coefficient: `reports/baseline_metrics.json`.

H1 is supported descriptively by the fitted negative grid coefficient: worse starting position lowers fitted podium probability. This is association, not a causal estimate. The baseline is useful but leaves substantial probability error. Test outcomes have not been evaluated at this milestone. This artifact is preserved as later feature sets are added.
