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

## Coherent race probabilities

Production predictions apply a deterministic race-level logit offset after calibration. For raw logits `z_i`, the service solves one scalar `delta` so `sum(sigmoid(z_i + delta)) = 3`. The same operation is applied separately to the selected model and grid baseline. It cannot change their within-race rankings, and it uses no outcome label. The response retains each raw probability, identifies the postprocessor as `race_logit_offset` version `v1`, and reports the raw sum, adjusted sum, and offset.

| Split and model | Raw log loss | Projected log loss | Raw Brier | Projected Brier | Top-three hit rate |
|---|---:|---:|---:|---:|---:|
| Validation 2019–2021, selected | 0.209557 | 0.208772 | 0.062173 | 0.062043 | 0.727778 |
| Validation 2019–2021, grid baseline | 0.246224 | 0.246220 | 0.069488 | 0.069481 | 0.716667 |
| Consumed test 2022–2024, selected | 0.219846 | 0.218918 | 0.069285 | 0.069044 | 0.647059 |
| Consumed test 2022–2024, grid baseline | 0.249898 | 0.249804 | 0.073811 | 0.073772 | 0.651961 |

The maximum absolute sum error across evaluated races is `8.89e-16`; all rankings are preserved. A seed-42 paired bootstrap samples 5,000 whole races from the consumed test. For projected selected minus projected baseline, its 95% intervals are -0.049274 to -0.013971 for log loss, -0.008490 to -0.000895 for Brier score, and -0.034314 to 0.024510 for top-three hit rate. The first two intervals exclude zero for this archive sample; the ranking interval does not. This is post-test iterative evidence because these outcomes had already been inspected. It is not an unseen confirmation set and cannot support a fresh selection claim.

## Maximum-entropy podium sets

The Podium Outcome Lab derives a complete probability distribution over unordered three-driver subsets from the released race marginals. For a subset `S` of exactly three drivers, it uses

`q(S) = exp(sum(theta_i for i in S)) / Z`

and solves the parameters so each driver's total probability across all subsets containing that driver reconstructs the released marginal. One parameter is fixed because adding a constant to every parameter does not change a fixed-size distribution. The analytic Jacobian is the covariance matrix of the subset membership indicators. This is the maximum-entropy distribution subject to the released marginal constraints, so it adds no unsupported interaction preference beyond those constraints.

The executable evaluation `python -m scripts.evaluate_podium_outcomes` covered all 68 supported races and 1,359 driver rows. It enumerated 77,349 complete sets; each race had 969–1,140 combinations and converged. Distribution mass summed to one, reconstructed marginals summed to three within `8.89e-16`, and maximum per-driver reconstruction error was `3.82e-13`. Full derivation averaged 3.620 ms per race and peaked at 15.424 ms on the local verification machine. Entropy ranged from 3.9937 to 5.8993 bits, corresponding to 15.93–59.69 effective outcomes. The aggregate report is `reports/podium_outcome_local_evaluation.json`.

For Monaco 2024, the 1,140-set distribution has 4.7317 bits of entropy and 26.57 effective outcomes. The leading unordered set is Carlos Sainz, Charles Leclerc, and Oscar Piastri at 13.57%; the first 12 sets contain 79.94% of total mass. These are derived set probabilities, not observed-frequency validation metrics. The derivation reads no same-race outcome, fits no new parameters from result labels, does not predict the order within a set, and has not been independently validated as a joint finishing model.

## Reproduction

After ingestion, execute `python -m scripts.train_baseline`, `python -m scripts.compare_models`, `python -m scripts.check_calibration`, then `python -m scripts.evaluate_final`. Generate structural release evidence with `python -m scripts.evaluate_probability_projection` and `python -m scripts.evaluate_podium_outcomes`, then bind the fitted artifacts and fit-time reports to the trusted local manifest with `python -m scripts.build_model_manifest`. These scripts write metrics from actual predictions and derivations. Re-running after seeing test results is reproduction, not a new untouched holdout. A genuinely new tuning exercise needs a new prospective evaluation protocol.

## Explanations

Tree SHAP describes the fitted gradient boosting margin. The sigmoid calibrator transforms margin by slope and intercept, so SHAP values are multiplied by that same slope and the reference adjusted by the intercept. The race-level postprocessor adds its shared offset to the calibrated reference without changing the feature contributions. Applying sigmoid to the adjusted reference plus all contributions exactly reconstructs the emitted production probability (tested to tolerance `1e-7`). Contributions are calibrated log-odds, not percentage-point or causal effects. Feature importance is mean absolute SHAP across the final test and is descriptive only; it did not select features.

The UI only serves 2022–2024 predictions, avoiding display of in-training or model-selection results as held-out inference. Raw historical data may include later corrections; original point-in-time grids and entry lists cannot be proven from this snapshot. Grid zero has a fixed proxy encoding. Operational nonfinish status is not a pure mechanical DNF signal. See ADRs 002–003 and `EXPERIMENTS.md` for features, priors, ablations and unsupported hypotheses.

## Counterfactual grid sensitivity

The Grid Scenario Lab exchanges the `grid_position` feature for exactly two recorded starters while preserving every other feature value, calibration parameter, model artifact, and postprocessor. It calculates the released and scenario forecasts from separate copies during one request. The contract exposes the actual grid position and transformed model input separately, so a pit-lane grid of `0` remains distinct from its fixed proxy input of `25`. Tests confirm this edge case, the cached inference frame and subsequent released forecast remain unchanged, the operation is symmetric when the driver order is reversed, both probability sets sum to three, and every SHAP reconstruction remains exact.

This is a sensitivity calculation inside the fitted model. It does not estimate the causal effect of a real grid penalty, account for how qualifying pace or race strategy would change, create an unseen evaluation set, or validate performance on future seasons. Because the podium-count projection uses one shared race offset, changing two grid inputs can cause small probability changes for other entrants even though their feature values remain fixed. The public contract exposes that whole-field effect and labels `outcome_data_used`, `causal`, and `validated_forecast` as false.
