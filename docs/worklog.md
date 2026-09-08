# Engineering worklog

## 2026-09-08 — Source inspection and audit

Read the brief, package README, master source document, all scope slides and speaker notes, and every CSV. Confirmed there was no Git repository. Implemented a deterministic audit with source hashes, missingness, inferred types, key checks, entity references, per-year coverage and suspicious-value reporting. Executed it on all 701,433 rows. Historical duplicate driver/race result records are retained as a documented grain limitation. Raw CSVs and supplied documents remain untouched and excluded from redistribution until licensing provenance is established.

Validation: audit executed successfully; type/null parsing, malformed-row rejection, and report integrity tests executed. The audit is an initial foundation, not a completed product.

## 2026-09-08 — Relational ingestion

Added committed source-to-SQL column mappings, SQLAlchemy metadata, foreign keys, join indexes and transactional ingestion. Loaded all 14 tables into local SQLite; independently compared every table count to the audit and ran `PRAGMA foreign_key_check` with no violations. Seven tests passed, including changed-source and nonempty-target rejection. PostgreSQL DDL compilation was checked; live PostgreSQL has not yet been exercised. Recorded ADR 001. No AWS operations performed.
