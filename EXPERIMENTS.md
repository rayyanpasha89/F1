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

## Calibration and isolated hypotheses — before final test

Executed `python -m scripts.check_calibration`. Sigmoid calibration was fitted on training-only temporal out-of-fold margins (fit through 2014 → 2015–2016; fit through 2016 → 2017–2018). The deployment base model remains fit on 2010–2018. Validation log loss improved slightly from 0.209820 to 0.209557, so sigmoid calibration was selected. The small difference should not be overstated. Parameters, reliability bins and timestamps are in `reports/calibration_selection.json`.

Clean H3 ablation: grid + recent podium rate gives log loss 0.229013 versus grid + career rate 0.228719. Thus recent podium rate alone did NOT beat career rate on this validation period. Additional recent finish/nonfinish signals in EXP-002 account for a different comparison. Clean H4 ablation: team feature set 0.226373 versus same set + circuit history 0.225183, modest support for circuit history in this configuration. These are descriptive validation comparisons with no confidence intervals.

Final selected artifact: EXP-007 boosting with training-OOF sigmoid calibration, fit years 2010–2018 and selection years 2019–2021. Test remains unopened in this commit. The selected parameters are frozen in `reports/model_selection.json` before final evaluation.

## Final test — frozen model evaluation

Executed `python -m scripts.evaluate_final` after selection was committed. Test 2022–2024: calibrated boosting log loss 0.219846 vs baseline 0.249898, Brier 0.069285 vs 0.073811, ROC-AUC 0.935364 vs 0.913827. Top-three hit rate 0.647059 is slightly below baseline 0.651961; exact podium set is equal at 0.161765. The model remains selected under the predeclared validation log-loss rule. Full per-season, calibration, provenance and SHAP summaries are saved in `reports/`. This test is now consumed and must not be described as untouched in later tuning.

## Podium-count probability projection — post-test structural release

Executed `python -m scripts.evaluate_probability_projection` after the final test had already been consumed. This is a structural postprocessor, not a new fitted model: one shared log-odds offset is solved independently for each race so the driver marginals sum to the three available podium positions. It reads raw pre-race probabilities and the known podium count only. It uses no result, point, status, lap, or pit-stop outcome; a shared offset preserves driver ranking and is added to the SHAP reference value so additive reconstruction remains exact.

On validation 2019–2021, selected-model log loss changed from 0.209557 to 0.208772 and Brier score from 0.062173 to 0.062043. On the already-consumed 2022–2024 test, log loss changed from 0.219846 to 0.218918 and Brier score from 0.069285 to 0.069044. Top-three hit rate is unchanged by construction on both splits. Across every evaluated race, both the selected model and grid baseline preserve rank and sum to three within `8.89e-16` maximum absolute error.

The paired 5,000-replicate, seed-42 whole-race bootstrap on the consumed test compares projected selected model minus projected baseline. The estimated difference is -0.030886 log loss (95% interval -0.049274 to -0.013971), -0.004727 Brier score (-0.008490 to -0.000895), and -0.004902 top-three hit rate (-0.034314 to 0.024510). These intervals describe sampled-race variation. They do not undo reuse of the test outcomes, remove selection bias, or create a fresh holdout. Full deterministic metrics, per-season values, constraints, and evidence labels are in `reports/race_constraint_evaluation.json`; artifact and report hashes are bound by `models/manifest.json`.
