# Model Accountability Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship coherent podium probabilities, verified artifact lineage, a Forecast vs Reality Race Lab, a public model card, hardened HTTP delivery, and complete local/cloud evidence without modifying any PowerPoint.

**Architecture:** A pure race-level logit projection adjusts both model and baseline marginals to sum to the known three podium slots while preserving rank and SHAP additivity. A manifest binds trusted artifacts and reports; dedicated services expose allowlisted model-card and post-race review contracts. React consumes those contracts, while middleware, readiness checks, CI audits, and release verification harden the deployed system.

**Tech Stack:** Python 3.11, NumPy, pandas, scikit-learn, SHAP, FastAPI, Pydantic v2, SQLAlchemy, React 19, Vite, Vitest, AWS CodeBuild/ECR/Lightsail/PostgreSQL/CloudWatch, Terraform 1.13.5.

**Spec:** `docs/superpowers/specs/2026-09-10-model-accountability-design.md`

## Global Constraints

- Do not create, edit, regenerate, replace, or stage any `.pptx` file.
- Preserve the existing fixed NL2SQL and agentic benchmark files byte-for-byte.
- Use no same-race or future outcome as a prediction input.
- Treat the already-consumed 2022–2024 test as iterative post-test evidence.
- Keep the database/model as factual sources; Bedrock never generates probabilities or post-race metrics.
- Keep AWS mutations restricted to account `148356747273`, profile `default`, explicit region `eu-north-1`.
- Do not delete or modify unrelated or retained AWS resources.
- Use focused failing tests before each behavior change and preserve chronological commits.

---

### Task 1: Establish the isolated release workspace and plan evidence

**Files:**
- Create: `docs/superpowers/plans/2026-09-10-model-accountability.md`

**Interfaces:**
- Consumes: approved design in `docs/superpowers/specs/2026-09-10-model-accountability-design.md`
- Produces: isolated `feat/model-accountability` worktree and exact execution checklist

- [x] Record SHA-256 for both existing presentation files before implementation.
- [x] Detect whether the checkout is already a linked worktree and verify `.worktrees/` is ignored.
- [x] Create `.worktrees/model-accountability` on branch `feat/model-accountability` using `git worktree add` because no native worktree tool is available.
- [x] Copy only ignored local verification inputs required by the plan: the SQLite database, two trusted joblib artifacts, processed features, and audited source CSV directory. Do not copy `.env`, Terraform state, or credentials.
- [x] Reuse dependencies through safe ignored symlinks or install from lock files; do not commit environment directories.
- [x] Run `.venv/bin/pytest -q -rs`, frontend tests/lint/format/build, Ruff, and both Terraform validations. Require the same green baseline before feature code.
- [x] Commit this plan on the feature branch with `git commit -m "docs: plan model accountability release"`.

### Task 2: Add the race-level podium probability projection

**Files:**
- Create: `backend/ml/probability.py`
- Create: `tests/test_probability.py`
- Modify: `backend/ml/predictor.py`
- Modify: `tests/test_ml.py`

**Interfaces:**
- Produces: `project_expected_count(probabilities: Sequence[float], expected_count: int = 3) -> ProbabilityProjection`
- Produces: immutable `ProbabilityProjection(adjusted: np.ndarray, log_odds_offset: float, raw_sum: float, adjusted_sum: float, expected_count: int)`
- Changes: `Predictor.predict(race_id)` adds `model_version`, `postprocessing`, per-driver `raw_probability`, and `raw_baseline_probability`; `probability` and `baseline_probability` become projected values

- [x] Write failing pure tests requiring deterministic finite output, exact sum within `1e-10`, strict bounds, stable ordering, symmetry for equal inputs, and controlled rejection of NaN, out-of-range values, too few entrants, or impossible expected counts.
- [x] Run `.venv/bin/pytest tests/test_probability.py -q` and capture the missing-module failure.
- [x] Implement clipped-logit monotonic bisection with no labels or outcomes and a maximum fixed iteration count.
- [x] Run the focused tests and require them to pass.
- [x] Add failing predictor tests requiring both selected and baseline sums to equal three and SHAP reconstruction to use `base_log_odds + postprocessing.log_odds_offset + sum(factors)` exactly.
- [x] Update `Predictor.predict` to project selected and baseline arrays, expose audit metadata, and adjust each driver's explanation base without changing factors or rank.
- [x] Run `.venv/bin/pytest tests/test_probability.py tests/test_ml.py tests/test_api.py -q` and require all focused tests to pass.
- [x] Commit with `git commit -m "ml: enforce coherent race podium probabilities"`.

### Task 3: Generate the post-test projection evaluation and artifact manifest

**Files:**
- Create: `scripts/evaluate_probability_projection.py`
- Create: `scripts/build_model_manifest.py`
- Create: `reports/race_constraint_evaluation.json`
- Create: `models/manifest.json`
- Create: `tests/test_model_evidence.py`
- Modify: `.gitignore`
- Modify: `EXPERIMENTS.md`
- Modify: `docs/evaluation.md`

**Interfaces:**
- Produces: `evaluate_projection(frame, artifact, baseline, bootstrap_replicates=5000, seed=42) -> dict`
- Produces: `build_manifest(root: Path) -> dict`
- Manifest schema: `f1-model-manifest-v1` with artifact/report/source hashes, split years, features, calibration, and postprocessor

- [x] Add failing tests for deterministic whole-race bootstrap output, rank preservation, validation ship gates, explicit consumed-test labeling, required hashes, and no secret/path fields.
- [x] Run `.venv/bin/pytest tests/test_model_evidence.py -q` and confirm the missing implementations fail.
- [x] Implement evaluation for raw/projected selected model and raw/projected baseline on validation and consumed-test splits, per-season metrics, average probability sums, and paired whole-race bootstrap differences.
- [x] Implement manifest generation using SHA-256 and allowlisted model-selection metadata; add `!models/manifest.json` to `.gitignore`.
- [x] Execute both scripts from the trusted local artifacts. Require validation log loss and Brier improvement, unchanged rank, exact expected sums, and reproducible output apart from the explicit generation timestamp.
- [x] Document the structural method and the consumed-test evidence boundary in `EXPERIMENTS.md` and `docs/evaluation.md`.
- [x] Run the focused tests and JSON/schema checks.
- [x] Commit with `git commit -m "ml: record probability coherence and model lineage"`.

### Task 4: Verify model artifacts before deserialization and expose readiness

**Files:**
- Modify: `backend/ml/predictor.py`
- Create: `backend/ml/evidence.py`
- Modify: `backend/main.py`
- Modify: `tests/test_ml.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_deployment_contract.py`
- Modify: `.dockerignore`
- Modify: `Dockerfile`
- Modify: `buildspec.yml`
- Modify: `scripts/release_aws.py`
- Modify: `scripts/release_lightsail.py`

**Interfaces:**
- Produces: `load_manifest(path: Path = ROOT / "models/manifest.json") -> ModelManifest`
- Produces: `verify_model_bundle(root: Path = ROOT) -> ModelManifest`
- Produces: `GET /api/health/ready -> {status, archive_through, model_version, checks}`

- [x] Write failing tests proving hashes are checked before `joblib.load`, manifest/report mismatches fail with controlled `PredictionUnavailable`, and invalid calibration/features/interfaces are rejected.
- [x] Add failing API tests for a successful allowlisted readiness response and safe 503 behavior without filesystem paths or exception text.
- [x] Implement strict Pydantic manifest models and bundle validation, then call verification before deserialization.
- [x] Make production lifespan validate read-only PostgreSQL and the complete model bundle; keep `/api/health` as liveness and add `/api/health/ready`.
- [x] Include only the manifest, projection report, final metrics, model selection, and data audit evidence in the container.
- [x] Make release packaging validate the bundle before upload and include the manifest. Make CodeBuild call the real verifier. Change Lightsail health checks to `/api/health/ready`.
- [x] Run focused ML/API/deployment tests and a local Docker-context inclusion audit without printing secrets.
- [x] Commit with `git commit -m "security: verify model lineage at runtime"`.

### Task 5: Build the Forecast vs Reality review service and API

**Files:**
- Create: `backend/ml/review.py`
- Create: `tests/test_race_review.py`
- Modify: `backend/main.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `RaceReviewService(predictor: Predictor, analytics: Analytics).review(race_id: int) -> RaceReview`
- Produces: `GET /api/predictions/{race_id}/review`
- `RaceReview` contains allowlisted race, predicted/recorded podiums, hit count, exact-set flag, Brier/MAE, deterministic surprises, driver rows, and leakage notes

- [x] Write failing synthetic tests for metric arithmetic, stable tie-breaking, missing podium rejection, unsupported model years, and bounded/allowlisted serialization.
- [x] Add failing mutation tests proving same-race outcome changes cannot alter forecast probabilities/factors and future outcomes cannot alter an earlier review.
- [x] Run `.venv/bin/pytest tests/test_race_review.py -q` and confirm missing service failures.
- [x] Implement Pydantic response models and the review service by joining the predictor output to recorded results after prediction is complete.
- [x] Add the API route and controlled exception behavior.
- [x] Add a real-data integration assertion that Monaco 2024 has three predicted-podium hits and deterministic Brier arithmetic without hard-coding the backend answer.
- [x] Run focused review/API/ML tests.
- [x] Commit with `git commit -m "feat: add forecast versus reality race review"`.

### Task 6: Expose a bounded public model card

**Files:**
- Create: `backend/ml/model_card.py`
- Create: `tests/test_model_card.py`
- Modify: `backend/main.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `ModelCardService(root: Path = ROOT).get() -> ModelCard`
- Produces: `GET /api/model-card`
- The response allowlists identity, lineage hashes, temporal split, features, metrics, bootstrap intervals, calibration, intended use, and limitations

- [ ] Write failing tests for exact allowlisted top-level fields, manifest/report agreement, finite metrics, temporal ordering, consumed-test disclosure, and absence of paths/secrets/serialized objects.
- [ ] Run the focused tests and confirm the missing service/route failures.
- [ ] Implement Pydantic model-card contracts and deterministic assembly from validated committed evidence.
- [ ] Add the API route and make readiness validate that the card can be assembled.
- [ ] Run model-card, API, and bundle tests.
- [ ] Commit with `git commit -m "feat: publish verified model accountability data"`.

### Task 7: Add the Model Accountability and Race Lab frontend

**Files:**
- Create: `frontend/src/ForecastReview.jsx`
- Create: `frontend/src/ForecastReview.test.jsx`
- Create: `frontend/src/ModelLab.jsx`
- Create: `frontend/src/ModelLab.test.jsx`
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/Predictions.jsx`
- Modify: `frontend/src/style.css`

**Interfaces:**
- `ForecastReview({raceId, year})` consumes `/predictions/{raceId}/review`
- Lazy `ModelLab` consumes `/model-card`
- Route: `/model`; header label: `Model accountability`

- [ ] Write failing component tests for review success, exact post-race labeling, predicted/recorded podiums, Brier semantics, surprises, loading/error/unavailable states, and model-page link.
- [ ] Write failing Model Lab tests for temporal split, before/after metric table, uncertainty intervals, lineage, limitations, and accessible headings.
- [ ] Run focused Vitest files and confirm missing components fail.
- [ ] Implement Forecast Review after the existing prediction panel without mixing result labels into forecast language.
- [ ] Implement the lazy Model Lab route with native HTML/CSS visualizations and add navigation.
- [ ] Add responsive styles and keep controls keyboard accessible.
- [ ] Run focused and full frontend tests, ESLint, Prettier, and Vite build. Inspect chunk output to confirm Model Lab is separate from the initial bundle.
- [ ] Commit with `git commit -m "ui: add model accountability race lab"`.

### Task 8: Harden HTTP delivery, runtime telemetry, and dashboard stability

**Files:**
- Create: `backend/http.py`
- Create: `tests/test_http.py`
- Modify: `backend/main.py`
- Modify: `backend/web.py`
- Modify: `tests/test_web.py`
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/style.css`
- Modify: `frontend/index.html`
- Create: `frontend/public/robots.txt`

**Interfaces:**
- Produces: `install_http_policy(app: FastAPI) -> None`
- Every response receives a generated `X-Request-ID`; health/chat are `no-store`; historical GET APIs are short-cache; hashed assets are immutable

- [ ] Write failing tests for request IDs, CSP, HSTS, nosniff, frame denial, referrer/permissions policy, gzip, cache rules, and immutable hashed assets.
- [ ] Add failing frontend tests or DOM assertions for reserved standings loading geometry and metadata files.
- [ ] Implement the middleware with server-generated identifiers and no request/header reflection.
- [ ] Add safe `prediction_complete` and `review_complete` logs containing only request ID, race ID, model version, postprocessor, elapsed time, probability sum, and hit count.
- [ ] Set asset cache headers, shell no-cache, valid meta description/title, and robots policy.
- [ ] Add an accessible table skeleton/reserved layout that removes asynchronous standings shift without hiding status text.
- [ ] Run HTTP/web/API/frontend tests and verify logs exclude sentinel secrets, SQL, paths, and question content.
- [ ] Commit with `git commit -m "perf: harden delivery and inference telemetry"`.

### Task 9: Enforce dependency and release verification gates

**Files:**
- Create: `.github/dependabot.yml`
- Modify: `.github/workflows/validate.yml`
- Create: `scripts/verify_public_release.py`
- Create: `tests/test_verify_public_release.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/deployment.md`
- Modify: `AI_ASSISTANCE.md`
- Modify: `docs/adversarial_review.md`

**Interfaces:**
- Produces: append-only CLI `python -m scripts.verify_public_release --base-url URL --output NEW.json [--access-code-file PATH]`
- Verifier checks route/status/schema/header/model-sum/review/model-card/readiness and optional bounded chat; it never writes access codes or provider configuration

- [ ] Write failing verifier tests using an in-process HTTP server for no-overwrite behavior, safe output, route contracts, headers, coherent probabilities, and optional chat redaction.
- [ ] Implement the verifier with explicit timeouts and allowlisted summaries.
- [ ] Add CI steps for `pip-audit==2.9.0` against the fully pinned runtime direct requirements with `--no-deps --disable-pip`, plus `npm audit --omit=dev --audit-level=high`.
- [ ] Add monthly Dependabot configuration for pip, npm, and GitHub Actions with a conservative open-PR limit.
- [ ] Update architecture, deployment, AI disclosure, README, and adversarial review with implemented behavior and evidence boundaries. Do not edit presentation documentation or files.
- [ ] Run verifier tests, workflow syntax checks, dependency audits, and the full standard suites.
- [ ] Commit with `git commit -m "ci: verify model accountability release"`.

### Task 10: Complete local, PostgreSQL, browser, and AWS release evidence

**Files:**
- Create: `reports/model_accountability_local_verification.json`
- Create after deployment: `reports/model_accountability_aws_release.json`
- Create after deployment: `reports/model_accountability_cloud_verification.json`
- Modify: `docs/worklog.md`
- Modify: this plan's checkboxes

**Interfaces:**
- Consumes: every artifact and verifier above
- Produces: clean synchronized `main`, exact ECR/Lightsail deployment, append-only machine-readable evidence

- [ ] Re-run 100% of Python tests with skip reasons, then all four PostgreSQL integration tests using the isolated admin and SELECT-only reader URLs without printing either value.
- [ ] Run Ruff check/format, all frontend tests/lint/format/build, both Terraform validations, model evidence regeneration comparison, whole-archive sweep, JSON parse checks, presentation hash comparison, and a sensitive-value scan.
- [ ] Record exact counts, durations, hashes, dependency audit results, projection gates, and presentation non-modification in `reports/model_accountability_local_verification.json`.
- [ ] Review the complete feature diff for leakage, fabricated evidence, artifact trust, unsafe report loading, Pydantic overexposure, cache mistakes, response/log secrets, performance regressions, and README disagreement.
- [ ] Merge `feat/model-accountability` to `main` without squashing or rewriting history, push, and wait for all GitHub jobs.
- [ ] Before each AWS mutation, run the guarded account/profile/region checks. Build the exact merge SHA in CodeBuild and wait for `SUCCEEDED`.
- [ ] Deploy the immutable image to `f1-strategist-demo`; require Lightsail `RUNNING`/`ACTIVE` and the exact image SHA.
- [ ] Run the public verifier with bounded chat, desktop/mobile browser flows, console/network checks, and Lighthouse. Require accessibility 100, best practices 100, and CLS at most 0.10.
- [ ] Retrieve bounded Lightsail logs and export a new CloudWatch snapshot. Verify prediction/review/chat events exist and sensitive values are absent.
- [ ] Write new AWS/cloud reports and worklog evidence, commit, push, wait for final CI, then reconfirm public readiness, deployed SHA, clean Git, and unchanged presentation hashes.
