# ADR 001 — Relational storage and source grain

Accepted 2026-09-08. Use SQLAlchemy Core metadata with SQLite initially and PostgreSQL-compatible integer/float/text columns. Convert source camelCase names to snake_case using the committed `knowledge/schema.json` mapping. ISO dates and racing time strings stay text to preserve original representations and distinguish elapsed durations from wall-clock times. Missing `\N` and empty strings become SQL NULL. No other values are imputed in storage.

Source primary keys are authoritative. Historical result records are not unique by driver/race, so that pair receives a nonunique index, not a constraint. Join qualifying/laps/pits to results on BOTH race and driver; beware historical multiplicity. Constructor summaries must count distinct races for starts and race wins. Standings are stored post-race snapshots, not reconstructed from points sums (historical scoring rules and deductions matter).

Foreign keys are enforced by the database, including SQLite connection pragmas. The loader verifies source fingerprints before touching tables, refuses nonempty targets, and loads all rows in one transaction in dependency order. It never drops tables. Schema changes currently require a new project database; migrations will be needed for an existing deployed schema. `database/schema.sql` is generated documentation; SQLAlchemy metadata is the executable definition.

Indexes cover entity/race joins and year/round navigation. Raw data, databases and model binaries remain outside Git. The supplied snapshot can be independently checked against committed SHA-256 hashes. A clone needs the source CSV package; automatic third-party downloads are deliberately not claimed while exact provenance is unresolved.
