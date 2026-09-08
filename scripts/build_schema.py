"""Generate reviewed relational metadata from the committed audit, not live inference."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def snake(value):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def main():
    audit = json.loads((ROOT / "reports/data_audit.json").read_text())
    tables = {}
    relationships = []
    for name, t in audit["tables"].items():
        columns = {}
        for source, spec in t["columns"].items():
            col = snake(source)
            # Dates and timing strings stay ISO/text; conversions are explicit in feature code.
            columns[col] = {
                "source": source,
                "type": {"integer": "integer", "float": "float"}.get(spec["inferred_type"], "text"),
                "nullable": spec["missing"] > 0,
            }
        fks = []
        for f in t["foreign_keys"]:
            parent, col = f["references"].split(".")
            edge = {"column": snake(f["column"]), "references": f"{parent}.{snake(col)}"}
            fks.append(edge)
            relationships.append({"table": name, **edge})
        tables[name] = {
            "columns": columns,
            "primary_key": [snake(c) for c in t["primary_key"]],
            "foreign_keys": fks,
        }
    (ROOT / "knowledge/schema.json").write_text(json.dumps(tables, indent=2) + "\n")
    (ROOT / "knowledge/relationships.json").write_text(json.dumps(relationships, indent=2) + "\n")


if __name__ == "__main__":
    main()
