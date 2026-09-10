# Agentic Retrieval and Query Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the F1 strategist robust to misspellings, paraphrases, ambiguity, and contextual follow-ups while adding one bounded SQL repair attempt and a user-visible audit trace.

**Architecture:** Add deterministic query augmentation, database-backed entity reranking, and relationship-aware schema ranking before the existing Bedrock router. Keep the frozen predictor and read-only SQL executor as the only answer sources. Enforce a request-local three-call budget, permit one sanitized repair call, and return an allowlisted trace to the React chat.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, SQLGlot, SQLite/PostgreSQL, React 18, Vite, Vitest, AWS Bedrock Mantle, CodeBuild, ECR, Lightsail Containers, Lightsail PostgreSQL, CloudWatch.

**Spec:** `docs/superpowers/specs/2026-09-10-agentic-retrieval-design.md`

## Global Constraints

- Run every implementation step in `.worktrees/agentic-retrieval` on `feat/agentic-retrieval`.
- Write a focused failing test and capture the expected failure before each behavior change.
- Use only the supplied 1950–2024 database and frozen 2022–2024 podium model as factual sources.
- Preserve deterministic unsupported checks, ambiguity clarification, SQLGlot validation, read-only execution, 200-row cap, one-second query timeout, rate limits, access-code handling, and production privilege verification.
- Permit at most three Bedrock calls per request and at most one SQL repair attempt.
- Never log or return credentials, access codes, connection strings, headers, prompts, raw exceptions, or provider response bodies.
- Keep the fixed 40-case benchmark immutable and write every live run to a new report file.
- Before each AWS mutation, verify account `148356747273`, profile `default`, and region `eu-north-1` through the guarded scripts.
- Do not remove or clean existing AWS resources without explicit user authorization.

---

### Task 1: Commit the approved design and executable plan

**Files:**

- Create: `docs/superpowers/specs/2026-09-10-agentic-retrieval-design.md`
- Create: `docs/superpowers/plans/2026-09-10-agentic-retrieval.md`

- [x] Review the spec against the approved bounded hybrid architecture: query augmentation, database-backed reranking, structured conversation, one repair attempt, three-call maximum, safe trace, frontend audit panel, separate evaluation, and AWS release.
- [x] Run `rg -n 'T[B]D|TO[D]O|implement[ ]later|similar[ ]to|appropriate[ ]error[ ]handling' docs/superpowers/specs/2026-09-10-agentic-retrieval-design.md docs/superpowers/plans/2026-09-10-agentic-retrieval.md` and require no matches.
- [x] Confirm every implementation task names exact files, tests, commands, and expected outcomes.
- [x] Commit with `git add docs/superpowers && git commit -m "docs: design bounded agentic retrieval pipeline"`.

### Task 2: Add deterministic query augmentation and entity reranking

**Files:**

- Create: `backend/ai/retrieval.py`
- Create: `tests/test_retrieval.py`
- Modify: `backend/ai/grounding.py`

- [x] Write failing tests for `augment_question` that require deduplicated original/corrected variants, contextual variants only for follow-up markers, selected-race context, a four-variant limit, and no mutation of the original question.
- [x] Write failing tests for `rank_entities` using a tiny database-backed catalog. Require exact full-name selection, conservative typo ranking, prior-turn boost, selected-race participant boost, shared-surname ambiguity, deterministic reasons, and stable ordering.
- [x] Run `.venv/bin/pytest tests/test_retrieval.py -q` and confirm collection or assertion failures because `backend.ai.retrieval` does not exist.
- [x] Implement `QueryVariant`, `RankedEntity`, and `EntityRanking` Pydantic models in `backend/ai/retrieval.py`.
- [x] Implement `augment_question(original, corrected, previous_question=None, race_id=None)` with a maximum of four unique variants and explicit `source` labels.
- [x] Refactor the catalog query in `grounding.py` into `entity_catalog(analytics)` so spelling resolution and ranking use the same database rows.
- [x] Implement `rank_entities(analytics, variants, prior_entities=(), race_id=None)` with normalized exact/reference/component similarity, full-name evidence, prior-turn and selected-race boosts, a confidence threshold, and ambiguity output.
- [x] Keep `resolve_entities` backward-compatible while returning the catalog-free existing response shape.
- [x] Run `.venv/bin/pytest tests/test_retrieval.py tests/test_entity_resolution.py -q` and require all tests to pass.
- [x] Commit with `git add backend/ai/retrieval.py backend/ai/grounding.py tests/test_retrieval.py docs/superpowers/plans/2026-09-10-agentic-retrieval.md && git commit -m "feat: add deterministic query and entity retrieval"`.

### Task 3: Add relationship-aware schema ranking

**Files:**

- Modify: `backend/ai/retrieval.py`
- Modify: `tests/test_retrieval.py`

- [x] Add failing tests for `rank_schema` that require `drivers` and `results` for driver wins, `races` for season filters, `pit_stops` plus relationship tables for pit-stop comparisons, router-hint filtering to known tables, shortest-path closure from `knowledge/relationships.json`, a compact selected set, and all-schema fallback for an unrankable question.
- [x] Run `.venv/bin/pytest tests/test_retrieval.py -q` and confirm the new assertions fail.
- [x] Implement deterministic token and phrase weights for F1 terms, entity kinds, and valid router hints.
- [x] Parse the repository relationship list into an undirected table graph and add the shortest lexicographically stable relationship path between required tables.
- [x] Return selected tables, per-table scores, and path reasons in the retrieval context; never add names outside `SCHEMA`.
- [x] Run `.venv/bin/pytest tests/test_retrieval.py -q` and require all tests to pass.
- [x] Commit with `git add backend/ai/retrieval.py tests/test_retrieval.py docs/superpowers/plans/2026-09-10-agentic-retrieval.md && git commit -m "feat: rank schema with relationship closure"`.

### Task 4: Introduce bounded conversation state, call budget, and audit trace

**Files:**

- Modify: `backend/ai/chat.py`
- Modify: `tests/test_chat.py`
- Create: `tests/test_agentic_chat.py`

- [x] Add failing validation tests for `ConversationEntity`, `ConversationTurn`, and `ChatRequest.conversation`: maximum three turns, known entity kinds, positive IDs, bounded names/questions, forbidden extra fields, and backward-compatible `previous_question`.
- [x] Add a scripted provider test that captures router input and requires variants, ranked entities, selected race, and compact structured turns while excluding prior SQL, results, and assistant prose.
- [x] Add failing tests that every route returns a trace with allowlisted fields, that early refusal and ambiguity report zero calls, and that serialized trace output excludes sentinel access codes, database URLs, prompts, raw errors, and provider bodies.
- [x] Add a failing test that a `ProviderCallBudget` refuses a fourth invocation.
- [x] Run `.venv/bin/pytest tests/test_chat.py tests/test_agentic_chat.py -q` and confirm the new tests fail for missing models, fields, or trace.
- [x] Implement the conversation models and retain the last three validated turns.
- [x] Implement a request-local `ProviderCallBudget(max_calls=3)` wrapper and route every `structured` call through it.
- [x] Build retrieval before routing, feed only allowlisted JSON context to Bedrock, combine valid router hints with deterministic schema ranking, and preserve prediction/explanation behavior.
- [x] Implement a trace builder with original/interpreted questions, variants, selected entities, selected tables, route, attempts, provider call count, aggregate provider timing, and total timing.
- [x] Add the trace to deterministic unsupported, ambiguity, provider-routed clarification, prediction, explanation, executed, empty, and rejected responses.
- [x] Run `.venv/bin/pytest tests/test_chat.py tests/test_agentic_chat.py tests/test_entity_resolution.py -q` and require all tests to pass.
- [x] Commit with `git add backend/ai/chat.py tests/test_chat.py tests/test_agentic_chat.py tests/test_entity_resolution.py docs/superpowers/plans/2026-09-10-agentic-retrieval.md && git commit -m "feat: add bounded conversation and audit trace"`.

### Task 5: Add one sanitized SQL repair attempt

**Files:**

- Modify: `backend/ai/chat.py`
- Modify: `tests/test_agentic_chat.py`

- [x] Add a failing scripted-provider test where generation returns `DELETE FROM races`, repair returns `SELECT COUNT(*) AS races FROM races`, and the response executes with three calls and two trace attempts.
- [x] Add failing tests for two rejected SQL candidates, exactly one repair invocation, no repair for an empty valid result, no repair for unsupported or clarify routes, and no path above three provider calls.
- [x] Add a failing redaction test where the query executor raises from an exception containing a sentinel database URL and secret; require the repair prompt and serialized response to contain only `execution_rejected` and fixed safe guidance.
- [x] Run `.venv/bin/pytest tests/test_agentic_chat.py -q` and confirm the repair assertions fail.
- [x] Reuse `SQLPlan` with a distinct repair system prompt that accepts only the failed candidate, sanitized category, selected schema, repository rules, and allowlisted retrieval context.
- [x] Refactor SQL execution into one helper and expose only a coarse failure category to the repair stage.
- [x] Invoke repair exactly once for `UnsafeQuery` or `QueryFailed`, validate and execute the replacement through the unchanged boundary, and finish with `query_rejected` after a second failure.
- [x] Record both attempts, final SQL, provider call count, and repair count in the response trace.
- [x] Run `.venv/bin/pytest tests/test_agentic_chat.py tests/test_chat.py tests/test_sql_safety.py -q` and require all tests to pass.
- [x] Commit with `git add backend/ai/chat.py tests/test_agentic_chat.py docs/superpowers/plans/2026-09-10-agentic-retrieval.md && git commit -m "feat: repair one rejected SQL plan safely"`.

### Task 6: Add privacy-safe structured application logging

**Files:**

- Modify: `backend/main.py`
- Modify: `tests/test_api.py`

- [ ] Add a failing API test with a captured logger that requires one completion event containing route, status, provider call count, repair count, table names, and elapsed milliseconds.
- [ ] Add sentinel values in the request, headers, and mocked failure and assert they do not occur in captured logs.
- [ ] Run `.venv/bin/pytest tests/test_api.py -q` and confirm the logging assertions fail.
- [ ] Log one `chat_complete` event after `chat_service.answer` using explicit scalar fields from the returned trace. Log only a safe exception type on unexpected application failures and allow existing exception handlers to produce their fixed responses.
- [ ] Run `.venv/bin/pytest tests/test_api.py tests/test_chat.py tests/test_agentic_chat.py -q` and require all tests to pass.
- [ ] Commit with `git add backend/main.py tests/test_api.py && git commit -m "feat: log safe chat execution evidence"`.

### Task 7: Send structured turns and render the audit trace in React

**Files:**

- Modify: `frontend/src/StrategistChat.jsx`
- Modify: `frontend/src/StrategistChat.test.jsx`
- Modify: `frontend/src/styles.css`

- [ ] Extend the existing frontend test with three prior responses and require the POST body to contain at most three compact turns with only `question`, `intent`, `entities`, and `race_id`; require it to exclude answer text, SQL, result rows, provider metadata, and access code.
- [ ] Add a failing render test for a response trace. Require a collapsed “How this answer was built” disclosure that shows interpreted question, route, entity names, table names, two SQL attempts, three model calls, and total elapsed time when opened.
- [ ] Add a failing test that legacy responses without a trace still render successfully.
- [ ] Run `npm test -- --run src/StrategistChat.test.jsx` from `frontend` and confirm the new payload and audit-panel assertions fail.
- [ ] Add a pure compact-turn mapper that derives safe entities from `response.trace.entities`, filters invalid turns, and slices the last three.
- [ ] Send both the compact `conversation` array and legacy `previous_question` during the compatibility period.
- [ ] Render the trace in a `<details>` panel with human-readable labels and no raw provider metadata or prompts.
- [ ] Add responsive styles consistent with the existing drawer and accessible summary/focus behavior.
- [ ] Run `npm test -- --run src/StrategistChat.test.jsx` and require all focused tests to pass.
- [ ] Run `npm test -- --run` and `npm run build`; require the complete frontend suite and production build to pass.
- [ ] Commit with `git add frontend/src/StrategistChat.jsx frontend/src/StrategistChat.test.jsx frontend/src/styles.css && git commit -m "feat: show how strategist answers are built"`.

### Task 8: Add the separate agentic evaluation suite and runner

**Files:**

- Create: `tests/nl2sql/agentic_questions.json`
- Create: `scripts/benchmark_agentic.py`
- Create: `tests/test_benchmark_agentic.py`
- Modify: `README.md`

- [ ] Author a fixed development suite with unique IDs and explicit expectations across misspellings, paraphrases, shared-name ambiguity, selected-race context, pronoun follow-ups, unsupported requests, and normal statistics. Include gold SQL only for statistics answers and structured previous turns only for follow-ups.
- [ ] Write failing runner tests for suite hashing, no-overwrite behavior, sequential conversation construction, exact row comparison through the existing `equivalent` helper, correction/entity/intent/clarification assertions, and summary fields for calls, repairs, and latency.
- [ ] Run `.venv/bin/pytest tests/test_benchmark_agentic.py -q` and confirm failures because the runner is absent.
- [ ] Implement `scripts/benchmark_agentic.py` with an injectable service for offline tests and a CLI requiring a new output path.
- [ ] Record suite hash, Git SHA, model, case response, correctness components, call count, repair count, latency, and summary aggregates. Preserve every partial report after each case.
- [ ] Document that the new suite and fixed 40-case suite are development evaluations and are reported separately.
- [ ] Run `.venv/bin/pytest tests/test_benchmark_agentic.py tests/test_retrieval.py tests/test_agentic_chat.py -q` and require all tests to pass.
- [ ] Commit with `git add tests/nl2sql/agentic_questions.json scripts/benchmark_agentic.py tests/test_benchmark_agentic.py README.md && git commit -m "test: add agentic retrieval evaluation suite"`.

### Task 9: Run complete local and PostgreSQL verification

**Files:**

- Modify if evidence requires: `docs/worklog.md`
- Create: `reports/agentic_local_verification.json`

- [ ] Run `.venv/bin/pytest -q` and record totals, skips, warnings, duration, and Git SHA.
- [ ] Run `npm test -- --run` and `npm run build` from `frontend` and record totals and build result.
- [ ] Run repository lint, formatting, security, and infrastructure validation commands defined by the current CI workflow; require the same gates that GitHub Actions uses.
- [ ] Run the opt-in PostgreSQL integration tests against the project database configuration without printing connection values; require read-only execution and privilege checks to pass.
- [ ] Exercise deterministic typo, ambiguity, follow-up, repair, refusal, and prediction paths locally with scripted providers and record assertions in `reports/agentic_local_verification.json`.
- [ ] If any verification fails, preserve the output, add a failing regression test, fix the cause, and rerun the affected check before repeating the full verification.
- [ ] Commit the verification report and worklog entry with `git add reports/agentic_local_verification.json docs/worklog.md && git commit -m "docs: record agentic pipeline verification"`.

### Task 10: Run live Bedrock evaluation without overwriting evidence

**Files:**

- Create: `reports/nl2sql_run_07.json`
- Create: `reports/agentic_run_01.json`
- Modify after genuine results: `docs/worklog.md`

- [ ] Confirm required Bedrock environment variables are present by checking variable names and nonempty status without printing values.
- [ ] Run `.venv/bin/python scripts/benchmark_nl2sql.py --output reports/nl2sql_run_07.json` exactly once and preserve all passes, failures, call metadata, and latency.
- [ ] Run `.venv/bin/python scripts/benchmark_agentic.py --output reports/agentic_run_01.json` exactly once and preserve all passes, failures, corrections, clarifications, selected entities, calls, repairs, and latency.
- [ ] Compare Run 07 with Run 06 and agentic Run 01 with its explicit expectations. Describe regressions, improvements, and suite limitations without calling the results unseen accuracy.
- [ ] Fix only demonstrated product defects through a new failing test. Write any repeat live execution to the next numbered report instead of editing an earlier report.
- [ ] Update the worklog with the exact report names, hashes, Git SHA, result counts, mean latency, provider-call distribution, repair count, and preserved failures.
- [ ] Commit with `git add reports/nl2sql_run_07.json reports/agentic_run_*.json docs/worklog.md && git commit -m "test: record agentic Bedrock evaluation"`.

### Task 11: Review, merge, and verify GitHub CI

**Files:**

- Modify as findings require: implementation and test files above

- [ ] Run `git diff $(git merge-base HEAD main)..HEAD --check` and inspect the complete feature diff for source-boundary violations, prompt leakage, unsafe SQL bypasses, excessive model calls, schema-selection errors, conversation overcollection, and presentation claims.
- [ ] Run the verification-before-completion suite again after review changes: complete backend tests, frontend tests/build, infrastructure checks, and focused privacy tests.
- [ ] Merge `feat/agentic-retrieval` into `main` without rewriting history after the branch is green.
- [ ] Push `main` to `origin` and record the exact merge SHA.
- [ ] Wait for the GitHub Actions workflow on that SHA and require every Python, frontend, and infrastructure job to pass.
- [ ] If CI fails, add a local reproducer, fix the cause on the feature branch or a focused follow-up branch, merge, push, and wait for the replacement SHA.

### Task 12: Build and deploy the exact commit to AWS Lightsail

**Files:**

- Modify if needed: `scripts/release_lightsail.py`
- Create: `reports/aws_agentic_release.json`

- [ ] Verify `aws sts get-caller-identity --profile default` returns account `148356747273` and `aws configure list --profile default` resolves `eu-north-1`; do not print secret values.
- [ ] Start CodeBuild for the exact merged Git SHA and wait for `SUCCEEDED`. Record the build ID, source SHA, image tag, and timestamps.
- [ ] Invoke the guarded Lightsail release script for `f1-strategist-demo` using that immutable image tag. Wait for the deployment to reach `ACTIVE` and health checks to pass.
- [ ] Confirm the active deployment image resolves to the intended SHA and the managed public endpoint remains HTTPS.
- [ ] Write `reports/aws_agentic_release.json` with account, region, Git SHA, build ID/result, deployment version/state, image tag, and nonsecret timings.

### Task 13: Verify the public API, frontend, logs, and presentation evidence

**Files:**

- Create: `reports/aws_agentic_cloud_verification.json`
- Modify: `docs/worklog.md`
- Modify: `docs/architecture.md`
- Modify: `docs/ai_assistance.md`
- Modify: `docs/adversarial_review.md`
- Create: `docs/presentations/F1_Race_Strategist_Final_Review.pptx`
- Create: `docs/final_demo_guide.md`

- [ ] Verify the public `/`, a supported race route, `/api/health`, comparison, profiles, standings, predictions, and frontend assets return successful responses.
- [ ] Through the public chat API, verify one normal statistic, one misspelled entity with correction, one structured follow-up, one ambiguous surname clarification without SQL, one weather refusal without SQL, and one race prediction/explanation. Space calls within the deployed rate limits.
- [ ] Open the public frontend, submit a misspelled question, and verify the answer, correction, generated SQL, and “How this answer was built” panel render with the expected route, entities, tables, attempts, calls, and timing.
- [ ] Retrieve a bounded CloudWatch log snapshot and assert chat completion records exist while sentinel secrets, request text, SQL, connection strings, and credentials do not.
- [ ] Write `reports/aws_agentic_cloud_verification.json` with URL, deployment SHA, each assertion, response status, safe trace summary, asset check, and log event count.
- [ ] Update architecture, AI-assistance disclosure, adversarial review, and worklog with the verified implementation, limitations, test totals, evaluation results, CI run, CodeBuild ID, deployment state, and cloud checks.
- [ ] Create a final editable presentation using the existing interim deck’s evidence style. Include verified agentic retrieval, query repair, UI trace, live benchmark comparison, GitHub CI, AWS architecture, and public deployment screenshots. Keep the interim deck unchanged as a historical snapshot.
- [ ] Validate the PowerPoint package, render every slide, inspect for overlap or clipping, verify native tables/charts and speaker notes, and record the SHA-256. State if native PowerPoint opening was not performed.
- [ ] Run the complete local verification one final time after documentation-only changes where applicable.
- [ ] Commit all release evidence and presentation artifacts, push `main`, wait for the final documentation CI run, and confirm the application deployment still points to the verified code SHA.

### Task 14: Completion report

- [ ] Confirm `git status --short` is clean on `main` and `git rev-parse HEAD` is pushed to `origin/main`.
- [ ] Confirm all numbered evaluation and AWS evidence files are immutable and contain no secrets.
- [ ] Confirm the public URL is healthy and the active Lightsail deployment is the verified application image.
- [ ] Report what changed, full test results, live benchmark results with limitations, GitHub Actions and CodeBuild evidence, public cloud verification, presentation path, demo guide path, and any remaining operational limitations or AWS costs.
