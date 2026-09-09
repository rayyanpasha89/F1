# SQL generation and execution rules

Use only the committed F1 schema, snake_case column names and explicit join keys. SELECT and nonrecursive read-only WITH queries are supported. One statement only. No mutations, DDL, locking, metadata introspection, external schemas, arbitrary functions, Cartesian joins or raw lap/pit dumps. Maximum eight joins, 12,000 SQL characters, 700 parsed nodes, 200 returned rows and one-second query execution budget. SQLite also has a two-million-opcode budget. Unsupported function/query shapes should be rephrased, not retried unsafely.

Join pit_stops and lap_times to results on both race_id and driver_id when deriving constructors. Avoid multiplying counts by joining several one-to-many tables before aggregation. Group detail tables before deeper joins. Count distinct races for race counts. Do not substitute race points for recorded standings. State filters, units and missing-data limitations with returned rows. Do not claim that successful execution proves answer correctness.

SQLite uses a separate mode=ro connection, query_only, a restrictive authorizer and progress handler. PostgreSQL requires a dedicated SELECT-only role, read-only transactions and statement/lock timeouts. The model cannot access ingestion credentials. Application answers must be rendered from executed rows, not model-memory statistics. No unsupported weather answers.

For points explicitly excluding sprints, use SUM(results.points). constructor_results.points includes sprint points on sprint weekends in this snapshot. Always use races.round/date for the last race, never MAX(race_id).
