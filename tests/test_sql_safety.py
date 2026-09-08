from pathlib import Path
import sqlite3

import pytest
from backend.ai.sql_safety import validate_sql, sqlite_query, UnsafeQuery, QueryFailed


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE races",
        "DELETE FROM races",
        "UPDATE races SET year=1",
        "INSERT INTO races VALUES(1)",
        "ALTER TABLE races ADD COLUMN secret TEXT",
        "CREATE TABLE bad(id INT)",
        "TRUNCATE races",
        "SELECT * FROM races; DROP TABLE drivers",
        "PRAGMA writable_schema=ON",
        "ATTACH DATABASE '/tmp/evil.db' AS evil",
        "SELECT * FROM sqlite_master",
        "SELECT load_extension('evil')",
        "SELECT randomblob(1000000000)",
        "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT * FROM x",
        "SELECT * INTO other FROM races",
        "SELECT * FROM races FOR UPDATE",
        "SELECT * FROM races CROSS JOIN results",
        "SELECT * FROM races,results",
        "SELECT * FROM lap_times LIMIT 5",
        "SELECT * FROM pit_stops LIMIT 5",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM information_schema.tables",
        "WITH x AS (DELETE FROM races RETURNING *) SELECT * FROM x",
    ],
)
def test_rejects_unsafe_queries(sql):
    with pytest.raises(UnsafeQuery):
        validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) AS races FROM races WHERE year=2023",
        "WITH x AS (SELECT year, COUNT(*) AS n FROM races GROUP BY year) SELECT * FROM x ORDER BY year",
        "SELECT d.surname, COUNT(*) AS wins FROM results x JOIN drivers d USING(driver_id) WHERE x.position=1 GROUP BY d.driver_id,d.surname",
        "SELECT race_id,AVG(milliseconds) AS average FROM lap_times GROUP BY race_id",
        "SELECT MIN(milliseconds) FROM pit_stops",
    ],
)
def test_permits_bounded_analytics(sql):
    assert validate_sql(sql)
    if Path("database/f1.db").exists():
        result = sqlite_query("database/f1.db", sql)
        assert result["columns"] and len(result["rows"]) <= 200


def test_row_limit_and_database_read_only(tmp_path):
    p = tmp_path / "f1.db"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE races(race_id INTEGER,year INTEGER)")
        c.executemany("INSERT INTO races VALUES(?,2024)", [(i,) for i in range(300)])
    result = sqlite_query(p, "SELECT race_id FROM races ORDER BY race_id", max_rows=10)
    assert len(result["rows"]) == 10 and result["truncated"]
    assert result["rows"][0] == [0]
    with pytest.raises(UnsafeQuery):
        sqlite_query(p, "DELETE FROM races")
    with sqlite3.connect(p) as c:
        assert c.execute("SELECT COUNT(*) FROM races").fetchone()[0] == 300


def test_expensive_query_interrupted_and_error_is_safe(tmp_path):
    p = tmp_path / "f1.db"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE results(race_id INTEGER,points INTEGER)")
        c.executemany("INSERT INTO results VALUES(1,1)", [()] * 500)
    with pytest.raises(QueryFailed, match="resource limits"):
        sqlite_query(
            p,
            "SELECT SUM(a.points*b.points) FROM results a JOIN results b ON a.race_id=b.race_id",
            opcode_budget=1000,
        )
    with pytest.raises(QueryFailed):
        sqlite_query(p, "SELECT nonexistent FROM results")
