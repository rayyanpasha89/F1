# Grid Scenario Lab implementation plan

**Goal:** Ship a read-only, tested grid-swap sensitivity simulator through the existing React, FastAPI, verified-model, CI, and AWS release path.

**Architecture:** Refactor the predictor around one race-frame calculation, then compare an untouched frame with a copied frame whose two `grid_position` values are exchanged. A strict scenario service converts the internal predictions into a small public contract. React renders the comparison on supported race pages, and the release verifier checks one bounded scenario against the public origin.

## Tasks

- [x] Add failing predictor and scenario-contract tests.
- [x] Refactor prediction calculation without changing the existing endpoint contract.
- [x] Add strict grid-swap request/response models and scenario service.
- [x] Add the POST endpoint, safe refusal paths, and bounded structured event.
- [x] Add API and log tests, including `no-store` delivery.
- [x] Add the Grid Scenario Lab React flow and component tests.
- [x] Add responsive, accessible styling and reduced-motion behavior.
- [x] Extend the append-only public verifier and its adversarial tests.
- [x] Update model accountability, architecture, evaluation, deployment, demo, adversarial review, README, and worklog documentation.
- [x] Run focused and full local verification, including PostgreSQL integration and infrastructure checks.
- [x] Preserve supplied presentation files byte-for-byte.
- [ ] Review, merge, push, wait for GitHub Actions, and build the exact merge commit on AWS.
- [ ] Deploy the immutable image only after guarded account and region checks.
- [ ] Verify public API, browser flows, accessibility, performance, logs, and deployed-image provenance.
