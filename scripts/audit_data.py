"""Reproducible source audit; never modifies supplied CSV files."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = {
    "circuits": ["circuitId"],
    "constructors": ["constructorId"],
    "drivers": ["driverId"],
    "races": ["raceId"],
    "seasons": ["year"],
    "status": ["statusId"],
    "results": ["resultId"],
    "qualifying": ["qualifyId"],
    "constructor_results": ["constructorResultsId"],
    "constructor_standings": ["constructorStandingsId"],
    "driver_standings": ["driverStandingsId"],
    "lap_times": ["raceId", "driverId", "lap"],
    "pit_stops": ["raceId", "driverId", "stop"],
    "sprint_results": ["resultId"],
}
REFERENCES = {
    "raceId": ("races", "raceId"),
    "driverId": ("drivers", "driverId"),
    "constructorId": ("constructors", "constructorId"),
    "circuitId": ("circuits", "circuitId"),
    "statusId": ("status", "statusId"),
    "year": ("seasons", "year"),
}
NULLS = {"", r"\N"}


def read_source(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        if not reader.fieldnames or any(None in row or None in row.values() for row in rows):
            raise ValueError(f"Malformed CSV: {path.name}")
        return reader.fieldnames, rows


def inferred(values):
    values = [v for v in values if v not in NULLS]
    if not values:
        return "unknown"
    for label, convert in [("integer", int), ("float", float), ("date", date.fromisoformat)]:
        try:
            for v in values:
                convert(v)
            return label
        except ValueError:
            pass
    return "text"


def audit(source):
    tables = {name: read_source(source / f"{name}.csv") for name in KEYS}
    races = {r["raceId"]: r for r in tables["races"][1]}
    report = {"format_version": 1, "null_tokens": sorted(NULLS), "tables": {}}
    for name, (columns, rows) in tables.items():
        primary = KEYS[name]
        key_counts = Counter(tuple(r[c] for c in primary) for r in rows)
        fields = {}
        for col in columns:
            vals = [r[col] for r in rows]
            fields[col] = {
                "inferred_type": inferred(vals),
                "missing": sum(v in NULLS for v in vals),
                "distinct_non_null": len(set(vals) - NULLS),
            }
        foreign = []
        for col in columns:
            if col not in REFERENCES or REFERENCES[col][0] == name:
                continue
            parent, key = REFERENCES[col]
            allowed = {r[key] for r in tables[parent][1]}
            orphans = sorted({r[col] for r in rows} - allowed - NULLS)
            foreign.append(
                {"column": col, "references": f"{parent}.{key}", "orphan_values": orphans}
            )
        years = [int(races[r["raceId"]]["year"]) for r in rows if r.get("raceId") in races]
        if "year" in columns:
            years = [int(r["year"]) for r in rows]
        coverage = dict(sorted(Counter(years).items()))
        secondary = (
            ["raceId", "driverId"] if name in {"results", "qualifying", "sprint_results"} else None
        )
        issues = []
        if secondary:
            counts = Counter(tuple(r[k] for k in secondary) for r in rows)
            duplicates = {str(k): v for k, v in counts.items() if v > 1}
            if duplicates:
                issues.append({"duplicate_driver_race": duplicates})
        for col in ("grid", "milliseconds"):
            if col in columns:
                count = sum(r[col] not in NULLS and float(r[col]) <= 0 for r in rows)
                if count:
                    issues.append({f"nonpositive_{col}": count})
        report["tables"][name] = {
            "file": f"{name}.csv",
            "sha256": hashlib.sha256((source / f"{name}.csv").read_bytes()).hexdigest(),
            "rows": len(rows),
            "columns": fields,
            "primary_key": primary,
            "duplicate_primary_keys": sum(n - 1 for n in key_counts.values() if n > 1),
            "null_primary_keys": sum(any(r[c] in NULLS for c in primary) for r in rows),
            "single_column_key_candidates": [
                c
                for c, stats in fields.items()
                if stats["missing"] == 0 and stats["distinct_non_null"] == len(rows)
            ],
            "foreign_keys": foreign,
            "year_range": [min(years), max(years)] if years else None,
            "rows_by_year": coverage,
            "suspicious_values": issues,
        }
    report["total_rows"] = sum(t["rows"] for t in report["tables"].values())
    report["limitations"] = [
        "No weather, tyre compound, fuel load, telemetry, or live updates.",
        "Coverage start does not imply complete coverage; inspect rows_by_year.",
        "Grid 0 is a pit-lane/unknown/nonstandard start, not pole position.",
        "Early shared-drive results can violate driver/race uniqueness; resultId is the source grain.",
        "Final classified position can include nonfinishers; DNF is not equivalent to null position.",
        "Pit duration includes pit-lane transit and interruptions, not necessarily stationary service time.",
        "Retrospectively maintained source: no point-in-time version history for corrections/grid changes.",
        "Source package supplies no license or download receipt; redistribution provenance is unverified.",
    ]
    return report


def render(report):
    lines = [
        "# Dataset audit",
        "",
        "Generated by `python -m scripts.audit_data`. Source bytes are SHA-256 fingerprinted.",
        "",
        f"Total rows: **{report['total_rows']:,}** across {len(report['tables'])} CSVs.",
        "",
        "| Table | Rows | Years | Key duplicates | Missing cells |",
        "|---|---:|---|---:|---:|",
    ]
    for name, t in report["tables"].items():
        lines.append(
            f"| {name} | {t['rows']:,} | {t['year_range']} | {t['duplicate_primary_keys']} | {sum(c['missing'] for c in t['columns'].values()):,} |"
        )
    lines += ["", "## Limitations", ""] + [f"- {s}" for s in report["limitations"]]
    for name, t in report["tables"].items():
        lines += [
            "",
            f"## {name}",
            "",
            f"Grain/key: `{', '.join(t['primary_key'])}`.",
            "",
            "| Column | Inferred type | Missing |",
            "|---|---|---:|",
        ]
        lines += [
            f"| {c} | {s['inferred_type']} | {s['missing']} |" for c, s in t["columns"].items()
        ]
        lines += [
            "",
            "Relationships: "
            + "; ".join(
                f"{f['column']} → {f['references']} ({len(f['orphan_values'])} orphan values)"
                for f in t["foreign_keys"]
            ),
            "",
            "Findings: `" + json.dumps(t["suspicious_values"]) + "`",
        ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "dataset")
    args = parser.parse_args()
    report = audit(args.source)
    (ROOT / "reports/data_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "docs/data_audit.md").write_text(render(report))
    print(json.dumps({"total_rows": report["total_rows"], "tables": len(report["tables"])}))
    if any(
        t["duplicate_primary_keys"]
        or t["null_primary_keys"]
        or any(f["orphan_values"] for f in t["foreign_keys"])
        for t in report["tables"].values()
    ):
        raise SystemExit("Integrity failures; inspect audit before ingestion.")


if __name__ == "__main__":
    main()
