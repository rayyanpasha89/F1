# Engineering worklog

## 2026-09-08 — Source inspection and audit

Read the brief, package README, master source document, all scope slides and speaker notes, and every CSV. Confirmed there was no Git repository. Implemented a deterministic audit with source hashes, missingness, inferred types, key checks, entity references, per-year coverage and suspicious-value reporting. Executed it on all 701,433 rows. Historical duplicate driver/race result records are retained as a documented grain limitation. Raw CSVs and supplied documents remain untouched and excluded from redistribution until licensing provenance is established.

Validation: audit executed successfully; type/null parsing, malformed-row rejection, and report integrity tests executed. The audit is an initial foundation, not a completed product.

## 2026-09-08 — Relational ingestion

Added committed source-to-SQL column mappings, SQLAlchemy metadata, foreign keys, join indexes and transactional ingestion. Loaded all 14 tables into local SQLite; independently compared every table count to the audit and ran `PRAGMA foreign_key_check` with no violations. Seven tests passed, including changed-source and nonempty-target rejection. PostgreSQL DDL compilation was checked; live PostgreSQL has not yet been exercised. Recorded ADR 001. No AWS operations performed.

## 2026-09-08 — Analytics API

Implemented season/race navigation, final recorded standings, qualifying, separate grid payloads, classified results, pit summaries and driver/constructor profiles. Queries use bound values and fixed route enums. Profiles distinguish race points from championship totals and distinct podium races from individual podium finishes. Tested the 2024 navigation path, both standings types, all race tables, profiles, 1950 empty coverage, invalid identifiers and safe database errors. Fourteen tests passed. Two upstream TestClient deprecation warnings remain; they do not represent failures. No ML/chat is exposed yet.

## 2026-09-08 — Historical frontend

Implemented real API-backed React season, race, driver and constructor views with URL navigation, loading/error/empty states and responsive timing tables. Production build passed and three API-client tests passed. Browser verification loaded the 2024 standings, followed the Monaco weekend, checked 20 result rows, switched to qualifying and opened Charles Leclerc's profile. Inspected desktop and 390px screenshots; mobile document width remained 390px and tables scroll internally. No Vite overlay or browser errors were observed. Initial browser attempt failed because development servers had stopped between user turns; restarting them resolved it. No model or chat claims were added to this milestone.

## 2026-09-08 — Measured baseline and GitHub connection

Executed grid-only logistic regression on 2010–2018 with 2019–2021 validation. Saved actual metrics (log loss 0.246224, top-three hit rate 0.716667), the local model and experiment registry. Seventeen tests passed, including outcome mutation invariance, temporal separation, deterministic training and metric semantics. Final test not evaluated. User announced a GitHub F1 repository; found and verified empty `rayyanpasha89/F1`, connected origin and pushed the four earlier commits without rewriting history.

## 2026-09-08 — Historical features and model comparison

Added date-batched history generation and driver/team/circuit/career features. Twenty tests passed, including future and same-date outcome mutation, teammate leakage, shuffled input order, and debutant defaults. Executed eight additional experiments using only 2019–2021 validation for selection. Gradient boosting EXP-007 obtained validation log loss 0.209820 versus baseline 0.246224. Wrote actual experiment records and froze this provisional selection before final-test access. Identified that circuit contribution still needs a separate ablation; no isolated H4 success is claimed yet.

## 2026-09-08 — Calibration selection frozen

Executed training-only out-of-fold sigmoid calibration and clean H3/H4 ablations. Calibration slightly improved validation log loss (0.209557). Recent podium rate alone did not beat career podium rate; circuit history modestly improved the controlled team-feature comparison. Documented both results without claiming universal hypothesis success. Selection is now frozen before opening the final test. Added SHAP dependency for genuine tree explanations; explanations have not yet been claimed as verified.

## 2026-09-08 — Final evaluation and explainable inference

Executed reserved 2022–2024 evaluation after calibration-selection commit. Reported probability-score gains and the slight top-three hit-rate decline honestly. Verified SHAP reconstruction across held-out rows and API inference. Added race prediction UI with baseline comparison, all model factors and explicit reference units. Twenty-two Python tests, three frontend tests and production build passed. Browser loaded 20 Monaco predictions and a real Leclerc 76.4% explanation; inspected the full-page screenshot and observed no browser errors. Earlier training/selection races are refused by the prediction API. No AWS resources created.

## 2026-09-08 — SQL safety foundation and configuration stop

Implemented single-statement AST validation, schema/function restrictions, explicit joins, aggregated lap/pit policy, SQLite read-only URI/authorizer, capped results and timed/opcode-bounded execution. Added PostgreSQL read-only execution code, not yet live-tested. Fixed a syntax error caught in the new parametrized tests before proceeding. All 52 Python tests passed. Documented the implemented boundary and remaining semantic/LLM work in ADR 004.

Checked only presence (not values) of OPENAI_API_KEY, ANTHROPIC_API_KEY and BEDROCK_MODEL_ID in the process environment; none is configured. No provider integration is yet configured. Pausing LLM work under the user's explicit missing-credential stop condition, and updating README to accurately reflect implemented features and outstanding work. No AWS profiles/resources inspected or mutated. This is an intermediate checkpoint, not definition-of-done completion.

## 2026-09-09 — Bedrock transport and live SQL smoke test

User confirmed default AWS account 148356747273, IAM user ray-demo2, as the intended non-Naaz account and confirmed the supplied Bedrock key belongs to it. Explicit STS/default configuration checks preceded billable inference. The endpoint is Bedrock Mantle in eu-north-1; CLI default region is us-east-1, so deployment region must be explicit. Saved credentials remain in ignored .env, never Git. Bedrock connection test returned CONNECTION_OK with HTTP 200 from openai.gpt-oss-120b.

Added dotenv configuration with an AWS-only endpoint check, bounded OpenAI-compatible HTTP transport, separate structured intent and SQL stages, safe execution and deterministic result rendering. Prediction routing uses the real model, not LLM-generated probabilities. Fifty-eight tests passed; test doubles exist only in tests and are not benchmark evidence. Auth transport failures omit raw response bodies. Authored 40 fixed benchmark cases, with independent gold SQL for 30 analytics questions and 10 refusal cases, before running the benchmark.

## 2026-09-09 — First live benchmark and validator correction

Executed all 40 fixed questions against Bedrock. Run 01 recorded 21/40 answer checks passing (11/30 analytics, 10/10 refusals). It exposed a policy bug: SQLGlot represents AND/OR as Func subclasses, and our arbitrary-function allowlist incorrectly rejected them. This also prevented several reference queries from being evaluated, so Run 01 is diagnostic evidence, not a clean model-accuracy estimate. Preserved the complete report including failures and timings. Added explicit structural boolean-node handling and regression coverage for compound filters and every fixed reference query. All 32 SQL safety tests passed after the correction. No benchmark questions or gold answers were fed to the model.

## 2026-09-09 — Second live benchmark and semantic grounding

Run 02: all 30 analytics SQL queries executed and all 10 refusals passed; 24/30 analytics matched the strict reference result shape, for 34/40 total. The six failures were one incorrect exact entity-name match (Monaco), two singular-superlative queries returning whole rankings, and three responses with extra label/ID columns. Some underlying values were right despite failing the fixed shape contract. Preserved both reports. Added database-derived entity-label retrieval and generic instructions for singular rankings, requested columns, complete GROUP BY columns and chronological ordering by date/round rather than race_id. No case-specific answer mappings were added.

### Correction to the grounding milestone

The test command preceding commit 3760daa failed because the synthetic two-row races fixture lacked the newly required entity tables. The shell sequence continued to commit despite that failure; this was an execution-workflow error, not a passing-test milestone. No history was rewritten. Added empty synthetic entity tables to the fixture and reran the full suite: all 62 Python tests passed. Subsequent commits are issued in separate tool calls after inspecting test results to prevent fall-through. The live application database already had these tables.

## 2026-09-09 — Third benchmark and verified sprint semantics

Run 03 passed 39/40 checks (29/30 analytics and 10/10 refusals); all 30 analytics queries executed. The remaining failure used constructor_results.points for explicitly sprint-excluded points. Investigated the source: all 180 constructor/race rows with sprint records in 2021–2024 equal main-race plus sprint points. Added this verified semantic distinction to grounding/routing and a regression test. Preserved Run 03 without rewriting its failed answer. This fixed-suite iteration is development evaluation, not an unseen generalization estimate.

## 2026-09-09 — Fourth benchmark and aggregated CTE support

Run 04 retained 39/40 checks, with the sprint-excluded points answer now correct. One otherwise valid deep pit-stop query was rejected because it selected detail in a CTE before aggregating in the outer SELECT. Updated the policy to allow this bounded pattern while continuing to reject raw final outputs and scalar-subquery attempts to disguise raw dumps. Added regression tests; all 33 SQL safety tests passed. Run 04 remains preserved with its rejection.

## 2026-09-09 — Chat interface, bounded access and fifth benchmark

Run 05 passed all 40 fixed cases: 30 executed analytics answers and 10 safe refusals, mean latency 3.707 seconds across all cases. Reports 01–05 remain preserved. The comparator checks positional column values and row multisets, not ranking order; structural join checks are proxies rather than semantic proof. This repeatedly used development suite does not estimate unseen accuracy. Integrated chat with visible SQL, real model factors, retry/clear, race context and an optional in-memory access code. Added two concurrent-call slots, six requests/minute per client and 200/day per process. These limits reset on restart and are not a durable billing budget. Backend suite: 67 passed, three opt-in PostgreSQL tests skipped, five upstream warnings. Frontend: five tests passed; lint, formatting and production build passed; npm audit found zero vulnerabilities.

## 2026-09-09 — Reproducible review notebooks and PostgreSQL checks

Executed all four review notebooks with nbclient using the project environment: source audit/coverage, measured baseline, temporal features/experiments, final evaluation/calibration. They call production modules and reproduce recorded values; they are retrospective reproducibility artifacts, not a fabricated pre-experiment diary. Loaded all 701,433 rows into isolated local PostgreSQL 16.15 and verified all table counts, analytics routes, SQLite/PostgreSQL feature equivalence and database-level denial of DELETE/CREATE for a SELECT-only role (three integration tests passed). Added synthetic all-table ingestion and late-FK-error rollback coverage that does not require private CSVs. Configured GitHub validation for Python and frontend; remote CI execution is pending.

## 2026-09-09 — CI passed and initial AWS plan

GitHub run 34341916849 passed both Python and frontend jobs. Terraform 1.13.5 with locked AWS provider 6.63.0 initialized and validated. Draft HCL formatting errors were caught and corrected before planning. Actual initial plan: 49 additions, zero changes/deletions. Shared full plan and rough $55–75/month continuous dev estimate before first deployment, identifying persistent RDS/ALB/Fargate/storage charges. Confirmed default-profile account 148356747273 again. Container runtime is prepared but not yet executed: Docker is unavailable locally, so the documented CodeBuild gate will verify the Linux image. Backend regression suite remains 67 passed, three opt-in skips. Terraform has no secret values; runtime secret population will occur outside state. No AWS resources have been created at this checkpoint.

## 2026-09-09 — Container and adversarial SQL verification

CodeBuild 5eda1bf9-3b44-4233-9f4b-ba0afba33f6e succeeded for committed image 2014f6e: Linux dependency install, model deserialization and immutable ECR push all passed. Browser recheck initially used an old backend process; restarted it and confirmed the current UI returns Verstappen/63, exposes executed SQL, refuses wet-weather claims and routes Monaco predictions to Leclerc 76.4% with real SHAP factors. Inspected mobile chat screenshot at 390px. History scan found no configured Bedrock API key in 301 Git objects; short non-secret project-label matches were distinguished from credentials.

Adversarial inspection found scalar-subquery and window aggregate expressions could disguise raw detail selection. Tightened aggregation detection to require row aggregation in the correct SELECT scope; three new regression cases pass. Full suite: 72 passed, three opt-in skips. Replayed all 30 executed Run 05 SQL statements locally under the tightened policy and obtained unchanged results. This replay is not a new live LLM benchmark. Infrastructure creation remains in progress; application desired count is zero.

## 2026-09-09 — AWS restrictions and authorized Lightsail alternative

Initial apply partially created 44 Terraform-managed resources. CloudFront distribution failed with account-verification AccessDenied (request 49873923-4180-4b38-9eb0-d3e38b6cbd2d). RDS failed with FreeTierRestrictionError for seven-day backups. No RDS database or public app was created; ECS desired count remains zero. Existing ALB incurs persistent charges. No cleanup/deletion performed. Corrected image 0be5be2 passed CodeBuild 7a11237d-9c94-452a-b8bf-22bd6e9c5726. User authorized Lightsail or another AWS alternative and account verification, then signed into Opera; verified browser account matches CLI 148356747273.

Validated separate Lightsail Terraform plan: three additions, no changes/deletions. Small container service $15/month plus encrypted micro PostgreSQL bundle $15/month, verified through regional Lightsail APIs. Uses managed HTTPS endpoint and private persistent PostgreSQL. A Terraform-managed CloudFormation database resource lets Lightsail generate its password outside state, unlike the native Terraform Lightsail database resource's required password attribute. Added same-origin React hosting with API/path traversal/asset boundary tests; 73 Python tests pass. Presentation and demonstration guide requested and in progress.

## 2026-09-09 — Interim presentation delivered

Created a 15-slide editable PowerPoint covering verified dataset coverage, application architecture, real dashboard and prediction screenshots, temporal ML evaluation, all five live NL2SQL benchmark runs, actual GitHub commit history and CI evidence, and the current AWS deployment limitations. Added speaker notes with sources and a demonstration guide containing exact pages, commands, questions, expected results and speaking cues. All 15 rendered slides were visually reviewed; package integrity, layout geometry, native tables, chart workbook and artifact import checks passed. Native PowerPoint opening was not verified. Cloud deployment remains in progress and is explicitly marked accordingly. Presentation SHA-256: 2e1700f802c51ac29a6a186de10c3a610015b9e72e9b9785b488dfd45a873737.

## 2026-09-09 — Product completion gaps and first live AWS app

Re-read the original request after the user emphasized the complete product, spelling tolerance and frontend verification. Added a dedicated race driver comparison using strictly earlier five-appearance form and circuit history, explicit post-race outcome disclosure, profile recent-form summaries, and native HTML bar views of suitable executed chat results. Added conservative database-derived spelling repair with visible corrections and clarification for ambiguous historical names. Fixed named-driver explanations to use that driver's actual prediction and SHAP contributions. The live targeted suite passed six cases, including misspellings, ambiguous names and unsupported weather. Browser verified Lewis Hamliton -> Hamilton -> 105 executed wins and selectable comparison drivers. No model retraining or fabricated metrics.

Lightsail provisioned all three planned resources. A container connected to PostgreSQL while the database remained private. Strict ingestion validated 701,433 rows across all 14 tables; runtime reader has SELECT privileges and a read-only default. Requested rotation of the temporary master password, then deployed image 13ed44e. Eight public smoke routes passed, including all 20 model probabilities. The newer product code is not yet deployed at this milestone.

Added guarded Lightsail releases and explicit CloudWatch log export, plus production startup rejection of writable credentials. The new live PostgreSQL test caught an unqualified catalog-name lookup; switched to catalog OIDs and all four PostgreSQL integration checks passed. Current local Python suite passed 82 tests (opt-in PostgreSQL checks run separately); frontend seven tests, lint, formatting and build passed. The interim presentation remains a snapshot of the earlier checkpoint.

## 2026-09-10 — Verified cloud release and final self-review checkpoint

AWS CodeBuild `ffeb7d46-c73c-4b13-9be7-971bc7a49581` succeeded for commit `8d0e8d1`, and the guarded release deployed that immutable image to Lightsail. The service reached RUNNING/ACTIVE. Public HTTPS checks returned 200 for the frontend, race deep link, health, driver comparison, profile recent form and Monaco predictions. The deployed JavaScript contains the comparison and spelling-correction UI. Cloud chat corrected `Lewis Hamliton`, executed read-only SQL and returned 105 wins; ambiguous `Schumacher` requested clarification among three stored drivers; wet-weather analysis refused without SQL. The database remains private.

Re-ran the complete fixed 40-case live Bedrock suite after the entity-resolution changes. Run 06 passed all 30 analytics cases and 10 refusals with 3.988-second mean latency. This remains a reused development suite, not unseen accuracy. Exported 80 bounded Lightsail log events into CloudWatch stream `lightsail/20260909T162739453171Z`; continuous runtime logs remain in Lightsail. GitHub Actions run `34376649850` passed Python, frontend and both Terraform configurations. Updated the adversarial review and README to match deployed behavior and preserved machine-readable cloud evidence.

## 2026-09-10 — Agentic retrieval local verification

Implemented the approved bounded orchestration design on an isolated feature worktree. The chat now preserves the original question while building explicit corrected and contextual variants, ranks database-backed entities, selects a compact relationship-closed schema, accepts up to three structured prior turns, and exposes an allowlisted execution trace. Statistics still pass through the unchanged SQLGlot and read-only database boundary. A rejected generated query receives exactly one repair attempt with a coarse error category; no path can exceed three Bedrock calls. Added privacy-safe completion logs and a React “How this answer was built” panel. Access codes, prior answers, SQL result rows, raw provider metadata, connection strings, prompts and exception text are excluded from conversation context and the trace.

Added a separate 22-case agentic development suite and append-only runner covering misspellings, paraphrases, shared-surname clarification, contextual follow-ups, unsupported requests and a selected-race explanation. Before paid inference, executed all 14 gold SQL statements and audited deterministic correction, entity and schema expectations. That audit caught and fixed false positives where generic words could resemble historic driver references or three-letter codes and where a shared forename could select extra drivers. The suite is explicitly a development evaluation, not an unseen accuracy estimate.

Fresh local gates passed on source commit `9d7b028`: 111 regular Python tests, nine frontend tests, Ruff, ESLint, Prettier and the Vite production build. Downloaded the workflow-pinned Terraform 1.13.5 binary, verified its archive checksum against HashiCorp's checksum list, and validated both Terraform roots with locked AWS provider 6.63.0. Created the separate local database `f1_agentic_verify_20260910`, loaded the audited 701,433 rows, and ran all four PostgreSQL integration tests with a dedicated SELECT-only role. They verified row counts/routes, SQLite/PostgreSQL feature parity, database-level mutation denial and production startup privilege checks. No Naaz database was accessed or changed. Detailed nonsecret evidence is in `reports/agentic_local_verification.json`.

## 2026-09-10 — Live bounded-retrieval evaluation

Preserved three new runs of the unchanged fixed suite while using it to test the relationship-aware schema selector. Run 07 passed 39/40 at 3.628-second mean latency. Q27 used driver standings and constructor summaries to answer which constructor Fernando Alonso raced for, returning every constructor at his races. Added a failing regression and made “race for” association resolve through `results`. Run 08 passed Q27 and 39/40 overall at 3.829 seconds, exposing Q28: “classification order” incorrectly used championship standings. Added a second failing regression, mapped race classification to `results`, and preferred `results` as the neutral driver/race relationship bridge when no explicit standing concept exists. Explicit championship-standing questions still select their standing tables.

Run 09 then passed all 40 cases: 30/30 executed analytics answers and 10/10 safe refusals, with 3.651-second mean latency. Its provider-call distribution was eight zero-call deterministic responses, two one-call routed refusals and thirty two-call statistics answers; no repair was needed. Compared with Run 06's 3.988-second mean, Run 09 was about 8.5% faster in this execution. Network and provider variation prevent attributing the entire change to shorter schema prompts.

The separate agentic Run 01 passed all 22 cases at 3.013-second mean latency: 14/14 statistics answers, seven safe clarification/refusal cases and one selected-race explanation. It made 29 Bedrock calls with distribution `{0: 7, 1: 1, 2: 14}` and no live repair. The one-repair and terminal-rejection paths remain covered by deterministic tests because no generated query in this run failed the SQL boundary. Both the fixed and agentic suites were used during development and are not unseen generalization estimates. Reports 07–09 and agentic Run 01 remain append-only evidence.

## 2026-09-10 — Agentic AWS release and browser quality pass

Merged the agentic work into `main`, preserved the feature history and pushed it to GitHub. The merge and each focused correction passed Python, frontend and infrastructure CI before release. Final application commit `4b3946451986f09fdd11d880a2de757366947989` passed GitHub Actions run `34456776706`. Local verification passed 113 Python tests with four opt-in checks skipped in the default run, all four isolated PostgreSQL checks when supplied both admin and SELECT-only reader URLs, nine frontend tests, Ruff, ESLint, Prettier, the Vite production build and both Terraform roots.

Guarded AWS operations repeatedly verified account `148356747273`, profile `default` and region `eu-north-1`. CodeBuild `cce52796-d309-4d3c-a536-4a97e796c0a1` built the exact final SHA, installed locked runtime dependencies, deserialized the trusted model artifacts and pushed its immutable ECR image. Lightsail deployment 9 reached `RUNNING`/`ACTIVE` on that full image tag. Eight public routes passed, including the frontend, deep link, health, standings, comparison, profile and all 20 Monaco probabilities. Five public chat paths passed: misspelled Lewis Hamilton with 105 wins, structured 2020 follow-up with 11 wins, zero-call Schumacher clarification, zero-call wet-weather refusal and selected-race explanation. No live repair was needed; observed requests used at most two provider calls.

The first cloud log probe exposed that safe `chat_complete` records were suppressed by Uvicorn's logger topology. A module-level log setting still propagated to an unhandled root logger, so the application now emits through the configured `uvicorn.error` hierarchy. The exact Uvicorn configuration was reproduced locally before rebuilding. Five safe completion lines were then retrieved from Lightsail and exported to CloudWatch stream `lightsail/agentic-20260910T085254152735Z`; the access code, question text, SQL, provider settings, credentials and connection strings were absent from the checked records.

Real browser QA opened the public frontend in Opera and used a temporary isolated Playwright environment for durable screenshots. The first expanded trace revealed an unrelated `Jackie Lewis` entity next to the correct Lewis Hamilton answer. A failing catalog regression reproduced both surname-component and stored-reference paths. The reranker now suppresses overlapping lower-confidence component/reference/edit matches when an explicit full driver name is present, while retaining separately explicit full names and codes. Final API and browser assertions show only Lewis Hamilton in the trace. Machine-readable release and cloud checks are in `reports/aws_agentic_release.json` and `reports/aws_agentic_cloud_verification.json`; presentation screenshots are under `docs/presentations/assets/`.

## 2026-09-10 — Final presentation and demonstration package

Created the final 15-slide editable PowerPoint while preserving the interim deck as its original historical snapshot. The final deck uses actual public application, agent-trace, Monaco prediction and GitHub CI screenshots; four native tables; an editable benchmark chart; and speaker notes on every slide. Package integrity, layout geometry, Arial font policy, first-party Artifact Tool import, native table presence and embedded chart workbook validation passed. All 15 slides were rendered and visually reviewed, including individual full-size inspection of the dashboard, trace and prediction evidence. Native PowerPoint opening was not performed. Final presentation SHA-256: `d7a042fce3ea5999ef7b8d61b0d92b3e931269b6974633b05b85f816b6b1df84`.

Added `docs/final_demo_guide.md` with the live URL, verified release identifiers, an eight-step walkthrough, expected answers and traces, evidence locations, speaking cues, reviewer questions and explicit limitations. The access code remains outside Git and is referenced only by its protected workspace location.
