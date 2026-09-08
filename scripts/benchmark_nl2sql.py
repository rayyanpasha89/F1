"""Live fixed-suite evaluation. Gold SQL is never supplied to the model."""

import argparse
import hashlib
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import sqlglot
from sqlglot import exp

from backend.database import ROOT, make_engine
from backend.ai.chat import ChatService, ChatRequest
from backend.ai.sql_safety import sqlite_query, validate_sql


def equivalent(actual, expected):
    if len(actual) != len(expected):
        return False

    def same(a, b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return math.isclose(a, b, rel_tol=1e-5, abs_tol=0.005)
        return a == b

    # Compare as row multisets: rankings are checked separately where order is specified.
    remaining = list(expected)
    for row in actual:
        match = next(
            (
                i
                for i, other in enumerate(remaining)
                if len(row) == len(other) and all(same(a, b) for a, b in zip(row, other))
            ),
            None,
        )
        if match is None:
            return False
        remaining.pop(match)
    return not remaining


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite benchmark evidence; use a new output name.")
    cases_path = ROOT / "tests/nl2sql/questions.json"
    cases = json.loads(cases_path.read_text())
    service = ChatService(make_engine())
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "suite_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "model": "openai.gpt-oss-120b",
        "comparison": "Exact row multiset and positional column values, numeric tolerance abs 0.005/rel 1e-5; aliases ignored. Join table/key checks are structural proxies, not proof.",
        "cases": [],
    }
    for case in cases:
        start = time.monotonic()
        record = {
            "id": case["id"],
            "question": case["question"],
            "expected_intent": case["expected_intent"],
        }
        try:
            result = service.answer(ChatRequest(question=case["question"]))
            record["response"] = result
            sql = result.get("sql")
            record["sql_valid"] = False
            record["execution_success"] = result.get("status") == "executed"
            if sql:
                try:
                    validate_sql(sql)
                    record["sql_valid"] = True
                except ValueError:
                    pass
            if case["expected_intent"] == "unsupported":
                record["safe_refusal"] = (
                    result["intent"] == "unsupported" and not record["execution_success"]
                )
                record["answer_correct"] = record["safe_refusal"]
            else:
                gold = sqlite_query(ROOT / "database/f1.db", case["gold_sql"])
                record["expected_rows"] = gold["rows"]
                record["answer_correct"] = record["execution_success"] and equivalent(
                    result["result"]["rows"], gold["rows"]
                )
                if sql and record["sql_valid"]:
                    tree = sqlglot.parse_one(sql)
                    actual_tables = {t.name for t in tree.find_all(exp.Table)}
                    record["required_tables_present"] = (
                        set(case["required_tables"]) <= actual_tables
                    )
                    join_keys = {
                        column.name
                        for eq in tree.find_all(exp.EQ)
                        for column in [eq.left, eq.right]
                        if isinstance(column, exp.Column)
                    }
                    join_keys |= {
                        c.name for j in tree.find_all(exp.Join) for c in (j.args.get("using") or [])
                    }
                    needed = (
                        {"race_id", "driver_id"}
                        if "pit_stops" in case["required_tables"]
                        and "results" in case["required_tables"]
                        else set()
                    )
                    record["critical_join_keys_present"] = needed <= join_keys
                record["safe_refusal"] = None
        except Exception as exc:
            record.update({"answer_correct": False, "error_type": type(exc).__name__})
        record["elapsed_ms"] = round((time.monotonic() - start) * 1000, 3)
        report["cases"].append(record)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            case["id"],
            "PASS" if record["answer_correct"] else "FAIL",
            record.get("error_type", ""),
            flush=True,
        )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = {
        "cases": len(cases),
        "answer_correct": sum(r["answer_correct"] for r in report["cases"]),
        "analytics_correct": sum(
            r["answer_correct"] for r in report["cases"] if r["expected_intent"] == "statistics"
        ),
        "safe_refusals": sum(r.get("safe_refusal") is True for r in report["cases"]),
        "execution_success": sum(r.get("execution_success", False) for r in report["cases"]),
        "mean_latency_ms": sum(r["elapsed_ms"] for r in report["cases"]) / len(cases),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
