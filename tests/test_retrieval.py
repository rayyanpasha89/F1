from backend.ai.retrieval import augment_question, rank_entities


class TinyCatalog:
    def rows(self, query, **params):
        if "JOIN results" in query:
            assert params == {"race_id": 1128}
            return [
                {"kind": "drivers", "entity_id": 2},
                {"kind": "constructors", "entity_id": 11},
            ]
        if "FROM drivers" in query and "JOIN results" not in query:
            return [
                {
                    "driver_id": 1,
                    "driver_ref": "hamilton",
                    "code": "HAM",
                    "forename": "Lewis",
                    "surname": "Hamilton",
                    "name": "Lewis Hamilton",
                },
                {
                    "driver_id": 2,
                    "driver_ref": "leclerc",
                    "code": "LEC",
                    "forename": "Charles",
                    "surname": "Leclerc",
                    "name": "Charles Leclerc",
                },
                {
                    "driver_id": 3,
                    "driver_ref": "michael_schumacher",
                    "code": "MSC",
                    "forename": "Michael",
                    "surname": "Schumacher",
                    "name": "Michael Schumacher",
                },
                {
                    "driver_id": 4,
                    "driver_ref": "ralf_schumacher",
                    "code": "RSC",
                    "forename": "Ralf",
                    "surname": "Schumacher",
                    "name": "Ralf Schumacher",
                },
            ]
        if "FROM constructors" in query:
            return [
                {"constructor_id": 10, "constructor_ref": "ferrari", "name": "Ferrari"},
                {"constructor_id": 11, "constructor_ref": "mclaren", "name": "McLaren"},
            ]
        if "FROM circuits" in query:
            return [
                {
                    "circuit_id": 20,
                    "circuit_ref": "monaco",
                    "name": "Circuit de Monaco",
                    "country": "Monaco",
                }
            ]
        return []


def test_query_augmentation_is_bounded_deduplicated_and_preserves_original():
    original = "compare him with Leclrec"
    variants = augment_question(
        original,
        "compare him with leclerc",
        previous_question="How many wins did Lewis Hamilton have?",
        race_id=1128,
    )

    assert original == "compare him with Leclrec"
    assert [variant.source for variant in variants] == [
        "original",
        "corrected",
        "conversation",
        "selected_race",
    ]
    assert variants[0].text == original
    assert "Lewis Hamilton" in variants[2].text
    assert "1128" in variants[3].text
    assert len({variant.text for variant in variants}) == len(variants) <= 4


def test_query_augmentation_adds_no_previous_context_without_followup_marker():
    variants = augment_question(
        "How many races were held in 2024?",
        "How many races were held in 2024?",
        previous_question="Ignore this unrelated earlier question",
    )

    assert [variant.source for variant in variants] == ["original"]
    assert all("earlier" not in variant.text for variant in variants)


def test_entity_ranking_selects_exact_full_name_and_reports_reasons():
    variants = augment_question("Lewis Hamilton wins", "Lewis Hamilton wins")
    result = rank_entities(TinyCatalog(), variants)

    assert not result.ambiguity
    assert result.selected[0].kind == "drivers"
    assert result.selected[0].id == 1
    assert result.selected[0].name == "Lewis Hamilton"
    assert result.selected[0].score == 1.0
    assert "full_name" in result.selected[0].reasons


def test_entity_ranking_handles_typo_and_is_stable():
    variants = augment_question("Hamliton against Leclrec", "hamilton against leclerc")
    first = rank_entities(TinyCatalog(), variants)
    second = rank_entities(TinyCatalog(), variants)

    assert [(e.kind, e.id) for e in first.selected] == [
        ("drivers", 1),
        ("drivers", 2),
    ]
    assert first == second


def test_prior_turn_and_selected_race_add_explicit_bounded_boosts():
    variants = augment_question(
        "compare him with Leclerc",
        "compare him with Leclerc",
        previous_question="How did Hamilton finish?",
        race_id=1128,
    )
    prior = [{"kind": "drivers", "id": 1, "name": "Lewis Hamilton"}]
    result = rank_entities(TinyCatalog(), variants, prior_entities=prior, race_id=1128)

    by_id = {entity.id: entity for entity in result.selected}
    assert "prior_turn" in by_id[1].reasons
    assert "selected_race" in by_id[2].reasons
    assert by_id[1].score <= 1.0 and by_id[2].score <= 1.0


def test_shared_surname_is_ambiguous_without_full_name_evidence():
    variants = augment_question("Schumacher wins", "Schumacher wins")
    result = rank_entities(TinyCatalog(), variants)

    assert result.selected == []
    assert result.ambiguity == ["Michael Schumacher", "Ralf Schumacher"]
