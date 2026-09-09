import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from backend.database import make_engine, metadata
from scripts.load_data import ingest


def test_foreign_keys_and_not_null_enforced():
    engine = make_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(metadata.tables["races"].insert(), {"race_id": 1, "year": 9999})
    assert "FOREIGN KEY" in str(
        CreateTable(metadata.tables["results"]).compile(dialect=postgresql.dialect())
    )


def test_all_ingested_counts_and_integrity():
    if not Path("database/f1.db").exists():
        pytest.skip("Run ingestion for full source integration check")
    report = json.loads(Path("reports/data_audit.json").read_text())
    with make_engine().connect() as conn:
        for name, t in report["tables"].items():
            assert conn.scalar(select(func.count()).select_from(metadata.tables[name])) == t["rows"]
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        assert (
            conn.scalar(text("SELECT MAX(date) FROM races JOIN results USING (race_id)"))
            == "2024-12-08"
        )
        assert conn.scalar(text("SELECT COUNT(*) FROM results WHERE milliseconds IS NULL")) > 0


def test_ingestion_rejects_changed_source(tmp_path):
    (tmp_path / "circuits.csv").write_text("changed")
    with pytest.raises(ValueError, match="fingerprint"):
        ingest(make_engine("sqlite:///:memory:"), tmp_path)


def test_ingestion_does_not_overwrite():
    if not Path("dataset/races.csv").exists() or not Path("database/f1.db").exists():
        pytest.skip("Local source required")
    with pytest.raises(ValueError, match="not empty"):
        ingest(make_engine(), Path("dataset"))


def test_constructor_results_include_sprint_points_in_supplied_snapshot():
    if not Path("database/f1.db").exists():
        pytest.skip("Source integration requires ingestion")
    with make_engine().connect() as conn:
        race_points = conn.scalar(
            text(
                "SELECT SUM(points) FROM results JOIN races USING(race_id) WHERE constructor_id=6 AND year=2024"
            )
        )
        sprint_points = conn.scalar(
            text(
                "SELECT SUM(points) FROM sprint_results JOIN races USING(race_id) WHERE constructor_id=6 AND year=2024"
            )
        )
        constructor_points = conn.scalar(
            text(
                "SELECT SUM(points) FROM constructor_results JOIN races USING(race_id) WHERE constructor_id=6 AND year=2024"
            )
        )
        assert sprint_points > 0
        assert constructor_points == race_points + sprint_points


def test_synthetic_ingestion_is_transactional_without_private_source(tmp_path):
    import csv
    from backend.database import SCHEMA

    source = tmp_path / "source"
    source.mkdir()
    for name, spec in SCHEMA.items():
        with (source / f"{name}.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([s["source"] for s in spec["columns"].values()])
            writer.writerow(
                [
                    2024
                    if col == "year"
                    else 1
                    if s["type"] in {"integer", "float"}
                    else "synthetic"
                    for col, s in spec["columns"].items()
                ]
            )
    engine = make_engine("sqlite:///:memory:")
    counts = ingest(engine, source, verify_hashes=False)
    assert len(counts) == 14 and all(n == 1 for n in counts.values())
    # A source constraint failure late in dependency order must roll back earlier rows.
    results = source / "results.csv"
    with results.open() as stream:
        rows = list(csv.reader(stream))
    rows[1][rows[0].index("driverId")] = "999"
    with results.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    rejected = make_engine("sqlite:///:memory:")
    with pytest.raises(IntegrityError):
        ingest(rejected, source, verify_hashes=False)
    with rejected.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(metadata.tables["drivers"])) == 0
