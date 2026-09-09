# F1 Race Strategist

An academic Formula 1 intelligence application with historical dashboards and genuine, explainable podium predictions. Built progressively with tested Git milestones. **The AWS dev application is live on [Lightsail](https://f1-strategist-demo.ys85rp5g9ncdj.eu-north-1.cs.amazonlightsail.com/). See `docs/worklog.md` for release and verification checkpoints.**

## Implemented

- Audited 14-table CSV snapshot: 701,433 rows, 1950–2024; source checksums, missingness, key checks and yearly coverage.
- Transactional SQLite/PostgreSQL ingestion with SQLAlchemy metadata, enforced relationships and indexes; both engines verified with the supplied data.
- FastAPI season/race endpoints, recorded standings, driver/constructor profiles, qualifying, grid, results and pit summaries.
- Race driver comparisons with earlier form and circuit history, profile recent-form summaries, conservative chat spelling repair and ambiguity clarification, and charts from suitable executed query results.
- React historical navigation with responsive tables and loading/error/empty states; real API data throughout.
- Measured grid-only logistic baseline and feature/model experiments with chronological validation.
- Frozen calibrated gradient boosting predictor for historical 2022–2024 races, with actual SHAP explanations and baseline comparison.
- Bedrock `openai.gpt-oss-120b` chat with separate intent/SQL stages, database-derived entity grounding, visible executed SQL, genuine prediction routing and unsupported-data refusals.
- Parser policy, read-only database access, 200-row caps, query timeouts, destructive-query rejection and optional chat access code.
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

Open `http://127.0.0.1:5173`. FastAPI documentation is at `http://127.0.0.1:8000/docs`. Vite proxies `/api` to the local backend. Data are historical; there is no live feed. Select 2024, open Monaco, compare results/grid/qualifying, then select a driver in the probability panel to see SHAP factors. Predictions for pre-2022 races are intentionally unavailable because those years overlap fit/selection.

## Tests and evidence

```sh
pytest -q
ruff check backend scripts tests
ruff format --check backend scripts tests
npm test --prefix frontend
npm run build --prefix frontend
```

At this checkpoint, 72 Python tests and 5 frontend tests pass; three additional opt-in PostgreSQL integration tests passed against the isolated local database. Some source/model integration tests skip when local artifacts are absent; a lightweight clone-only test run is not full data/ML verification. Five upstream TestClient/SHAP deprecation warnings are recorded. Browser checks exercised standings → Monaco → qualifying → driver profile and the real prediction panel, including a 390px viewport.

## Architecture

CSV → validated relational storage → FastAPI analytics / chronological feature pipeline → frozen ML model → React views. Statistics route through schema/terminology-grounded Bedrock SQL generation, parser validation and a separate read-only connection. Prediction/explanation questions call the frozen model directly. Unsupported requests return a capability-based refusal. Factual answers are rendered from executed rows or model outputs, not invented narrative statistics. Production ML logic lives in Python modules, not notebooks. Model artifacts must be locally generated or trusted: joblib files are not safe to load from untrusted uploads.

The executable schema is `backend/database.py` with committed `knowledge/schema.json`; SQL DDL is in `database/schema.sql`. Backend queries are centralized in `backend/services/analytics.py`. Dataset details: `docs/data_audit.md`. Decisions: `docs/decisions/`. Engineering history: `docs/worklog.md`. AI disclosure: `AI_ASSISTANCE.md`.

## ML methodology and results

Fit years 2010–2018; model selection 2019–2021; final test 2022–2024. Features are emitted before updating any same-date history. Past completed test races can inform later features, but no test outcomes fit parameters. Explicit mutation tests exercise same-race, future and teammate leakage. Model and training-only temporal calibration were committed before final-test evaluation.

| Final test | Grid baseline | Selected model |
|---|---:|---:|
| Log loss | 0.249898 | 0.219846 |
| Brier score | 0.073811 | 0.069285 |
| ROC-AUC | 0.913827 | 0.935364 |
| Top-three hit rate | 0.651961 | 0.647059 |

Probability scores improved; top-three hit rate did not. No universal superiority is claimed. `EXPERIMENTS.md` retains the baseline, failed/qualified hypotheses, feature ablations and calibration choices. `docs/evaluation.md` explains metrics and limitations. Machine-readable reports include per-season test scores and calibration bins. SHAP contributions reconstruct the calibrated probability and are associations in log-odds, not causal effects.

## Limits and remaining work

The dataset lacks weather, tyres and telemetry. Coverage of qualifying/laps/pits varies. Historical results include repeated driver/race records; final standings cannot be replaced by simple points sums. Historical grids may reflect later corrections; original point-in-time provenance is unavailable. Independent podium probabilities need not sum to three. No betting or live race functionality is implemented.

The fixed NL2SQL suite contains 30 analytics questions and 10 refusal cases. Live run 05 passed 40/40 after four preserved diagnostic/development runs; mean latency across all cases was 3.707 seconds. This is an iteratively used development suite, not an unseen generalization estimate. Answer scoring checks row multisets and positional columns with numerical tolerance; it does not score row ordering. Join-table/key checks are structural proxies. Full reports preserve failures and generated SQL. Reproduce with a new output path (billable):

```sh
python -m scripts.benchmark_nl2sql --output reports/nl2sql_new_run.json
python -m scripts.execute_notebooks
```

Chat has two concurrent slots, six requests/minute per client and 200/day per process. Limits reset on restart; behind the internal load balancer clients may share a limit. The access code is the primary demo access control, not individual user authentication. Browser chat history lives in session storage; the code stays in memory. Model-supplied assumptions are displayed as assumptions, not validated facts.

## AWS

Terraform defines dedicated S3/CloudFront, internal ALB, ECR/ECS Fargate, private RDS PostgreSQL, Secrets Manager, CodeBuild and CloudWatch resources. Account is explicitly restricted to confirmed non-Naaz **148356747273**, profile **default**, region **eu-north-1**. The first reviewed plan has 49 additions and no changes/deletions; infrastructure creation is in progress. Do not infer cloud readiness from these definitions. Deployment procedure, rough $55–75/month dev cost, persistent charges, TLS boundaries, rollback and state limitations are in `docs/deployment.md` and ADR 005. Cloud verification and final adversarial review remain pending.
