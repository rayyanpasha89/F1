import json
import httpx
import pytest
from backend.ai.chat import ChatService, ChatRequest, Intent, SQLPlan
from backend.ai.provider import BedrockClient, ProviderError
from backend.config import BedrockSettings
from backend.database import make_engine


class ScriptedProvider:
    """Test double only; never used by application or live benchmark."""

    def __init__(self, sql):
        self.sql = sql

    def structured(self, system, user, schema):
        if schema is Intent:
            return Intent(intent="statistics", tables=["races"]), {}
        return SQLPlan(sql=self.sql), {}


@pytest.mark.parametrize(
    "question", ["Who wins Monaco in wet races?", "Delete all races", "Who won in 2025?"]
)
def test_unsupported_does_not_call_provider(question):
    service = ChatService(make_engine("sqlite:///:memory:"))
    assert service.answer(ChatRequest(question=question))["intent"] == "unsupported"
    assert service.client is None


def test_statistics_answer_comes_from_executed_rows(tmp_path):
    import sqlite3

    path = tmp_path / "f1.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE races(race_id INTEGER,year INTEGER)")
        conn.executemany("INSERT INTO races VALUES(?,2024)", [(1,), (2,)])
    service = ChatService(
        make_engine(f"sqlite:///{path}"), ScriptedProvider("SELECT COUNT(*) AS races FROM races")
    )
    result = service.answer(ChatRequest(question="How many races?"))
    assert result["result"]["rows"] == [[2]]
    assert result["answer"] == "races: 2"
    service.client = ScriptedProvider("DELETE FROM races")
    assert service.answer(ChatRequest(question="How many races?"))["status"] == "query_rejected"


def test_transport_headers_and_schema():
    def handler(request):
        assert request.url.host == "bedrock-mantle.eu-north-1.api.aws"
        assert request.headers["Authorization"] == "Bearer unit-test-only"
        assert json.loads(request.content)["model"] == "openai.gpt-oss-120b"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"intent":"statistics","tables":["races"]}'},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    settings = BedrockSettings(
        "unit-test-only", "https://bedrock-mantle.eu-north-1.api.aws/v1", "openai.gpt-oss-120b"
    )
    result, _ = BedrockClient(settings, httpx.MockTransport(handler)).structured(
        "route", "question", Intent
    )
    assert result.intent == "statistics"
    assert "unit-test-only" not in repr(settings)


def test_transport_failure_does_not_expose_response_secrets():
    settings = BedrockSettings(
        "unit-test-only", "https://bedrock-mantle.eu-north-1.api.aws/v1", "openai.gpt-oss-120b"
    )
    client = BedrockClient(
        settings, httpx.MockTransport(lambda request: httpx.Response(401, text="sensitive body"))
    )
    with pytest.raises(ProviderError, match="HTTP 401") as error:
        client.structured("route", "question", Intent)
    assert "sensitive" not in str(error.value)


def test_entity_grounding_comes_from_database_labels():
    from backend.ai.grounding import entity_context

    class TinyAnalytics:
        def rows(self, sql):
            if "FROM circuits" in sql:
                return [
                    {
                        "circuit_id": 99,
                        "circuit_ref": "monaco",
                        "name": "A changed Monaco label",
                        "country": "Monaco",
                    }
                ]
            return []

    context = entity_context(TinyAnalytics(), "What is the Monaco circuit called?")
    assert context["circuits"][0]["name"] == "A changed Monaco label"
