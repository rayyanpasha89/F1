# Agentic Retrieval and Query Repair Design

**Date:** 2026-09-10  
**Status:** Approved for implementation  
**Product:** F1 Race Strategist

## Purpose

The strategist must answer historical F1 questions reliably when a user misspells a name, paraphrases a statistic, or asks a follow-up such as “compare him with Leclerc.” It must also remain auditable: every answer must come from the supplied 1950–2024 database or the frozen 2022–2024 podium model, and every generated query must pass the existing read-only SQL boundary.

The implementation adds a bounded orchestration layer around the current router, SQL generator, database executor, and predictor. It does not add an unrestricted tool loop, a vector database, live web data, or a second factual source.

## Goals

- Preserve the original question while producing explicit spelling corrections and bounded query variants.
- Retrieve database-backed driver, constructor, circuit, and race candidates and rank them using the current question, recent turns, and selected race.
- Rank schema tables deterministically and include the minimum relationship path needed to join selected concepts.
- Support short contextual follow-ups through structured, size-limited conversation turns.
- Make one controlled SQL repair attempt after a validation or read-only execution failure.
- Enforce a hard maximum of three Bedrock calls: route, generate, and optional repair.
- Return a safe audit trace to the frontend without exposing prompts, credentials, raw exceptions, or provider response bodies.
- Evaluate typo handling, paraphrases, ambiguity, follow-ups, repair behavior, provider-call count, accuracy, and latency separately from the fixed 40-case benchmark.
- Preserve current deterministic refusals, prediction boundaries, SQL validation, timeouts, row limits, rate limits, and production read-only role checks.

## Non-goals

- Answering weather, tyre, fuel, telemetry, betting, live, or post-2024 questions.
- Training or replacing the frozen podium model.
- Searching the internet or adding externally maintained F1 facts.
- Allowing the model to choose arbitrary tools or repeat until it finds an answer.
- Hiding ambiguity by selecting a low-confidence entity.
- Claiming unseen evaluation accuracy from a suite used during development.

## System boundary

The factual sources remain:

1. The normalized 14-table F1 database created from the supplied CSV snapshot.
2. The frozen calibrated podium model and its stored SHAP explanations for supported race weekends.
3. Repository-owned schema, relationship, SQL-rule, and terminology documents that describe those sources.

Bedrock interprets questions and writes a candidate SELECT statement. It does not supply answer facts. The application accepts an answer only after deterministic routing rules, entity resolution, schema selection, SQL validation, and read-only execution have succeeded.

## Request contract

`ChatRequest` keeps its existing fields and adds a bounded `conversation` list.

```json
{
  "question": "compare him with Leclrec",
  "race_id": 1128,
  "previous_question": "why is Hamilton likely to finish on the podium?",
  "conversation": [
    {
      "question": "why is Hamilton likely to finish on the podium?",
      "intent": "explanation",
      "entities": [
        {"kind": "drivers", "id": 1, "name": "Lewis Hamilton"}
      ],
      "race_id": 1128
    }
  ]
}
```

The API accepts at most three conversation turns. Each turn contains only the prior question, resolved intent, selected entity references, and race ID. SQL, result rows, provider metadata, access codes, and free-form assistant answers are excluded. `previous_question` remains supported during migration and is used only when structured conversation is absent.

## Retrieval pipeline

### 1. Normalize and augment

The application stores the original question unchanged. Existing database-backed spelling repair produces the interpreted question and visible corrections. A new deterministic augmenter creates at most four unique variants:

- original question;
- spelling-corrected question;
- corrected question with the previous question as context when a follow-up marker is present;
- corrected question with selected race context when `race_id` is present.

The augmenter never invents an entity or fact. It treats prior text as context, not as an instruction capable of overriding system rules.

### 2. Retrieve and rank entities

Candidate rows continue to come from the database. Ranking combines:

- exact normalized full-name, reference, code, and component matches;
- conservative edit similarity for misspellings;
- full-name evidence that distinguishes shared surnames;
- occurrence in a recent structured turn;
- participation in the selected race;
- entity-type words in the question.

Each ranked candidate includes `kind`, numeric `id`, stored `name`, score, and short deterministic reasons. The response selects only candidates above a confidence threshold with adequate separation from the next candidate. Shared surnames and close alternatives remain clarification cases.

### 3. Rank schema and close relationships

Schema ranking uses table names, column names, a small repository-owned intent vocabulary, entity kinds, and the router’s valid table hints. The ranking selects a small table set and then adds the shortest deterministic path from `knowledge/relationships.json` between required tables. For example, a driver wins query needs `drivers`, `results`, and `races` when season or chronology is requested.

Relationship closure never fabricates joins. If no relationship path exists, the system keeps the independently selected tables and records the limitation in the trace. All fourteen tables remain available as a safe fallback when ranking yields no useful table.

## Routing and planning

The route call receives the interpreted question, bounded variants, selected race, recent structured turns, ranked entities, and ranked schema. The router still chooses one of:

- `statistics` for SQL-backed historical analysis;
- `prediction` for the frozen model output;
- `explanation` for stored model contributions;
- `clarify` when the target is ambiguous or required context is absent;
- `unsupported` when the request falls outside the supplied sources.

Deterministic unsupported and ambiguity checks run before Bedrock and use zero model calls. Predictions and explanations use the local predictor after one routing call. Statistics use a second call to generate SQL.

## Controlled SQL repair

The first SQL candidate always passes through the existing SQLGlot policy and read-only executor. A repair call is permitted only when that candidate fails with `UnsafeQuery` or `QueryFailed`.

The repair prompt receives:

- the interpreted question and bounded retrieval context;
- the failed SQL candidate;
- a sanitized failure category and fixed guidance;
- the same selected schema, relationships, terminology, and SQL rules.

It never receives a database URL, credential, access code, traceback, raw driver exception, raw provider body, or unrestricted database metadata. The repaired SQL passes through the same validator and executor. A second failure ends the request with `query_rejected`; there is no fourth call and no loop.

Failure categories are deliberately coarse:

- `validation_rejected` for a parsed-policy rejection;
- `execution_rejected` for a read-only execution or resource-limit failure.

An empty result is a valid execution and is not repaired because absence can be the correct answer. Unsupported, ambiguous, prediction, and explanation paths never invoke repair.

## Call budget

The service owns a request-local call ledger. Before every provider invocation it checks the hard limit of three calls. Provider metadata is appended only after the call returns. Exceeding the budget is treated as a safe query rejection and is covered by tests.

| Route | Maximum Bedrock calls |
| --- | ---: |
| Deterministic unsupported or ambiguity | 0 |
| Prediction or explanation | 1 |
| Successful statistics query | 2 |
| Statistics query repaired once | 3 |

## Audit trace

Every response includes a `trace` object assembled from deterministic application state:

```json
{
  "original_question": "How many wins did Hamliton get?",
  "interpreted_question": "How many wins did hamilton get?",
  "variants": ["How many wins did Hamliton get?", "How many wins did hamilton get?"],
  "route": "statistics",
  "entities": [
    {"kind": "drivers", "id": 1, "name": "Lewis Hamilton", "score": 1.0, "reasons": ["name"]}
  ],
  "tables": ["drivers", "results"],
  "attempts": [
    {"number": 1, "outcome": "executed", "failure_category": null}
  ],
  "provider_call_count": 2,
  "provider_elapsed_ms": 3800.1,
  "total_elapsed_ms": 3812.4
}
```

Provider usage and model identifiers may remain in the existing `provider_calls` field for project evidence, but the trace shows only the call count and aggregate timing. The trace never contains system prompts, bearer tokens, project IDs, connection strings, raw exceptions, or response bodies.

Early deterministic responses also include a trace with route, zero calls, and zero attempts. Clarification responses include ranked candidates or suggestions only when they are safe database labels.

## Frontend behavior

The chat continues to show answers, result tables, charts, assumptions, model explanations, and generated SQL. It additionally:

- sends at most three compact structured prior turns;
- stores only the existing bounded 12-message UI history in session storage;
- derives the request context from resolved response trace entities and intent;
- shows a collapsed “How this answer was built” panel;
- displays the interpreted question, chosen route, entities, tables, SQL attempt count, provider call count, and elapsed time;
- preserves explicit spelling corrections and clarification suggestions.

The access code remains in component state and the request header only. It is never copied into conversation history or trace.

## Logging and evidence

Application logs record one structured completion line per chat request with route, status, provider call count, repair count, selected table names, and elapsed milliseconds. They do not record the question, SQL, entity names, credentials, headers, database URLs, model prompts, or raw exceptions.

Evaluation writes append-only, numbered JSON reports. The existing fixed 40-case benchmark remains unchanged. A separate agentic suite records typo, paraphrase, ambiguity, follow-up, and repair-related behavior. Reports include suite hash, commit, model, case outcome, provider-call count, repair count, and latency. Any failed run is preserved instead of overwritten.

## Evaluation strategy

Offline tests verify pure retrieval scores, relationship closure, ambiguity, context bounds, repair policy, call limits, trace redaction, frontend payloads, and trace rendering. Existing SQL-safety and application tests remain mandatory.

Live evaluation has two tracks:

1. Re-run the immutable 40-case NL2SQL suite and compare accuracy, refusal safety, latency, and calls with Run 06.
2. Run the new agentic suite with explicit expected intent, correction, entity, clarification, and answer checks. Sequential follow-up cases retain their structured prior turn.

The report labels both suites as development evaluations. It does not describe either as an unseen test set.

## Deployment and verification

After all local and PostgreSQL integration checks pass, merge the feature branch to `main`, push GitHub, build the exact merge commit through AWS CodeBuild, deploy its image to the existing Lightsail service, and verify the public API and frontend. AWS mutations must use the guarded release scripts and verify account `148356747273`, profile `default`, and region `eu-north-1` before changing resources.

Cloud verification must cover:

- ordinary historical statistics;
- a misspelled entity with visible correction;
- a structured follow-up;
- an ambiguous family name clarification without SQL;
- unsupported weather refusal without SQL;
- a supported prediction or explanation;
- the frontend audit panel;
- health and existing product routes;
- CloudWatch log evidence without sensitive content.

The release report records the Git commit, CodeBuild build ID and result, Lightsail deployment state, public URL checks, response assertions, and log snapshot count.

## Risks and controls

| Risk | Control |
| --- | --- |
| Model generates unsafe SQL | Existing AST allowlist, single-query policy, read-only connection, timeout, opcode budget, and row cap apply to every attempt. |
| Repair becomes an uncontrolled loop | Exactly one repair call and a request-local three-call limit. |
| Wrong person selected after a typo | Database-backed ranking, confidence separation, full-name evidence, and clarification on ambiguity. |
| Follow-up context overrides rules | Structured bounded fields; prior text is quoted as context and cannot change system policy. |
| Trace leaks secrets or prompts | Trace is constructed from allowlisted fields; tests search serialized responses and logs for sentinel secrets. |
| Schema ranking omits a join table | Deterministic relationship closure plus all-schema fallback when ranking is empty. |
| Evaluation overstates quality | Fixed and agentic suites are reported separately and labeled as development suites; failures are preserved. |
| Deployment drifts from tested code | Image tag and verification report use the exact merged Git SHA. |

## Acceptance criteria

The work is complete when:

- retrieval and reranking are deterministic and tested against real database labels;
- structured follow-ups work without sending result rows or SQL as context;
- failed generated SQL is repaired at most once and all SQL controls still apply;
- every response contains a safe trace and the UI renders it;
- no path exceeds three provider calls;
- all backend, frontend, infrastructure, and PostgreSQL integration checks pass;
- both live evaluation tracks have preserved reports with honest results;
- the exact verified commit is built, deployed to Lightsail, and exercised through the public frontend and API;
- worklog, architecture, evidence, and presentation artifacts reflect the verified result.
