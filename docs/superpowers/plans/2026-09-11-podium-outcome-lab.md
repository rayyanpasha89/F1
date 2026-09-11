# Podium Outcome Lab implementation plan

**Goal:** Ship a read-only, mathematically coherent view of likely unordered podium sets through the existing frozen-model, FastAPI, React, verification, CI, and AWS release path.

**Architecture:** Convert one verified race prediction into the maximum-entropy distribution over all fixed-size three-driver sets. A strict service exposes bounded outcomes, co-podium pairs, and integrity diagnostics. React resolves recorded driver names and renders the result only on demand. The public verifier independently compares reconstructed marginals with the released prediction endpoint.

## Tasks

- [x] Prove solver feasibility and latency across all 68 supported races.
- [x] Freeze the statistical, API, evidence, logging, and UX contracts.
- [ ] Add failing mathematical service and real-artifact tests.
- [ ] Implement the deterministic maximum-entropy fixed-size solver and strict response models.
- [ ] Add the GET endpoint, bounded refusal paths, cache behavior, and safe structured event.
- [ ] Add failing endpoint, contract, and logging tests, then make them pass.
- [ ] Add failing React interaction tests, then build the Podium Outcome Lab UI.
- [ ] Add responsive, accessible styling and reduced-motion-compatible states.
- [ ] Extend the append-only public verifier and its adversarial tests.
- [ ] Update the model card, architecture, evaluation, deployment, demo, README, and chronological worklog documentation.
- [ ] Run focused and full local verification, including the 68-race sweep and PostgreSQL integration.
- [ ] Preserve supplied presentation files byte-for-byte.
- [ ] Review, merge, push, wait for GitHub Actions, and build the exact merge commit on AWS.
- [ ] Deploy the immutable image only after guarded account and region checks.
- [ ] Verify the public API, browser flows, accessibility, performance, logs, and deployed-image provenance.
