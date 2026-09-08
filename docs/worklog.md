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
