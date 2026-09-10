import hashlib
import json

import pytest

from scripts.benchmark_agentic import (
    build_request,
    evaluate_case,
    run_benchmark,
    summarize,
)


class FakeService:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def answer(self, request):
        self.requests.append(request)
        return self.response


def test_build_request_constructs_structured_followup_context():
    request = build_request(
        {
            "question": "How many did he win in 2020?",
            "race_id": 1128,
            "conversation": [
                {
                    "question": "Tell me about Lewis Hamilton",
                    "intent": "statistics",
                    "entities": [{"kind": "drivers", "id": 1, "name": "Lewis Hamilton"}],
                    "race_id": None,
                }
            ],
        }
    )

    assert request.question == "How many did he win in 2020?"
    assert request.race_id == 1128
    assert request.conversation[0].entities[0].id == 1
    assert request.previous_question is None


def test_evaluate_case_checks_rows_corrections_entities_tables_calls_and_repairs():
    response = {
        "intent": "statistics",
        "status": "executed",
        "corrections": [{"original": "Hamliton", "corrected": "hamilton"}],
        "result": {"columns": ["wins"], "rows": [[105]]},
        "trace": {
            "entities": [{"kind": "drivers", "id": 1, "name": "Lewis Hamilton"}],
            "tables": ["drivers", "results"],
            "provider_call_count": 3,
            "repair_count": 1,
        },
    }
    service = FakeService(response)
    case = {
        "id": "A01",
        "question": "How many wins did Lewis Hamliton have?",
        "expected_intent": "statistics",
        "expected_corrections": [{"original": "Hamliton", "corrected": "hamilton"}],
        "expected_entities": [{"kind": "drivers", "id": 1}],
        "expected_tables": ["drivers", "results"],
        "gold_sql": "SELECT 105",
    }

    record = evaluate_case(
        service,
        case,
        gold_runner=lambda sql: {"rows": [[105]]},
    )

    assert record["answer_correct"] is True
    assert all(record["checks"].values())
    assert record["provider_call_count"] == 3
    assert record["repair_count"] == 1
    assert len(service.requests) == 1


def test_evaluate_case_requires_safe_clarification_without_sql():
    service = FakeService(
        {
            "intent": "clarify",
            "suggestions": ["Michael Schumacher", "Ralf Schumacher"],
            "trace": {"provider_call_count": 0, "repair_count": 0},
        }
    )
    case = {
        "id": "A02",
        "question": "How many wins did Schumacher have?",
        "expected_intent": "clarify",
        "expected_suggestions": ["Michael Schumacher", "Ralf Schumacher"],
    }

    record = evaluate_case(service, case, gold_runner=lambda sql: None)

    assert record["answer_correct"] is True
    assert record["checks"]["safe_non_execution"] is True
    assert record["checks"]["suggestions"] is True


def test_summary_reports_accuracy_calls_repairs_and_latency():
    summary = summarize(
        [
            {
                "answer_correct": True,
                "expected_intent": "statistics",
                "provider_call_count": 2,
                "repair_count": 0,
                "elapsed_ms": 100,
            },
            {
                "answer_correct": False,
                "expected_intent": "clarify",
                "provider_call_count": 0,
                "repair_count": 0,
                "elapsed_ms": 20,
            },
            {
                "answer_correct": True,
                "expected_intent": "statistics",
                "provider_call_count": 3,
                "repair_count": 1,
                "elapsed_ms": 180,
            },
        ]
    )

    assert summary == {
        "cases": 3,
        "answer_correct": 2,
        "statistics_correct": 2,
        "safe_non_statistics": 0,
        "provider_calls": 5,
        "provider_call_distribution": {"0": 1, "2": 1, "3": 1},
        "repairs": 1,
        "mean_latency_ms": 100.0,
    }


def test_run_benchmark_hashes_suite_writes_report_and_refuses_overwrite(tmp_path):
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "A03",
                    "question": "Is weather available?",
                    "expected_intent": "unsupported",
                }
            ]
        )
    )
    output = tmp_path / "report.json"
    service = FakeService(
        {
            "intent": "unsupported",
            "trace": {"provider_call_count": 0, "repair_count": 0},
        }
    )

    report = run_benchmark(
        output,
        cases_path=cases_path,
        service=service,
        gold_runner=lambda sql: None,
        git_commit="unit-test-sha",
        model="unit-test-model",
    )

    assert output.exists()
    assert report["suite_sha256"] == hashlib.sha256(cases_path.read_bytes()).hexdigest()
    assert report["git_commit"] == "unit-test-sha"
    assert report["summary"]["answer_correct"] == 1
    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        run_benchmark(output, cases_path=cases_path, service=service)
