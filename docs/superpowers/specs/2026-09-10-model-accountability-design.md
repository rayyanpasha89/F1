# Model Accountability Release Design

**Date:** 10 September 2026

**Status:** Approved through the user's instruction to select, add, test, and finish a high-impact supported feature without stopping

**Product:** F1 Race Strategist

**Presentation boundary:** No PowerPoint file may be created, edited, regenerated, or replaced in this release.

## Purpose

The current application already covers the approved historical dashboard, race weekend, profiles, leakage-safe podium model, SHAP explanations, grounded agentic chat, read-only SQL, AWS deployment, CI, and public verification. This release makes the model itself inspectable as a product and tightens the runtime around it.

The headline feature is a **Forecast vs Reality Race Lab**. For every supported 2022–2024 race, users can compare the genuine pre-race podium forecast with the recorded podium, see how many predicted top-three drivers matched, inspect a race-level Brier score, and understand the largest over- and under-predictions. Forecast inputs and explanations remain pre-race; recorded results enter only the explicitly labeled post-race review.

A companion **Model Accountability** page presents the training/selection/test timeline, deployed model identity, baseline comparison, uncertainty intervals, calibration evidence, intended use, and limitations. It is backed by machine-readable reports tied to exact model artifacts.

## Audit findings that drive the release

A read-only whole-archive sweep exercised all 75 seasons and 1,125 races. Results and grid data existed for all 1,125 races, qualifying for 494, pit stops for 285, and all 68 supported model races produced finite probabilities with exact SHAP reconstruction. The sweep found no current route/data failures.

The next gaps are architectural rather than missing MVP screens:

1. The classifier emits independent driver probabilities even though a completed Formula 1 race has exactly three podium positions. The average probability sum is close to three but is not guaranteed.
2. The container deserializes trusted model files but does not verify their hashes against a versioned manifest before loading.
3. Health checks prove database availability but do not prove the model artifacts and model evidence are internally consistent.
4. Users can inspect one driver's SHAP factors but cannot audit prediction quality for a selected race or inspect an in-product model card.
5. Safe chat events exist, while prediction and review inference lack equivalent lineage/timing telemetry.
6. Public Lighthouse evidence scored 100 for accessibility and best practices, but mobile cumulative layout shift was 0.282. The document also lacks a description and valid robots policy.
7. Static hashed assets have no immutable cache policy, API responses have no explicit cache/no-store policy, compression is absent, and baseline browser security headers are missing.
8. Runtime Python and production npm direct dependencies have no known vulnerabilities in the current audit, but CI does not enforce those audits.

## Considered approaches

### A. Model accountability and structural calibration — selected

Add an outcome-free race-level probability projection, artifact lineage, a model card, and per-race forecast review. This makes the existing real model more coherent and much easier to scrutinize. It uses only facts already supported by the archive and preserves the leakage boundary.

### B. Train a larger challenger model immediately — research track only

Additional recent-points, field-context, and histogram-gradient-boosting candidates were explored against the existing validation years. They did not beat the selected gradient booster on validation log loss. The final 2022–2024 test has already been consumed, so choosing a new model from its outcomes would weaken the academic evidence. Challenger experiments may be recorded, but no replacement is promoted without a new prospective protocol.

### C. Interactive strategy or weather simulator — rejected

A simulator could look impressive but the source package has no dependable tyres, weather, fuel, telemetry, or strategy labels. It would require fabricated assumptions and would conflict with the approved scope. The Race Lab delivers an interactive, high-impact feature while remaining grounded.

## Probability coherence

### Contract

For a supported race with at least three classified entrants, adjusted podium probabilities must:

- remain finite and strictly between zero and one;
- preserve the raw model ranking exactly;
- sum to three within `1e-10`;
- depend only on the pre-race raw probabilities and the known number of podium positions;
- use no finishing position, points, status, pit, lap, or other post-race outcome;
- retain exact SHAP reconstruction after the race-level offset is added to the explanation base value.

### Method

Let each raw probability be `p_i` and its logit be `z_i`. Solve one scalar offset `delta` by monotonic bisection so that:

`sum(sigmoid(z_i + delta)) = 3`

The same deterministic projection applies independently to the selected model and the grid-only baseline. Adding one shared log-odds offset preserves all rankings. The response exposes the method, target, raw sum, adjusted sum, and offset. Each driver retains the raw probability for audit and receives the adjusted production probability.

### Evidence boundary

An exploratory, outcome-free implementation check showed the projection improved validation log loss from 0.209557 to 0.208772 and final-test log loss from 0.219846 to 0.218918, with small Brier improvements and unchanged top-three ranking. These values must be reproduced by committed code. Because the final test was already consumed before this idea, the new report must call the comparison post-test iterative evidence. It may demonstrate arithmetic and sample uncertainty; it cannot be presented as a fresh untouched model-selection result.

A paired bootstrap samples whole races, not individual driver rows, with seed 42 and 5,000 replicates. It reports 95% intervals for selected-minus-baseline log loss, Brier score, and top-three hit rate. The report must explain that bootstrap intervals do not remove selection bias or create a new holdout.

## Artifact lineage and readiness

`models/manifest.json` is a tracked, non-secret contract generated from the trusted local artifacts and committed reports. It contains:

- schema version;
- model and baseline SHA-256 values;
- selected experiment and feature names;
- training, selection, and inference year ranges;
- calibration method;
- probability postprocessor name and version;
- source audit report SHA-256;
- final evaluation report SHA-256;
- generation timestamp.

The predictor verifies artifact hashes before any `joblib.load`. It then validates expected keys, model interfaces, feature names, year ranges, finite calibration values, and manifest/report agreement. Failure raises a controlled `PredictionUnavailable` without exposing paths or serialized content.

The release archive must include the manifest and exact reports used by the public model card. CodeBuild must execute the real artifact validation. Production startup under `F1_REQUIRE_READONLY=1` must validate both read-only PostgreSQL privileges and the model bundle.

`GET /api/health` remains a lightweight database liveness check for compatibility. `GET /api/health/ready` verifies database access, model bundle integrity, and model-card evidence. Lightsail uses the readiness route for deployment health checks.

## Forecast vs Reality Race Lab

### Backend response

`GET /api/predictions/{race_id}/review` returns one bounded object:

- race identity and an explicit `post_race_review` label;
- model version and postprocessor metadata;
- predicted podium: the three highest pre-race adjusted probabilities;
- recorded podium: the drivers classified first through third;
- top-three hit count from zero to three;
- exact-set boolean;
- race Brier score across all entrants;
- mean absolute probability error;
- the largest overprediction and underprediction, selected by deterministic error magnitude with stable tie-breaking;
- per-driver rows containing driver identity, constructor, grid, adjusted probability, predicted rank, recorded finish, podium outcome, and absolute error;
- notes that recorded outcomes are evaluation labels and never model inputs.

The review service must fail with the existing controlled prediction error for training/selection-era races. It must reject missing or incomplete recorded podiums rather than fabricate evaluation values.

### Leakage proof

Tests mutate the selected race's finishing position, points, and status. Forecast probabilities and SHAP factors must remain byte-for-byte equal. Only review labels and derived review metrics may change. Tests also mutate a future race and prove the earlier forecast and review remain unchanged.

### Frontend experience

The race page adds a visually distinct section after the probability panel:

- “Forecast vs reality” heading and post-race disclosure;
- hit count, race Brier score, and exact-set state;
- predicted and recorded podium lanes;
- accessible driver rows with probability and finish;
- largest surprise explanations;
- a link to the aggregate Model Accountability page;
- loading, error, unavailable, and empty states;
- responsive layout without generic decorative cards.

The current race result table remains separate. The new panel never describes outcome fields as model inputs.

## Model Accountability page

`GET /api/model-card` returns a bounded, validated subset of committed evidence:

- model identity, artifact hashes, postprocessor, and source coverage;
- intended use and excluded uses;
- feature list and exact temporal split;
- selected and baseline metrics before and after probability projection;
- per-season metrics;
- paired race-bootstrap intervals;
- calibration summary;
- explanation semantics;
- known data, evaluation, and operational limitations.

The endpoint does not return filesystem paths, serialized objects, credentials, environment values, or arbitrary report content.

The React route `/model` presents this material using native HTML and CSS: a temporal split band, metric comparison table, calibration/reliability visualization, lineage identifiers, and limitation sections. It links back to the archive and from each supported race review. The header includes “Model accountability.”

## HTTP, UX, and operational hardening

A focused middleware module adds:

- server-generated `X-Request-ID` on every response;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'`;
- a same-origin Content Security Policy compatible with bundled fonts and React inline width styles;
- `Referrer-Policy: no-referrer`;
- a restrictive `Permissions-Policy`;
- HSTS for the HTTPS deployment;
- gzip for eligible responses;
- `no-store` for chat and health;
- short public caching for immutable historical GET APIs;
- one-year immutable caching for hashed frontend assets and no-cache for the SPA shell.

Safe structured log lines are added for prediction and review completion. They include request ID, race ID, model version, postprocessor, elapsed time, probability sum, and review hit count. They exclude driver questions, SQL, credentials, headers, connection strings, prompts, provider bodies, and serialized model data.

The dashboard receives a table skeleton or equivalent reserved geometry so async standings do not move visible content. The root document gains a descriptive title/description and a valid robots file. The new route is code-split so it does not inflate the initial dashboard path.

## Verification and release

### Test layers

1. Pure probability-projection tests: bounds, exact sum, order preservation, deterministic output, invalid input, and no-op edge handling.
2. Manifest tests: hashes checked before deserialization, schema/interface validation, controlled failure, and release archive inclusion.
3. ML tests: all 68 supported races sum to three, raw and adjusted values are finite, and adjusted SHAP reconstruction is exact.
4. Leakage tests: same-race and future outcome mutations cannot change forecasts.
5. Review service/API tests: Monaco 2024 yields a complete recorded podium and deterministic metrics; unsupported years fail safely.
6. Model-card tests: only allowlisted evidence is returned and hashes/splits match the deployed artifacts.
7. HTTP tests: security/cache/request-ID/compression policies and immutable asset caching.
8. Frontend tests: successful, loading, error, and unavailable states for the Race Lab and Model Accountability page, with accessible labels.
9. Whole-product checks: all existing Python/PostgreSQL/frontend/Terraform suites, report regeneration, dependency audits, full archive sweep, browser flows, console/network inspection, and Lighthouse.

### Quality thresholds

- Existing analytics/chat behavior and fixed evaluation reports remain unchanged.
- All 68 supported race predictions reconstruct and sum to three.
- Projection may ship only if it preserves ranking and improves both validation log loss and validation Brier score over the unprojected selected model.
- Runtime and npm production dependency audits report no known direct vulnerabilities.
- Lighthouse accessibility and best-practices scores remain 100 on the public root; cumulative layout shift must be at most 0.10 in the recorded run.
- Public checks cover root, deep link, liveness, readiness, model card, review endpoint, prediction coherence, profiles, comparison, chat typo/follow-up/refusal, and security/cache headers.

### Release sequence

- Develop on an isolated feature branch/worktree.
- Preserve the existing PowerPoint files unchanged and verify their hashes before merge.
- Commit each tested milestone without rewriting history.
- Merge to `main`, push, and require GitHub Python/frontend/infrastructure jobs.
- Guard every AWS mutation with account `148356747273`, profile `default`, and explicit region `eu-north-1`.
- Build the exact merge SHA in CodeBuild, push the immutable ECR tag, and deploy it to Lightsail.
- Wait for `RUNNING`/`ACTIVE`, run public API/browser/Lighthouse verification, inspect safe logs, and write new append-only release reports.
- Keep earlier AWS resources untouched because cleanup is outside the authorized scope.

## Standards alignment

This release applies the parts of the NIST AI Risk Management Framework that fit this historical academic system: validity/reliability, security/resilience, accountability/transparency, explainability, and privacy. It also follows the AWS Machine Learning Lens emphasis on model lineage, environment consistency, operational health, and model-quality observability. A static archive does not experience incoming-data drift, so the implementation records that boundary rather than installing a meaningless live drift service.

## Completion criteria

The release is complete when the coherent model, artifact manifest, readiness gate, Race Lab, model card, HTTP hardening, performance fixes, dependency gates, documentation, CI, exact AWS deployment, browser checks, Lighthouse threshold, safe logs, and append-only evidence reports have all passed, with a clean synchronized `main`. Presentation files remain byte-identical to their pre-release versions.
