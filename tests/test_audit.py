import json
from pathlib import Path
from scripts.audit_data import inferred, read_source


def test_type_inference_and_nulls():
    assert inferred(["1", r"\N", ""]) == "integer"
    assert inferred(["0.5", "1"]) == "float"
    assert inferred(["2024-12-08"]) == "date"
    assert inferred([r"\N"]) == "unknown"
    assert inferred(["01:23.123"]) == "text"


def test_malformed_csv_is_rejected(tmp_path):
    import pytest

    p = tmp_path / "bad.csv"
    p.write_text("id,name\n1\n")
    with pytest.raises(ValueError):
        read_source(p)


def test_checked_in_audit_integrity():
    report = json.loads(Path("reports/data_audit.json").read_text())
    assert len(report["tables"]) == 14
    assert report["tables"]["races"]["year_range"] == [1950, 2024]
    assert report["tables"]["pit_stops"]["year_range"] == [2011, 2024]
    for table in report["tables"].values():
        assert table["rows"] > 0
        assert table["duplicate_primary_keys"] == 0
        assert table["null_primary_keys"] == 0
        assert all(not fk["orphan_values"] for fk in table["foreign_keys"])
