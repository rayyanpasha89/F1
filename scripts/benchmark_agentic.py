"""Live development evaluation for retrieval, context, and bounded repair."""

import argparse
import hashlib
import json
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.ai.chat import ChatRequest, ChatService
from backend.ai.sql_safety import sqlite_query
from backend.database import ROOT, make_engine
from scripts.benchmark_nl2sql import equivalent


def build_request(case):
    return ChatRequest.model_validate(
        {
            key: case[key]
            for key in ["question", "race_id", "previous_question", "conversation"]
            if key in case
        }
    )


def _expected_subset(expected, actual, fields):
    expected_values = {tuple(item.get(field) for field in fields) for item in expected}
    actual_values = {tuple(item.get(field) for field in fields) for item in actual}
    return expected_values <= actual_values


def evaluate_case(service, case, gold_runner=None):
    gold_runner = gold_runner or (lambda sql: sqlite_query(ROOT / "database/f1.db", sql))
    start = time.monotonic()
    record = {
        "id": case["id"],
        "question": case["question"],
        "expected_intent": case["expected_intent"],
    }
    try:
        response = service.answer(build_request(case))
        trace = response.get("trace", {})
        checks = {"intent": response.get("intent") == case["expected_intent"]}
        if "expected_corrections" in case:
            checks["corrections"] = _expected_subset(
                case["expected_corrections"],
                response.get("corrections", []),
                ("original", "corrected"),
            )
        if "expected_entities" in case:
            checks["entities"] = _expected_subset(
                case["expected_entities"], trace.get("entities", []), ("kind", "id")
            )
        if "expected_tables" in case:
            checks["tables"] = set(case["expected_tables"]) <= set(trace.get("tables", []))

        expected_intent = case["expected_intent"]
        if expected_intent == "statistics":
            gold = gold_runner(case["gold_sql"])
            checks["executed"] = response.get("status") == "executed"
            checks["rows"] = checks["executed"] and equivalent(
                response.get("result", {}).get("rows", []), gold["rows"]
            )
        elif expected_intent == "clarify":
            checks["safe_non_execution"] = "sql" not in response and "result" not in response
            if "expected_suggestions" in case:
                checks["suggestions"] = set(case["expected_suggestions"]) <= set(
                    response.get("suggestions", [])
                )
        elif expected_intent == "unsupported":
            checks["safe_non_execution"] = "sql" not in response and "result" not in response
        else:
            checks["prediction"] = bool(response.get("prediction", {}).get("predictions"))

        record.update(
            {
                "response": response,
                "checks": checks,
                "answer_correct": all(checks.values()),
                "provider_call_count": trace.get(
                    "provider_call_count", len(response.get("provider_calls", []))
                ),
                "repair_count": trace.get("repair_count", 0),
            }
        )
    except Exception as exc:
        record.update(
            {
                "checks": {},
                "answer_correct": False,
                "provider_call_count": 0,
                "repair_count": 0,
                "error_type": type(exc).__name__,
            }
        )
    record["elapsed_ms"] = round((time.monotonic() - start) * 1000, 3)
    return record


def summarize(records):
    distribution = Counter(str(record.get("provider_call_count", 0)) for record in records)
    count = len(records)
    return {
        "cases": count,
        "answer_correct": sum(record.get("answer_correct", False) for record in records),
        "statistics_correct": sum(
            record.get("answer_correct", False)
            for record in records
            if record.get("expected_intent") == "statistics"
        ),
        "safe_non_statistics": sum(
            record.get("answer_correct", False)
            for record in records
            if record.get("expected_intent") in {"clarify", "unsupported"}
        ),
        "provider_calls": sum(record.get("provider_call_count", 0) for record in records),
        "provider_call_distribution": dict(sorted(distribution.items())),
        "repairs": sum(record.get("repair_count", 0) for record in records),
        "mean_latency_ms": round(
            sum(record.get("elapsed_ms", 0) for record in records) / count if count else 0.0,
            3,
        ),
    }


def run_benchmark(
    output,
    *,
    cases_path=ROOT / "tests/nl2sql/agentic_questions.json",
    service=None,
    gold_runner=None,
    git_commit=None,
    model="openai.gpt-oss-120b",
):
    output = Path(output)
    cases_path = Path(cases_path)
    if output.exists():
        raise SystemExit("Refusing to overwrite benchmark evidence; use a new output name.")
    cases = json.loads(cases_path.read_text())
    service = service or ChatService(make_engine())
    git_commit = (
        git_commit
        or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "suite_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "git_commit": git_commit,
        "model": model,
        "evaluation_type": "development suite; not an unseen generalization estimate",
        "cases": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    for case in cases:
        record = evaluate_case(service, case, gold_runner)
        report["cases"].append(record)
        report["summary"] = summarize(report["cases"])
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            case["id"],
            "PASS" if record["answer_correct"] else "FAIL",
            record.get("error_type", ""),
            flush=True,
        )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = summarize(report["cases"])
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_benchmark(args.output)
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
