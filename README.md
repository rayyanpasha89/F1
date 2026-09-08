# F1 Race Strategist

An academic Formula 1 intelligence application with historical dashboards and genuine, explainable podium predictions. Built progressively with tested Git milestones. **In development: LLM chat and AWS deployment are not complete.**

## Implemented

- Audited 14-table CSV snapshot: 701,433 rows, 1950–2024; source checksums, missingness, key checks and yearly coverage.
- Transactional SQLite ingestion with SQLAlchemy metadata, enforced relationships and indexes.
- FastAPI season/race endpoints, recorded standings, driver/constructor profiles, qualifying, grid, results and pit summaries.
- React historical navigation with responsive tables and loading/error/empty states; real API data throughout.
- Measured grid-only logistic baseline and feature/model experiments with chronological validation.
- Frozen calibrated gradient boosting predictor for historical 2022–2024 races, with actual SHAP explanations and baseline comparison.
- SQL safety foundation: parser policy, read-only SQLite execution, row caps, timeouts and destructive-query rejection. This is not yet an LLM chat system.

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

Open `http://127.0.0.1:5173`. FastAPI documentation is at `http://127.0.0.1:8000/docs`. Vite proxies `/api` to the local backend. Data are historical; there is no live feed. Select 2024, open Monaco, compare results/grid/qualifying, then select a driver in the probability panel to see SHAP factors. Predictions for pre-2022 races are intentionally unavailable because those years overlap fit/selection.

## Tests and evidence

```sh
pytest -q
ruff check backend scripts tests
ruff format --check backend scripts tests
npm test --prefix frontend
npm run build --prefix frontend
```

At this checkpoint, 52 Python tests and 3 frontend tests pass. Some source/model integration tests skip when local artifacts are absent; a lightweight clone-only test run is not full data/ML verification. Two upstream TestClient deprecation warnings are recorded. Browser checks exercised standings → Monaco → qualifying → driver profile and the real prediction panel, including a 390px viewport.

## Architecture

CSV → validated relational storage → FastAPI analytics / chronological feature pipeline → frozen ML model → React views. The SQL safety module will sit between the future schema-grounded LLM generator and a separate read-only connection. Production ML logic lives in Python modules, not notebooks. Model artifacts must be locally generated or trusted: joblib files are not safe to load from untrusted uploads.

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

Still pending: configured LLM provider/model and live NL2SQL integration; 30–50-question benchmark; grounded chat routing/UI; executed evidence notebooks; CI; PostgreSQL runtime verification; containerization; Terraform; AWS deployment and cloud verification; final adversarial review. No chat benchmark, cloud deployment or completed-project claim is made.

AWS is the only production target: S3/CloudFront, ECR/ECS Fargate, RDS PostgreSQL, Secrets Manager and CloudWatch. No AWS resources have been created or queried during these milestones. The intended non-Naaz account must be verified using explicit `--profile default` identity/configuration checks before any AWS mutation. First infrastructure deployment requires a concrete Terraform plan and cost review. The Naaz account must never be used.
