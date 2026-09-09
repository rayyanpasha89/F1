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
