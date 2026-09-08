"""Portable metadata and connection factory; ingestion never runs during API startup."""

import json
import os
from pathlib import Path

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    event,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "knowledge/schema.json").read_text())
metadata = MetaData()
TYPES = {"integer": Integer, "float": Float, "text": Text}
for name, spec in SCHEMA.items():
    refs = {f["column"]: f["references"] for f in spec["foreign_keys"]}
    table = Table(
        name,
        metadata,
        *[
            Column(
                col,
                TYPES[s["type"]],
                *([ForeignKey(refs[col])] if col in refs else []),
                primary_key=col in spec["primary_key"],
                nullable=s["nullable"],
                autoincrement=False,
            )
            for col, s in spec["columns"].items()
        ],
    )
    for col in refs:
        if col not in spec["primary_key"][:1]:
            Index(f"ix_{name}_{col}", table.c[col])
Index("ix_races_year_round", metadata.tables["races"].c.year, metadata.tables["races"].c.round)
Index(
    "ix_results_race_driver",
    metadata.tables["results"].c.race_id,
    metadata.tables["results"].c.driver_id,
)


def make_engine(url=None):
    url = url or os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'database/f1.db'}")
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def configure(dbapi, record):
            dbapi.execute("PRAGMA foreign_keys=ON")
            dbapi.execute("PRAGMA busy_timeout=5000")

    return engine
