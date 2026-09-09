"""One-off Fargate ingestion. Operates only on this project's private RDS database."""

import json
import os
import secrets
import tempfile
import zipfile
from pathlib import Path

import boto3
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL

from backend.database import ROOT, SCHEMA, make_engine
from scripts.load_data import ingest


def main():
    session = boto3.Session(region_name="eu-north-1")  # ECS task role, not local profiles
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != "148356747273" or os.environ["F1_ACCOUNT_ID"] != identity["Account"]:
        raise RuntimeError("Wrong AWS account; refusing bootstrap")
    print(json.dumps({"stage": "identity", "account": identity["Account"]}), flush=True)
    sm = session.client("secretsmanager")
    admin = json.loads(sm.get_secret_value(SecretId=os.environ["F1_ADMIN_SECRET"])["SecretString"])
    tls = {
        "sslmode": "verify-full",
        "sslrootcert": "/usr/local/share/ca-certificates/rds-global.pem",
    }
    url = URL.create(
        "postgresql+psycopg",
        username=admin["username"],
        password=admin["password"],
        host=os.environ["F1_DB_HOST"],
        port=5432,
        database="f1",
        query=tls,
    )
    engine = make_engine(url)
    with tempfile.TemporaryDirectory() as temp:
        dest = Path(temp)
        session.client("s3").download_file(
            os.environ["F1_ARTIFACT_BUCKET"], "dataset/source.zip", str(dest / "source.zip")
        )
        with zipfile.ZipFile(dest / "source.zip") as archive:
            expected = {f"{name}.csv" for name in SCHEMA}
            if set(archive.namelist()) != expected:
                raise ValueError("Dataset archive must contain exactly the audited CSV names")
            archive.extractall(dest)
        with engine.connect() as conn:
            populated = conn.scalar(text("SELECT to_regclass('public.races')")) is not None
        if not populated:
            counts = ingest(engine, dest)
        else:
            # Repeat attempts validate, never delete or overwrite an existing dataset.
            with engine.connect() as conn:
                counts = {
                    name: conn.scalar(text(f'SELECT COUNT(*) FROM "{name}"')) for name in SCHEMA
                }
        expected_counts = {
            name: spec["rows"]
            for name, spec in json.loads((ROOT / "reports/data_audit.json").read_text())[
                "tables"
            ].items()
        }
        if counts != expected_counts:
            raise RuntimeError("Ingested row counts differ from audit; no repair attempted")
    runtime = json.loads(
        sm.get_secret_value(SecretId=os.environ["F1_RUNTIME_SECRET"])["SecretString"]
    )
    # Reuse a prior reader password on retries; rotating it would disrupt running tasks.
    from sqlalchemy.engine import make_url

    password = (
        make_url(runtime["DATABASE_URL"]).password
        if runtime.get("DATABASE_URL")
        else secrets.token_urlsafe(36)
    )
    with engine.begin() as conn:
        raw = conn.connection.driver_connection
        with raw.cursor() as cursor:
            exists = cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'f1_reader'").fetchone()
            if not exists:
                cursor.execute(
                    sql.SQL("CREATE ROLE f1_reader LOGIN PASSWORD {}").format(sql.Literal(password))
                )
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute("GRANT CONNECT ON DATABASE f1 TO f1_reader")
            cursor.execute("GRANT USAGE ON SCHEMA public TO f1_reader")
            cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO f1_reader")
            cursor.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO f1_reader"
            )
    reader = URL.create(
        "postgresql+psycopg",
        username="f1_reader",
        password=password,
        host=os.environ["F1_DB_HOST"],
        port=5432,
        database="f1",
        query=tls,
    ).render_as_string(hide_password=False)
    runtime.update(DATABASE_URL=reader, SQL_READONLY_DATABASE_URL=reader)
    sm.put_secret_value(SecretId=os.environ["F1_RUNTIME_SECRET"], SecretString=json.dumps(runtime))
    reader_engine = make_engine(reader)
    with reader_engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM races")) == counts["races"]
        assert not conn.scalar(text("SELECT has_table_privilege(current_user, 'races', 'DELETE')"))
        assert not conn.scalar(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        )
    print(
        json.dumps({"stage": "complete", "counts": counts, "reader_select_only": True}), flush=True
    )
    reader_engine.dispose()
    engine.dispose()


if __name__ == "__main__":
    # Do not print connection URLs or SDK exception responses containing secret material.
    try:
        main()
    except Exception as exc:
        print(json.dumps({"stage": "failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
