"""Strict, transactional import into empty project tables. Never drops/replaces data."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import sqlite

from backend.database import ROOT, SCHEMA, make_engine, metadata
from scripts.audit_data import NULLS


def ingest(engine, source, verify_hashes=True):
    manifest = json.loads((ROOT / "reports/data_audit.json").read_text())
    for name in SCHEMA:
        path = source / f"{name}.csv"
        if (
            verify_hashes
            and hashlib.sha256(path.read_bytes()).hexdigest() != manifest["tables"][name]["sha256"]
        ):
            raise ValueError(f"Source fingerprint mismatch: {name}; audit changes before importing")
    metadata.create_all(engine)
    counts = {}
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if conn.scalar(select(func.count()).select_from(table)):
                raise ValueError("Target database is not empty. Use a new project database URL.")
        for table in metadata.sorted_tables:
            spec = SCHEMA[table.name]["columns"]
            total = 0
            batch = []
            with (source / f"{table.name}.csv").open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != [s["source"] for s in spec.values()]:
                    raise ValueError(f"Column mismatch: {table.name}")
                for row in reader:
                    item = {}
                    for col, s in spec.items():
                        value = row[s["source"]]
                        item[col] = (
                            None
                            if value in NULLS
                            else {"integer": int, "float": float, "text": str}[s["type"]](value)
                        )
                    batch.append(item)
                    if len(batch) >= 2000:
                        conn.execute(table.insert(), batch)
                        total += len(batch)
                        batch = []
                if batch:
                    conn.execute(table.insert(), batch)
                    total += len(batch)
            counts[table.name] = total
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "dataset")
    parser.add_argument("--url", default=None)
    args = parser.parse_args()
    engine = make_engine(args.url)
    counts = ingest(engine, args.source)
    (ROOT / "reports/ingestion.json").write_text(json.dumps(counts, indent=2) + "\n")
    ddl = [
        str(CreateTable(t).compile(dialect=sqlite.dialect())) + ";" for t in metadata.sorted_tables
    ]
    ddl += [
        str(CreateIndex(i).compile(dialect=sqlite.dialect())) + ";"
        for t in metadata.sorted_tables
        for i in sorted(t.indexes, key=lambda i: i.name)
    ]
    (ROOT / "database/schema.sql").write_text("\n".join(ddl))
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
