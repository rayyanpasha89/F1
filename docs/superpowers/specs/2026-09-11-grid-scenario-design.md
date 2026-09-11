# Grid Scenario Lab design

**Date:** 2026-09-11
**Status:** Approved by the user's standing request to complete and extend the product
**Release boundary:** Historical 2022–2024 races, frozen `EXP-007+podium-count-v1` model

## Product goal

Add an interactive Race Lab control that answers a bounded question: how would the frozen podium model's output change if two recorded starters exchanged grid positions? The result should make model sensitivity tangible without presenting the output as a causal estimate, an unseen evaluation, or a live-race recommendation.

## User flow

On a supported race page, the user chooses two starters and runs a grid swap. The page shows the released forecast beside the counterfactual forecast for every driver, including original and scenario rank, podium probability change, and starting-grid SHAP contribution change. The user can reset the result and run another swap.

The control is unavailable before 2022 because those seasons overlap model training or selection. The interface labels every result as a counterfactual sensitivity analysis and links its meaning to the frozen model and retrospective snapshot.

## API contract

`POST /api/predictions/{race_id}/scenario`

Request:

```json
{
  "driver_a_id": 844,
  "driver_b_id": 830
}
```

Only two distinct positive driver IDs are accepted. Both must be starters in the selected race. The operation swaps their existing model grid inputs; callers cannot submit arbitrary feature values, duplicate positions, outcomes, SQL, or model parameters.

The bounded response contains:

- schema and model identity;
- the two actual driver/grid changes and their exact transformed model inputs;
- released and scenario probability, rank, actual grid position, model grid input, and grid SHAP contribution for every starter;
- proof that both race-level probability sets sum to three;
- an explicit evidence boundary with `outcome_data_used`, `causal`, and `validated_forecast` all false.

No database mutation occurs. The scenario frame is a copy of the cached feature frame, and only `grid_position` changes for the two selected drivers.

Recorded grid `0` means a pit-lane start and is represented separately from the model's fixed proxy input `25`. The API and UI expose both values so the proxy is never presented as a twenty-fifth starting position.

## Model behavior

The service runs the same verified artifacts, temporal support check, calibration, race-level logit projection, and exact SHAP reconstruction as the released forecast. The original and scenario calculations share one artifact load. The scenario probabilities still sum to the three available podium places and remain in `(0, 1)`.

Changing two grid inputs may alter every projected probability because the race-level normalizer is shared. The UI therefore displays all entrants and describes the result as model sensitivity. SHAP values explain the fitted model and do not establish that moving a driver on the grid would cause the displayed change.

## Safety and observability

Pydantic models forbid extra request and response fields and reject non-finite values. Errors remain bounded. A `scenario_complete` event records only request ID, race ID, model version, scenario kind, elapsed time, driver count, and probability sum. It does not record request bodies, names, feature vectors, questions, SQL, credentials, or paths.

The existing HTTP policy makes the POST response `no-store`. The public release verifier runs one deterministic Monaco swap and validates driver sets, swapped positions, rank permutations, finite deltas, model identity, and both probability sums without writing response content to its report.

## Verification

- predictor unit and real-artifact tests for copy isolation, swap symmetry, feature scope, SHAP reconstruction, and probability coherence;
- API tests for the allowlisted contract, request validation, safe errors, no-store delivery, and correlated structured log;
- React tests for selection, request state, result rendering, reset, errors, unsupported years, and accessible labels;
- Python, frontend, formatting, lint, dependency, build, PostgreSQL integration, Terraform, and public release verification gates;
- desktop and mobile browser QA after the exact release image reaches AWS.
