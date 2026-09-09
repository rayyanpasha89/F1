# Adversarial repository review

Review date: 2026-09-09. Conducted by the implementing Codex agent, not an independent reviewer. Cloud verification remains pending; this is not a completed-project certificate.

| Area | Evidence inspected | Finding / disposition |
|---|---|---|
| Target/future leakage | `backend/ml/features.py`, mutation tests, split masks | Outcomes are scoring columns only; feature allowlists select inputs. Same-date rows are emitted before any history update. Train 2010–2018, selection 2019–2021, final 2022–2024; parameters frozen before final evaluation. |
| Rolling semantics | Driver/team/circuit histories and tests | Previous five appearances/races, fixed debut priors. Team aggregates are race-level means across drivers. Career warmup starts 1990, not all history. |
| Point-in-time provenance | CSV audit and inference entry construction | Results snapshot supplies historical grids and participants; original pre-race publication timestamps and correction history are unavailable. This is retrospective pre-race-feature evaluation, not a verified live forecast archive. |
| Predictions and explanations | Saved artifact pipeline, final report, SHAP reconstruction | Real sklearn inference. Calibrated SHAP base and factors reconstruct probabilities within 1e-7. Factors are associative log-odds, not causal explanations. |
| Metrics and hypotheses | EXPERIMENTS, saved reports, executed notebooks | No fabricated successes: probability scores improve, top-three hit rate slightly declines; H3 recent form alone does not beat career. Four notebooks executed from production modules. |
| Frontend data | API client, browser network paths and visible rows | Real API payloads throughout. Fixtures are confined to tests. Browser verified standings/race/qualifying/profiles/predictions and chat. |
| SQL mutation boundary | AST validator, SQLite authorizer, live PostgreSQL role test | Single read-only statement, known tables/functions, capped rows and timed execution. SELECT-only PostgreSQL role independently denies DELETE/CREATE. |
| Raw detail policy | Aggregate scope inspection | Found scalar/window aggregate disguises; corrected and covered by three regression cases. Replayed all 30 saved Run 05 SQL queries with unchanged results after the fix. |
| Grounding/hallucination | Separate router/generator, actual DB entity retrieval, live suite | Weather/tyres/fuel/telemetry refused; factual responses rendered from rows/model. Model-supplied assumptions remain unverified and labeled. No manual statistical answer mapping. |
| Benchmark strength | All five reports, comparison implementation | Run 05 40/40 on an iteratively used fixed suite. Row ordering unscored; table/key presence checks are proxies. Does not establish unseen generalization. Earlier failures preserved. |
| Secrets | Git tracked paths and complete 301-object scan | Actual configured Bedrock API key absent. `.env`, state and models ignored. Short project-label text caused benign matches, not API-key leakage. Runtime secrets never inserted into Terraform state. |
| Tests/CI | Local suite and GitHub run 34341916849 | 72 Python tests after review; opt-in PostgreSQL tests separately pass. Five frontend tests. CI without private CSV/model artifacts exercises a smaller scope; not equivalent to full data/model verification. |
| Deployment contracts | ECS secret names versus chat config | Corrected mismatched read-only URL variable before service startup. Added contract coverage. |
| Container | CodeBuild 5eda1bf9-3b44-4233-9f4b-ba0afba33f6e | First Linux image builds and deserializes trusted models. Corrected SQL version needs its own image build before deployment. |
| AWS boundaries | Provider allowlist, dedicated names/tags/security groups | Confirmed account/default profile only. Private RDS and internal ALB; viewer HTTPS and DB verified TLS; private ALB/task hop HTTP. No unrelated resource changes planned. |
| Operational limitations | Terraform, chat limiter, docs | Single-AZ DB/single task; local Terraform state; no durable chat quota or alarm notification subscriber. Persistent AWS charges continue without traffic. These are explicit dev limitations. |
| Reproducibility | README, source checksums, dependency locks, Git history | Clone requires exact source package; no redistribution license was supplied. Trusted artifacts reproduced by scripts; no backdating/force-push. Worklog records one earlier test-command fall-through and corrective commit honestly. |

Remaining gate: finish provisioning, deploy corrected image, validate database role/TLS and full public HTTPS flow, inspect CloudWatch and update this review with actual cloud evidence. No definition-of-done completion is claimed before that gate.
