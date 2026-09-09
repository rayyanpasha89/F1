import pytest

from backend.ai.grounding import resolve_entities


class Catalog:
    def rows(self, query):
        if "FROM drivers" in query:
            return [
                {
                    "driver_id": 1,
                    "driver_ref": "hamilton",
                    "forename": "Lewis",
                    "surname": "Hamilton",
                    "name": "Lewis Hamilton",
                },
                {
                    "driver_id": 2,
                    "driver_ref": "leclerc",
                    "forename": "Charles",
                    "surname": "Leclerc",
                    "name": "Charles Leclerc",
                },
                {
                    "driver_id": 3,
                    "driver_ref": "leclere",
                    "forename": "Michel",
                    "surname": "Leclère",
                    "name": "Michel Leclère",
                },
                {
                    "driver_id": 4,
                    "driver_ref": "michael_schumacher",
                    "forename": "Michael",
                    "surname": "Schumacher",
                    "name": "Michael Schumacher",
                },
                {
                    "driver_id": 5,
                    "driver_ref": "ralf_schumacher",
                    "forename": "Ralf",
                    "surname": "Schumacher",
                    "name": "Ralf Schumacher",
                },
            ]
        if "FROM constructors" in query:
            return [{"constructor_id": 6, "constructor_ref": "ferrari", "name": "Ferrari"}]
        return [{"circuit_id": 7, "circuit_ref": "monaco", "name": "Circuit de Monaco"}]


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Lewis Hamliton wins", "Lewis hamilton wins"),
        ("Charles Leclrec at Moncao", "Charles leclerc at monaco"),
        ("Michael Schumcher for Ferarri", "Michael schumacher for ferrari"),
    ],
)
def test_spelling_uses_catalog_and_context(question, expected):
    result = resolve_entities(Catalog(), question)
    assert result["question"] == expected
    assert not result["ambiguity"]
    assert result["corrections"]


def test_shared_surname_and_similar_names_require_clarification():
    assert resolve_entities(Catalog(), "Schumacher wins")["ambiguity"] == [
        "Michael Schumacher",
        "Ralf Schumacher",
    ]
    assert resolve_entities(Catalog(), "Leclrec wins")["ambiguity"] == [
        "Charles Leclerc",
        "Michel Leclère",
    ]


def test_unknown_name_and_common_vocabulary_are_not_rewritten():
    question = "Compare average qualifying positions during recent seasons for Zzxqv"
    result = resolve_entities(Catalog(), question)
    assert result["question"] == question
    assert not result["corrections"]


def test_accents_and_correct_names_stay_unchanged():
    result = resolve_entities(Catalog(), "Michel Leclère at Monaco")
    assert not result["corrections"]
    assert not result["ambiguity"]


def test_ambiguous_identity_does_not_call_llm_or_execute_sql():
    from backend.ai.chat import ChatService, ChatRequest
    from backend.database import make_engine

    service = ChatService(make_engine("sqlite:///:memory:"))
    service.analytics = Catalog()
    result = service.answer(ChatRequest(question="How many wins for Schumacher?"))
    assert result["intent"] == "clarify"
    assert service.client is None
    assert "sql" not in result


def test_explanation_targets_named_driver_instead_of_leading_probability():
    from backend.ai.chat import ChatService, ChatRequest, Intent
    from backend.database import make_engine

    class Provider:
        def structured(self, *args):
            return Intent(intent="explanation"), {}

    class Predictor:
        def predict(self, race_id):
            return {
                "predictions": [
                    {
                        "driver_id": 2,
                        "probability": 0.8,
                        "baseline_probability": 0.7,
                        "factors": [],
                    },
                    {
                        "driver_id": 1,
                        "probability": 0.4,
                        "baseline_probability": 0.3,
                        "factors": [
                            {"feature": "grid_position", "log_odds_contribution": 0.25},
                            {"feature": "driver_recent_podium", "log_odds_contribution": -0.1},
                        ],
                    },
                ]
            }

    class RaceCatalog(Catalog):
        def race_table(self, *args):
            return [
                {"driver_id": 1, "driver_name": "Lewis Hamilton"},
                {"driver_id": 2, "driver_name": "Charles Leclerc"},
            ]

    service = ChatService(make_engine("sqlite:///:memory:"), Provider())
    service.analytics = RaceCatalog()
    service.predictor = Predictor()
    result = service.answer(
        ChatRequest(question="Why is Lewis Hamliton predicted there?", race_id=1)
    )
    assert result["explained_driver_id"] == 1
    assert "40.0%" in result["answer"]
    assert "+0.250" in result["answer"] and "-0.100" in result["answer"]
