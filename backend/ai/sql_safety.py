"""Defense in depth: AST policy plus a separate read-only SQL connection."""

from contextlib import closing
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

import sqlglot
from sqlglot import exp
from sqlalchemy import text

from backend.database import SCHEMA


class UnsafeQuery(ValueError):
    pass


class QueryFailed(ValueError):
    pass


ALLOWED_FUNCTIONS = {
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "ROUND",
    "ABS",
    "COALESCE",
    "NULLIF",
    "LOWER",
    "UPPER",
    "LENGTH",
    "SUBSTR",
    "SUBSTRING",
    "STRFTIME",
    "DATE",
    "CAST",
    "EXTRACT",
    "ROW_NUMBER",
    "RANK",
    "DENSE_RANK",
    "LAG",
    "LEAD",
}
SQLITE_FUNCTIONS = {name.lower() for name in ALLOWED_FUNCTIONS} | {"like"}


def validate_sql(sql, dialect="sqlite"):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 12000:
        raise UnsafeQuery("Query must be a nonempty SQL statement under 12,000 characters.")
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except (sqlglot.errors.ParseError, RecursionError) as exc:
        raise UnsafeQuery("SQL could not be parsed.") from exc
    if len(statements) != 1 or not isinstance(
        statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
    ):
        raise UnsafeQuery("Only one SELECT or read-only WITH query is permitted.")
    tree = statements[0]
    nodes = list(tree.walk())
    if len(nodes) > 700:
        raise UnsafeQuery("Query is too complex.")
    forbidden = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Create,
        exp.Drop,
        exp.Alter,
        exp.Command,
        exp.Into,
        exp.Lock,
        exp.Transaction,
    )
    if any(isinstance(node, forbidden) for node in nodes):
        raise UnsafeQuery("Mutation or locking SQL is not permitted.")
    if any(w.args.get("recursive") for w in tree.find_all(exp.With)):
        raise UnsafeQuery("Recursive queries are not permitted.")
    ctes = {c.alias for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.db or table.catalog or table.name not in set(SCHEMA) | ctes:
            raise UnsafeQuery("Query references a table outside the F1 schema.")
    joins = list(tree.find_all(exp.Join))
    if len(joins) > 8 or any(
        j.args.get("kind") == "CROSS" or not (j.args.get("on") or j.args.get("using"))
        for j in joins
    ):
        raise UnsafeQuery("Joins require explicit keys and are limited to eight.")
    for function in tree.find_all(exp.Func):
        # CASE/IF are structural expressions, not arbitrary database function calls.
        if isinstance(function, (exp.Case, exp.If, exp.And, exp.Or)):
            continue
        name = (
            function.name.upper()
            if isinstance(function, exp.Anonymous)
            else function.sql_name().upper()
        )
        if name not in ALLOWED_FUNCTIONS:
            raise UnsafeQuery(f"Function {name} is outside the supported analytics functions.")
    outer_aggregates = isinstance(tree, exp.Select) and any(
        agg.find_ancestor(exp.Select) is tree for agg in tree.find_all(exp.AggFunc)
    )
    for select in tree.find_all(exp.Select):
        direct_tables = [
            t for t in select.find_all(exp.Table) if t.find_ancestor(exp.Select) is select
        ]
        if any(t.name in {"lap_times", "pit_stops"} for t in direct_tables):
            if not outer_aggregates and not any(
                expression.find(exp.AggFunc) or isinstance(expression, exp.AggFunc)
                for expression in select.expressions
            ):
                raise UnsafeQuery(
                    "Lap and pit-stop questions require aggregation; raw dumps are unavailable."
                )
    return tree.sql(dialect=dialect)


def sqlite_query(path, sql, max_rows=200, timeout_seconds=1.0, opcode_budget=2_000_000):
    checked = validate_sql(sql)
    if not 1 <= max_rows <= 200:
        raise ValueError("Row cap must be between 1 and 200")
    path = Path(path).resolve()
    start = time.monotonic()
    steps = 0

    def progress():
        nonlocal steps
        steps += 1000
        return int(steps > opcode_budget or time.monotonic() - start > timeout_seconds)

    def authorize(action, arg1, arg2, db, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and arg1 in SCHEMA:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in SQLITE_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    try:
        with closing(
            sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=timeout_seconds)
        ) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.set_authorizer(authorize)
            conn.set_progress_handler(progress, 1000)
            cursor = conn.execute(
                f"SELECT * FROM ({checked}) AS bounded_answer LIMIT {max_rows + 1}"
            )
            columns = [c[0] for c in cursor.description]
            rows = cursor.fetchall()
            return {
                "columns": columns,
                "rows": [list(r) for r in rows[:max_rows]],
                "truncated": len(rows) > max_rows,
                "sql": checked,
                "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
            }
    except sqlite3.Error as exc:
        raise QueryFailed(
            "Query could not run within the read-only schema and resource limits."
        ) from exc


def postgres_query(readonly_engine, sql, max_rows=200):
    """Caller supplies a dedicated SELECT-only role, not the ingestion connection."""
    checked = validate_sql(sql, "postgres")
    if not 1 <= max_rows <= 200:
        raise ValueError("Invalid row cap")
    start = time.monotonic()
    try:
        with readonly_engine.connect() as conn, conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '1000ms'"))
            conn.execute(text("SET LOCAL lock_timeout = '250ms'"))
            cursor = conn.execute(
                text(f"SELECT * FROM ({checked}) AS bounded_answer LIMIT {max_rows + 1}")
            )
            columns = list(cursor.keys())
            rows = cursor.fetchall()
            return {
                "columns": columns,
                "rows": [list(r) for r in rows[:max_rows]],
                "truncated": len(rows) > max_rows,
                "sql": checked,
                "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
            }
    except Exception as exc:
        raise QueryFailed(
            "Query could not run within the read-only schema and resource limits."
        ) from exc
