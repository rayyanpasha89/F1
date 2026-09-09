"""One-off private database ingestion; credentials arrive only through environment."""

import json
import os
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from psycopg import sql
from sqlalchemy import text

from backend.database import ROOT, SCHEMA, make_engine
from scripts.load_data import ingest


def main():
    engine = make_engine(os.environ["F1_BOOTSTRAP_DATABASE_URL"])
    expected = {
        name: value["rows"]
        for name, value in json.loads((ROOT / "reports/data_audit.json").read_text())[
            "tables"
        ].items()
    }
    with engine.connect() as conn:
        exists = conn.scalar(text("SELECT to_regclass('public.races')")) is not None
    if exists:
        with engine.connect() as conn:
            counts = {name: conn.scalar(text(f'SELECT COUNT(*) FROM "{name}"')) for name in SCHEMA}
    else:
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            urllib.request.urlretrieve(os.environ["F1_SOURCE_URL"], dest / "source.zip")
            with zipfile.ZipFile(dest / "source.zip") as archive:
                if set(archive.namelist()) != {f"{name}.csv" for name in SCHEMA}:
                    raise ValueError("Unexpected archive members")
                archive.extractall(dest)
            counts = ingest(engine, dest)
    if counts != expected:
        raise RuntimeError("Database counts differ from audited source; no repair attempted")
    with engine.begin() as conn:
        cursor = conn.connection.driver_connection.cursor()
        exists = cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'f1_reader'").fetchone()
        if not exists:
            cursor.execute(
                sql.SQL("CREATE ROLE f1_reader LOGIN PASSWORD {}").format(
                    sql.Literal(os.environ["F1_READER_PASSWORD"])
                )
            )
        cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cursor.execute("GRANT CONNECT ON DATABASE f1 TO f1_reader")
        cursor.execute("GRANT USAGE ON SCHEMA public TO f1_reader")
        cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO f1_reader")
        cursor.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO f1_reader"
        )
        cursor.execute("ALTER ROLE f1_reader SET default_transaction_read_only = on")
        cursor.close()
    engine.dispose()
    print(json.dumps({"stage": "bootstrap_complete", "counts": counts}), flush=True)
    # Keep the one-off container alive until the operator sees completion and replaces it.
    time.sleep(3600)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"stage": "failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
