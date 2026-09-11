# Podium Outcome Lab design

**Date:** 2026-09-11
**Status:** Approved by the user's standing request to complete and extend the product
**Release boundary:** Historical 2022–2024 races, frozen `EXP-007+podium-count-v1` marginal model

## Product goal

Add a Podium Outcome Lab that turns the released per-driver podium probabilities into a coherent probability distribution over complete, unordered three-driver podium sets. The feature should answer questions such as “which three-driver podium is most consistent with this forecast?” while preserving the exact three-place race constraint and clearly separating a derived dependency model from a separately trained finishing-order model.

## Statistical contract

For one supported race, let each driver have the released marginal podium probability `p_i`, where every value is in `(0, 1)` and the values sum to three. Enumerate every three-driver subset `S` and fit the maximum-entropy fixed-size distribution

```text
q(S) = exp(sum(theta_i for i in S)) / Z
```

subject to each reconstructed marginal `sum(q(S) for S containing i) = p_i`.

The distribution uses only the already released marginal probabilities. The derivation does not read the selected race's outcome, retrain or modify the frozen model, infer the order of the three drivers, or claim independent validation as a joint forecast. Maximum entropy adds only the dependence required by the fact that every podium contains exactly three distinct drivers; it avoids adding an unsupported interaction preference between drivers.

The implementation canonicalizes drivers by ID, enumerates combinations deterministically, solves the identifiable `n - 1` parameter system with one parameter fixed to zero, and calculates the analytic covariance Jacobian. It refuses non-finite, infeasible, or non-convergent inputs. A successful result must have total probability one, complete unique combinations, reconstructed marginals within `1e-8`, and a reconstructed marginal sum of three.

## User flow

On a supported race page, the user opens the Podium Outcome Lab after reviewing the marginal forecast. The page lazily requests the derived distribution and shows:

- the most likely unordered podium sets and their cumulative probability;
- the driver pairs most likely to share a podium;
- distribution entropy and effective outcome count as concentration diagnostics;
- the maximum marginal reconstruction error as a numerical integrity check;
- the frozen model identity and a persistent evidence-boundary explanation.

The interface resolves driver names from the recorded race grid, preserves an explicit “unordered set” label, and does not display first, second, or third positions. It is unavailable before 2022 because those seasons overlap model training or selection.

## API contract

`GET /api/predictions/{race_id}/podium-outcomes?limit=12`

`limit` is an integer from 3 through 25. The response is a frozen, extra-field-forbidden Pydantic contract containing:

- schema, race, experiment, and frozen-model identity;
- the derivation method, podium size, complete combination count, probability sums, entropy, effective outcome count, returned count, returned mass, and maximum reconstruction error;
- the requested leading unordered podium sets, each with a deterministic rank, three canonical driver IDs, and probability;
- reconstructed marginals for every starter, matched to the released probability and forecast rank;
- the leading co-podium driver pairs and their probabilities;
- an evidence boundary with outcome use, separate joint-model training, joint-forecast validation, causality, and ordering semantics stated explicitly.

The endpoint is read-only and receives public five-minute caching under the existing HTTP policy. The bounded limit changes only how many ranked outcomes are returned; diagnostics and pair probabilities always derive from the complete distribution.

## Safety and observability

The solver accepts only the verified predictor output for a supported stored race. Callers cannot submit probabilities, features, outcomes, driver sets, SQL, or model parameters. Errors use the existing bounded prediction exception path.

A `podium_outcomes_complete` event records only request ID, race ID, model version, method, elapsed time, driver count, combination count, returned count, distribution sum, and maximum reconstruction error. It does not record names, probabilities by driver, feature values, questions, SQL, credentials, URLs, or paths.

The public release verifier checks the exact response allowlist, deterministic ordering, combination and pair uniqueness, model identity, probability bounds, total mass, returned mass, entropy bounds, marginal agreement with the released endpoint, and every evidence-boundary flag without persisting the public response body.

## Verification

- mathematical unit tests for exact symmetry, marginal reconstruction, permutation invariance, determinism, invalid inputs, and non-convergence refusal;
- real-artifact tests across all 68 supported 2022–2024 races for complete convergence, probability coherence, marginal error, and bounded latency reporting;
- API tests for the strict allowlist, limit validation, unsupported-race refusal, cache policy, and correlated safe log;
- React tests for lazy loading, race reset, driver-name resolution, ranked sets, pair rendering, diagnostics, errors, unsupported years, and accessible labels;
- public verifier tests for adversarial contract changes and numeric inconsistencies;
- full Python, frontend, formatting, lint, dependency, build, PostgreSQL integration, infrastructure, browser, accessibility, performance, and deployed-image provenance gates;
- byte-for-byte preservation of every supplied presentation file.
