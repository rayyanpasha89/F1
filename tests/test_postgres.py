"""Opt-in live PostgreSQL verification; requires an ingested database and a SELECT-only role."""

import os
import json
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.database import make_engine
from backend.services.analytics import Analytics
from backend.ml.features import source_frame, build_features, FEATURE_SETS
from backend.ai.sql_safety import postgres_query


@pytest.fixture
def pg():
    url = os.getenv("F1_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set F1_TEST_POSTGRES_URL for live PostgreSQL integration")
    engine = make_engine(url)
    yield engine
    engine.dispose()


def test_ingested_counts_and_api_queries(pg):
    report = json.loads(Path("reports/data_audit.json").read_text())
    with pg.connect() as conn:
        for name, t in report["tables"].items():
            assert conn.scalar(text(f"SELECT COUNT(*) FROM {name}")) == t["rows"]
    a = Analytics(pg)
    assert len(a.races(2024)) == 24
    assert a.standings(2024, "drivers")[0]["position"] == 1
    assert a.standings(1950, "constructors") == []
    for kind in ["grid", "results", "qualifying", "pit-stops"]:
        assert a.race_table(1128, kind)
    assert a.profile("drivers", 844, 2024)["results"]
    assert a.profile("constructors", 6, 2024)["results"]


def test_postgres_features_equal_sqlite_features(pg):
    if not Path("database/f1.db").exists():
        pytest.skip("SQLite source required for cross-engine equivalence")
    left = build_features(source_frame(pg))
    right = build_features(source_frame(make_engine()))
    pd.testing.assert_frame_equal(
        left[FEATURE_SETS["full"]], right[FEATURE_SETS["full"]], check_dtype=False
    )


def test_select_only_role_enforced_independently_of_parser(pg):
    reader_url = os.getenv("F1_TEST_READER_URL")
    if not reader_url:
        pytest.skip("Set F1_TEST_READER_URL for role-isolation check")
    reader = make_engine(reader_url)
    assert postgres_query(reader, "SELECT COUNT(*) FROM races WHERE year=2024")["rows"] == [[24]]
    with pytest.raises(DBAPIError), reader.begin() as conn:
        conn.execute(text("DELETE FROM races WHERE false"))
    with pytest.raises(DBAPIError), reader.begin() as conn:
        conn.execute(text("CREATE TABLE forbidden(id integer)"))
    reader.dispose()
