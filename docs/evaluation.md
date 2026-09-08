# Model evaluation

This is a retrospective post-grid, pre-race backtest over recorded entrants. Training: 2010–2018. Selection: 2019–2021. Final test: 2022–2024, 68 races and 1,359 driver entries. Model selection and training-only temporal sigmoid calibration were frozen in Git before final-test evaluation. No test outcomes fit parameters; previous test races can inform later race features, as in sequential forecasting.

| Final-test measure | Grid logistic baseline | Selected calibrated gradient boosting |
|---|---:|---:|
| Log loss | 0.249898 | 0.219846 |
| Brier score | 0.073811 | 0.069285 |
| ROC-AUC | 0.913827 | 0.935364 |
| Precision at 0.5 | 0.755556 | 0.706897 |
| Recall at 0.5 | 0.500000 | 0.602941 |
| F1 at 0.5 | 0.601770 | 0.650794 |
| Top-three hit rate | 0.651961 | 0.647059 |
| Exact podium set rate | 0.161765 | 0.161765 |
| Ten-bin calibration error | 0.020281 | 0.014595 |

The selected model improves probabilistic scoring and recall but does not improve top-three ranking hit rate. A better probability model is not automatically a better exact-podium selector. No perfect accuracy, statistical significance or causal inference is claimed. Small test seasons and regime changes limit conclusions. See `reports/final_test_metrics.json` for full precision, recall, calibration bins and per-season metrics. Test results were not used to change the selection.

## Reproduction

After ingestion, execute `python -m scripts.train_baseline`, `python -m scripts.compare_models`, `python -m scripts.check_calibration`, then `python -m scripts.evaluate_final`. These scripts write metrics from actual predictions. Re-running after seeing test results is reproduction, not a new untouched holdout. A genuinely new tuning exercise needs a new prospective evaluation protocol.

## Explanations

Tree SHAP describes the fitted gradient boosting margin. The sigmoid calibrator transforms margin by slope and intercept, so SHAP values are multiplied by that same slope and the reference adjusted by the intercept. Applying sigmoid to the reference plus all contributions exactly reconstructs the emitted probability (tested to tolerance 1e-7 on the test rows and real API inference). Contributions are calibrated log-odds, not percentage-point or causal effects. Feature importance is mean absolute SHAP across the final test and is descriptive only; it did not select features.

The UI only serves 2022–2024 predictions, avoiding display of in-training or model-selection results as held-out inference. Raw historical data may include later corrections; original point-in-time grids and entry lists cannot be proven from this snapshot. Grid zero has a fixed proxy encoding. Operational nonfinish status is not a pure mechanical DNF signal. See ADRs 002–003 and `EXPERIMENTS.md` for features, priors, ablations and unsupported hypotheses.
