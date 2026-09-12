# F1 Race Strategist

An academic Formula 1 intelligence application with historical dashboards and genuine, explainable podium predictions. Built progressively with tested Git milestones. **The AWS dev application is live on [Lightsail](https://f1-strategist-demo.ys85rp5g9ncdj.eu-north-1.cs.amazonlightsail.com/). See `docs/worklog.md` for release and verification checkpoints.**

## Implemented

- Audited 14-table CSV snapshot: 701,433 rows, 1950–2024; source checksums, missingness, key checks and yearly coverage.
- Transactional SQLite/PostgreSQL ingestion with SQLAlchemy metadata, enforced relationships and indexes; both engines verified with the supplied data.
- FastAPI season/race endpoints, recorded standings, driver/constructor profiles, qualifying, grid, results and pit summaries.
- Race driver comparisons with earlier form and circuit history, profile recent-form summaries, conservative chat spelling repair and ambiguity clarification, and charts from suitable executed query results.
- React historical navigation with responsive tables and loading/error/empty states; real API data throughout.
- Measured grid-only logistic baseline and feature/model experiments with chronological validation.
- Frozen calibrated gradient boosting predictor for historical 2022–2024 races, with actual SHAP explanations, grid-baseline comparison, and a deterministic race-level projection that makes every forecast sum to the three available podium places.
- Forecast-versus-reality review for every supported completed race, including predicted and recorded podiums, whole-grid Brier/absolute error, surprise drivers, and an explicit label boundary.
- Interactive Podium Outcome Lab that derives one coherent probability distribution over every unordered three-driver podium set, exactly reconstructs the released driver marginals, ranks complete sets and co-podium pairs, and discloses that it is a maximum-entropy derivation rather than a separately trained finishing-order model.
- Interactive Grid Scenario Lab that swaps two recorded starters, reruns the same frozen model, and compares every probability, rank, actual grid position, transformed model input, and starting-grid SHAP contribution without mutating data.
- Public Model Lab with verified lineage hashes, temporal split, raw/projected metrics, paired whole-race bootstrap intervals, per-season evidence, limitations, and the consumed-test disclosure.
- Bedrock `openai.gpt-oss-120b` chat with bounded query augmentation, database-derived entity and schema reranking, compact follow-up context, one controlled SQL repair, visible audit trace, genuine prediction routing and unsupported-data refusals.
- Parser policy, read-only database access, 200-row caps, query timeouts, destructive-query rejection and optional chat access code.
- Startup verification of model/evidence hashes before deserialization, readiness checks for database/model/card, generated request IDs, security and cache headers, gzip, safe inference telemetry, and an append-only public release verifier.
- Four executed reproducibility notebooks, fixed 40-question live benchmark and passing GitHub Python/frontend CI.

## Local setup

Python 3.11 and Node.js 22.12+ are required (tested locally with Python 3.11 and Node 26). From the repository root:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
npm ci --prefix frontend
```

Place the original supplied CSVs in `dataset/`. The files are not redistributed: the package did not include a license/download receipt. Obtain the project's exact source package and verify fingerprints in `reports/data_audit.json`. A clone alone does not contain the dataset or generated database/model binaries.

```sh
python -m scripts.audit_data
python -m scripts.load_data
python -m scripts.train_baseline
python -m scripts.compare_models
python -m scripts.check_calibration
python -m scripts.evaluate_final
python -m scripts.evaluate_probability_projection
python -m scripts.evaluate_podium_outcomes
python -m scripts.build_model_manifest
```

The loader refuses to overwrite a populated database. To reproduce ingestion again, supply a new project database with `--url sqlite:///database/reproduction.db`; use the matching `DATABASE_URL` for the backend and training. Never replace source data silently. Audit changes must be reviewed against the committed report and schema mapping.

Run these in two terminals:

```sh
# Terminal 1, virtual environment active
uvicorn backend.main:app --host 127.0.0.1 --port 8000
# Terminal 2
npm run dev --prefix frontend
```

Copy `.env.example` to `.env` and supply the AWS Bedrock Mantle key/base URL/project ID for chat; credentials stay server-side. The model is `openai.gpt-oss-120b`. Set `CHAT_ACCESS_CODE` to protect billable calls when sharing the app. PostgreSQL chat additionally requires `SQL_READONLY_DATABASE_URL` pointing to a SELECT-only role.

Open `http://127.0.0.1:5173`. FastAPI documentation is at `http://127.0.0.1:8000/docs`. Vite proxies `/api` to the local backend. Data are historical; there is no live feed. Select 2024, open Monaco, compare results/grid/qualifying, select a driver in the probability panel to see SHAP factors, build the Podium Outcome Lab map, then exchange two starters in the Grid Scenario Lab. Prediction-derived features and scenarios for pre-2022 races are intentionally unavailable because those years overlap fit/selection.

## Tests and evidence

```sh
pytest -q
ruff check backend scripts tests
ruff format --check backend scripts tests
npm test --prefix frontend
npm run build --prefix frontend
pip-audit --requirement requirements.runtime.lock --no-deps --disable-pip
npm audit --omit=dev --audit-level=high --prefix frontend
```

With the production-style server running, execute the black-box release contract into a new path. Add `--access-code-file` only when one bounded Bedrock typo-correction check is intended; the report never stores the code, question, SQL, answer, provider payload, or file path.

```sh
python -m scripts.verify_public_release \
  --base-url http://127.0.0.1:8000 \
  --output reports/public_release_new.json
```

At the Podium Outcome Lab local gate, 185 Python tests pass in the complete artifact/source-backed suite with only the four opt-in PostgreSQL checks skipped; those four pass separately against an isolated PostgreSQL 16.15 database with a dedicated `SELECT`-only role. The frontend supplies 22 passing tests. Some source/model integration tests skip when local artifacts are absent; a lightweight clone-only run is not full data/ML verification. Upstream TestClient/SHAP deprecation warnings are recorded. The 68-race derivation sweep solved all 77,349 complete sets with maximum marginal error `3.82e-13`. The production-style verifier passed the full outcome contract, and browser checks exercised its complete desktop and 390-pixel flows with no console errors, failed requests, accessibility-tree gaps, or horizontal overflow. See `reports/podium_outcome_local_evaluation.json` and `reports/podium_outcome_local_release.json`.

## Architecture

CSV → validated relational storage → FastAPI analytics / chronological feature pipeline → frozen ML model → React views. Statistics route through database-derived entity retrieval, conservative spelling repair, schema/terminology-grounded Bedrock SQL generation, parser validation and a separate read-only connection. Ambiguous names require clarification. Prediction/explanation questions call the frozen model directly, and named-driver explanations select that driver's actual model output. The podium-outcome endpoint converts the verified marginal probabilities into the unique maximum-entropy distribution over all fixed-size three-driver subsets and returns bounded ranked sets, co-podium pairs, and reconstruction diagnostics. The grid scenario endpoint copies one supported race frame and exchanges only two allowlisted grid inputs before using the same verified model and race projection. Unsupported requests return a capability-based refusal. Factual answers are rendered from executed rows or model outputs, not invented narrative statistics. Production ML logic lives in Python modules, not notebooks. Model artifacts must be locally generated or trusted: joblib files are not safe to load from untrusted uploads.

The executable schema is `backend/database.py` with committed `knowledge/schema.json`; SQL DDL is in `database/schema.sql`. Backend queries are centralized in `backend/services/analytics.py`. Dataset details: `docs/data_audit.md`. The final architecture is in `docs/architecture.md`, the presentation is `docs/presentations/F1_Race_Strategist_Final_Review.pptx`, and the exact walkthrough is `docs/final_demo_guide.md`. Decisions: `docs/decisions/`. Engineering history: `docs/worklog.md`. AI disclosure: `AI_ASSISTANCE.md`.

## ML methodology and results

Fit years 2010–2018; model selection 2019–2021; final test 2022–2024. Features are emitted before updating any same-date history. Past completed test races can inform later features, but no test outcomes fit parameters. Explicit mutation tests exercise same-race, future and teammate leakage. Model and training-only temporal calibration were committed before final-test evaluation.

| Consumed 2022–2024 test | Projected grid baseline | Projected selected model |
|---|---:|---:|
| Log loss | 0.249804 | 0.218918 |
| Brier score | 0.073772 | 0.069044 |
| ROC-AUC | 0.913876 | 0.936552 |
| Top-three hit rate | 0.651961 | 0.647059 |

Probability scores improved; top-three hit rate did not. The projected selected model is also better than the projected grid baseline for log loss and Brier score, while the paired top-three interval crosses zero. These outcomes had already been consumed before the structural postprocessor was assessed, so they are explicitly labeled post-test iterative evidence rather than a fresh holdout. `EXPERIMENTS.md` retains the baseline, failed/qualified hypotheses, feature ablations and calibration choices. `docs/evaluation.md` explains metrics and limitations. Machine-readable reports include per-season scores, calibration bins, projection checks, and whole-race bootstrap intervals. SHAP contributions reconstruct the projected probability after the race offset is added to the base; they remain associations in calibrated log-odds, not causal effects.

## Data and operational boundaries

The dataset lacks weather, tyres and telemetry. Coverage of qualifying/laps/pits varies. Historical results include repeated driver/race records; final standings cannot be replaced by simple points sums. Historical grids may reflect later corrections; original point-in-time provenance is unavailable. A bounded log-odds projection makes each displayed race sum to three while preserving the raw model ranking. The Podium Outcome Lab then produces a coherent joint distribution over unordered three-driver sets under a maximum-entropy assumption; it is not a learned interaction model, an ordered podium forecast, or independent validation evidence. Grid swaps show sensitivity inside the fitted model, not the physical or causal effect of moving a real car. No betting or live race functionality is implemented.

The fixed NL2SQL suite contains 30 analytics questions and 10 refusal cases. Live Run 09 passed 40/40 with 3.651-second mean latency after relationship-aware schema routing fixes; Runs 07 and 08 preserve the two 39/40 failures that led to those regressions. The separate Agentic Run 01 passed 22/22 with 3.013-second mean latency, 29 total calls and no live SQL repair. Runs 01–09 remain preserved, and NL2SQL Run 01 is diagnostic because a validator defect also blocked reference SQL. These iteratively used development suites are not unseen generalization estimates. Answer scoring checks row multisets and positional columns with numerical tolerance; it does not score row ordering. Join-table/key checks are structural proxies. Reproduce with a new output path (billable):

```sh
python -m scripts.benchmark_nl2sql --output reports/nl2sql_new_run.json
python -m scripts.benchmark_agentic --output reports/agentic_new_run.json
python -m scripts.execute_notebooks
```

The agentic development suite is separate from the immutable 40-case NL2SQL suite. It checks spelling corrections, ranked entities and tables, ambiguity, follow-ups, safe refusals, exact executed rows, provider-call counts, repair counts and latency. Both suites were used during development and are not unseen generalization estimates.

Chat has two concurrent slots, six requests/minute per client and 200/day per process. Limits reset on restart; behind the internal load balancer clients may share a limit. The access code is the primary demo access control, not individual user authentication. Browser chat history lives in session storage; the code stays in memory. Model-supplied assumptions are displayed as assumptions, not validated facts.

## AWS

The verified dev application runs at [the AWS Lightsail HTTPS endpoint](https://f1-strategist-demo.ys85rp5g9ncdj.eu-north-1.cs.amazonlightsail.com/), backed by private PostgreSQL 16.15. Lightsail deployment 18 is `RUNNING` / `ACTIVE` on immutable application image `74e60f2dcb74e2cab956321f0b1212f3cccfaeb1` with ECR digest `sha256:5efd1bf5722b1a6172b4855f05429ec5c04030b5376e4a61f3e46c42ab6e7109`. GitHub Actions run [`34659314030`](https://github.com/rayyanpasha89/F1/actions/runs/34659314030) and CodeBuild `f1-race-strategist-dev:502ca3f9-8a94-478c-a0b0-6901d5e6b786` passed for that exact source. The current public and combined evidence are in `reports/podium_outcome_aws_release_v18.json` and `reports/podium_outcome_cloud_verification.json`. The public contract passed 13 responses, including the maximum-entropy outcome map and bounded typo-tolerant Bedrock chat. Direct desktop/mobile QA found no failed request, console error, or horizontal overflow; Lighthouse scored 100 in all four categories at both sizes. CloudWatch stream `lightsail/20260911T235935380383Z` contains 172 deployment-18 events, including prediction, outcome, scenario, review, and chat completions. Every structured event matched its allowlist, and protected values, credential names, question text, SQL, outcome identities, and outcome URLs had zero matches. The protected presentation files were not edited.

Account is restricted to confirmed non-Naaz **148356747273**, profile **default**, region **eu-north-1**. Lightsail costs about $30/month plus Bedrock and incidental usage. The earlier partial S3/CloudFront/ECS/RDS plan left billable ALB/supporting resources; no destructive cleanup was authorized. Deployment, rollback, logging, security tradeoffs and retained costs are in `docs/deployment.md`, ADR 005 and ADR 006.
