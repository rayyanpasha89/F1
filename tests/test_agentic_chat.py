import json
import sqlite3

import pytest
from pydantic import ValidationError

from backend.ai.chat import (
    ChatRequest,
    ChatService,
    ConversationEntity,
    ConversationTurn,
    Intent,
    ProviderCallBudget,
    SQLPlan,
)
from backend.ai.provider import ProviderError
from backend.database import make_engine


def tiny_database(tmp_path):
    path = tmp_path / "agentic.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE drivers(
                driver_id INTEGER, driver_ref TEXT, code TEXT,
                forename TEXT, surname TEXT
            );
            CREATE TABLE constructors(
                constructor_id INTEGER, constructor_ref TEXT, name TEXT
            );
            CREATE TABLE circuits(
                circuit_id INTEGER, circuit_ref TEXT, name TEXT, country TEXT
            );
            CREATE TABLE races(race_id INTEGER, year INTEGER, circuit_id INTEGER);
            CREATE TABLE results(
                result_id INTEGER, race_id INTEGER, driver_id INTEGER, constructor_id INTEGER
            );
            INSERT INTO drivers VALUES(1, 'hamilton', 'HAM', 'Lewis', 'Hamilton');
            INSERT INTO drivers VALUES(2, 'leclerc', 'LEC', 'Charles', 'Leclerc');
            INSERT INTO constructors VALUES(10, 'ferrari', 'Ferrari');
            INSERT INTO circuits VALUES(20, 'monaco', 'Circuit de Monaco', 'Monaco');
            INSERT INTO races VALUES(1128, 2024, 20);
            INSERT INTO results VALUES(1, 1128, 1, 10);
            INSERT INTO results VALUES(2, 1128, 2, 10);
            """
        )
    return path


class CapturingProvider:
    def __init__(self, sql="SELECT COUNT(*) AS races FROM races"):
        self.sql = sql
        self.calls = []

    def structured(self, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        meta = {"model": "test-model", "elapsed_ms": 12.5, "usage": {"total_tokens": 10}}
        if schema is Intent:
            return Intent(intent="statistics", tables=["drivers", "results", "races"]), meta
        return SQLPlan(sql=self.sql), meta


def test_conversation_models_are_strict_and_bounded():
    entity = ConversationEntity(kind="drivers", id=1, name="Lewis Hamilton")
    turn = ConversationTurn(
        question="How many wins?", intent="statistics", entities=[entity], race_id=1128
    )
    request = ChatRequest(question="And podiums?", conversation=[turn, turn, turn])
    assert len(request.conversation) == 3
    assert request.previous_question is None

    with pytest.raises(ValidationError):
        ChatRequest(question="And podiums?", conversation=[turn, turn, turn, turn])
    with pytest.raises(ValidationError):
        ConversationEntity(kind="teams", id=1, name="Ferrari")
    with pytest.raises(ValidationError):
        ConversationTurn(
            question="Valid question", intent="statistics", entities=[], sql="SELECT 1"
        )


def test_router_receives_only_bounded_retrieval_and_conversation_context(tmp_path):
    path = tiny_database(tmp_path)
    provider = CapturingProvider()
    service = ChatService(make_engine(f"sqlite:///{path}"), provider)
    prior = ConversationTurn(
        question="How many wins did Lewis Hamilton have?",
        intent="statistics",
        entities=[ConversationEntity(kind="drivers", id=1, name="Lewis Hamilton")],
        race_id=1128,
    )

    result = service.answer(
        ChatRequest(
            question="How many did he win there?",
            race_id=1128,
            previous_question="legacy value should not win",
            conversation=[prior],
        )
    )

    context = json.loads(provider.calls[0]["user"])
    assert context["question"] == "How many did he win there?"
    assert context["selected_race_id"] == 1128
    assert len(context["conversation"]) == 1
    assert context["conversation"][0] == prior.model_dump()
    assert context["entities"][0]["name"] == "Lewis Hamilton"
    assert any("Previous question context" in variant for variant in context["variants"])
    serialized = json.dumps(context)
    assert "legacy value should not win" not in serialized
    assert "SELECT" not in serialized and "result_rows" not in serialized
    assert result["status"] == "executed"


def test_every_route_has_an_allowlisted_trace_and_early_routes_use_zero_calls(tmp_path):
    unsupported = ChatService(make_engine("sqlite:///:memory:")).answer(
        ChatRequest(question="Who won Monaco in wet weather?")
    )
    assert unsupported["trace"]["route"] == "unsupported"
    assert unsupported["trace"]["provider_call_count"] == 0
    assert unsupported["trace"]["attempts"] == []

    path = tiny_database(tmp_path)
    provider = CapturingProvider()
    executed = ChatService(make_engine(f"sqlite:///{path}"), provider).answer(
        ChatRequest(question="How many races?")
    )
    trace = executed["trace"]
    assert trace["original_question"] == "How many races?"
    assert trace["interpreted_question"] == "How many races?"
    assert trace["route"] == "statistics"
    assert trace["tables"]
    assert trace["attempts"] == [{"number": 1, "outcome": "executed", "failure_category": None}]
    assert trace["provider_call_count"] == 2
    assert trace["provider_elapsed_ms"] == 25.0
    assert trace["total_elapsed_ms"] >= 0


def test_trace_does_not_copy_provider_or_infrastructure_secrets(tmp_path):
    path = tiny_database(tmp_path)
    provider = CapturingProvider()
    provider_secret = "provider-body-SENTINEL"
    provider.structured = lambda system, user, schema: (
        (
            Intent(intent="statistics", tables=["races"])
            if schema is Intent
            else SQLPlan(sql="SELECT COUNT(*) AS races FROM races")
        ),
        {
            "model": "test-model",
            "elapsed_ms": 1,
            "usage": {"secret": provider_secret},
            "database_url": "postgresql://secret-SENTINEL",
        },
    )
    result = ChatService(make_engine(f"sqlite:///{path}"), provider).answer(
        ChatRequest(question="How many races?")
    )

    trace = json.dumps(result["trace"])
    assert provider_secret not in trace
    assert "postgresql://" not in trace
    assert "system" not in trace and "prompt" not in trace


def test_provider_call_budget_refuses_a_fourth_call():
    provider = CapturingProvider()
    budget = ProviderCallBudget(provider, max_calls=3)
    for _ in range(3):
        budget.structured("system", "user", Intent)
    with pytest.raises(ProviderError, match="call limit"):
        budget.structured("system", "user", Intent)
    assert budget.count == 3
