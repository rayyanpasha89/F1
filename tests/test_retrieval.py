from backend.ai.retrieval import augment_question, rank_entities, rank_schema


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
                {
                    "driver_id": 5,
                    "driver_ref": "pic",
                    "code": "PIC",
                    "forename": "Charles",
                    "surname": "Pic",
                    "name": "Charles Pic",
                },
                {
                    "driver_id": 6,
                    "driver_ref": "driver",
                    "code": None,
                    "forename": "Paddy",
                    "surname": "Driver",
                    "name": "Paddy Driver",
                },
                {
                    "driver_id": 7,
                    "driver_ref": "winkelhock",
                    "code": "WIN",
                    "forename": "Markus",
                    "surname": "Winkelhock",
                    "name": "Markus Winkelhock",
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


def test_full_name_evidence_excludes_relatives_and_shared_forenames():
    result = rank_entities(
        TinyCatalog(),
        augment_question(
            "Compare Michael Schumacher and Charles Leclerc",
            "Compare Michael Schumacher and Charles Leclerc",
        ),
    )

    assert [(entity.id, entity.name) for entity in result.selected] == [
        (3, "Michael Schumacher"),
        (2, "Charles Leclerc"),
    ]


def test_generic_words_and_lowercase_words_matching_codes_select_no_driver():
    result = rank_entities(
        TinyCatalog(),
        augment_question(
            "Which driver has the most wins in this archive?",
            "Which driver has the most wins in this archive?",
        ),
    )

    assert result.selected == []


def test_schema_ranking_selects_driver_results_and_season_relationships():
    result = rank_schema(
        "How many races did Lewis Hamilton win in the 2020 season?",
        entities=[{"kind": "drivers", "id": 1, "name": "Lewis Hamilton"}],
        router_hints=["drivers", "results", "made_up_table"],
    )

    assert {"drivers", "results", "races"} <= set(result.tables)
    assert "made_up_table" not in result.tables
    assert result.scores["results"] > result.scores.get("qualifying", 0)
    assert (
        "relationship_path" in result.reasons["races"] or "season_term" in result.reasons["races"]
    )


def test_schema_ranking_closes_shortest_paths_for_pit_stop_comparison():
    result = rank_schema(
        "Compare Hamilton and Leclerc pit stop time at the selected race",
        entities=[
            {"kind": "drivers", "id": 1, "name": "Lewis Hamilton"},
            {"kind": "drivers", "id": 2, "name": "Charles Leclerc"},
        ],
    )

    assert {"pit_stops", "drivers", "races"} <= set(result.tables)
    assert len(result.tables) <= 7
    assert "relationship_path" in result.reasons["races"]


def test_schema_ranking_uses_constructor_and_standings_intent():
    result = rank_schema(
        "Which constructor led the championship standings in 2023?",
        entities=[{"kind": "constructors", "id": 10, "name": "Ferrari"}],
    )

    assert {"constructors", "constructor_standings", "races"} <= set(result.tables)


def test_schema_ranking_falls_back_to_complete_known_schema():
    result = rank_schema("Tell me something interesting")

    assert len(result.tables) == 14
    assert result.fallback is True


def test_schema_ranking_recognizes_numeric_years_and_season_boundaries():
    dated = rank_schema("Count the Grands Prix on the 2023 calendar")
    boundaries = rank_schema("What years bookend the historical season collection?")

    assert "races" in dated.tables
    assert "seasons" in boundaries.tables


def test_driver_constructor_association_prefers_results_over_standings_summaries():
    result = rank_schema(
        "Which constructors did Fernando Alonso race for in 2023?",
        entities=[{"kind": "drivers", "id": 4, "name": "Fernando Alonso"}],
        router_hints=[
            "drivers",
            "driver_standings",
            "races",
            "constructor_results",
            "constructors",
            "results",
        ],
    )

    assert {"drivers", "results", "constructors", "races"} <= set(result.tables)
    assert "driver_standings" not in result.tables
    assert "constructor_results" not in result.tables
