"""Deterministic retrieval context for the bounded F1 chat pipeline."""

import json
import re
from collections import deque
from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.ai.grounding import entity_catalog, normalize
from backend.database import ROOT, SCHEMA


EntityKind = Literal["drivers", "constructors", "circuits"]


class QueryVariant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["original", "corrected", "conversation", "selected_race"]
    text: str = Field(min_length=1, max_length=3200)


class RankedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EntityKind
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list, max_length=8)


class EntityRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: list[RankedEntity] = Field(default_factory=list, max_length=12)
    ranked: list[RankedEntity] = Field(default_factory=list, max_length=20)
    ambiguity: list[str] = Field(default_factory=list, max_length=10)


class SchemaRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tables: list[str] = Field(min_length=1, max_length=14)
    scores: dict[str, float]
    reasons: dict[str, list[str]]
    fallback: bool = False


FOLLOWUP = re.compile(
    r"\b(he|him|his|she|her|hers|it|its|they|them|their|theirs|that|those|"
    r"same|former|latter|compare|versus|vs|what about|and what)\b",
    re.IGNORECASE,
)


def augment_question(original, corrected, previous_question=None, race_id=None):
    """Return no more than four unique, labeled variants without altering inputs."""
    candidates = [("original", original.strip())]
    if corrected.strip() != original.strip():
        candidates.append(("corrected", corrected.strip()))
    current = corrected.strip() or original.strip()
    if previous_question and FOLLOWUP.search(current):
        candidates.append(
            (
                "conversation",
                f"{current}\nPrevious question context: {previous_question.strip()}",
            )
        )
    if race_id is not None:
        candidates.append(("selected_race", f"{current}\nSelected race ID: {race_id}"))
    variants = []
    seen = set()
    for source, text in candidates:
        if not text or text in seen:
            continue
        variants.append(QueryVariant(source=source, text=text))
        seen.add(text)
        if len(variants) == 4:
            break
    return variants


def _row_identity(kind, row):
    return int(row[f"{kind[:-1]}_id"])


def _aliases(kind, row):
    if kind == "drivers":
        return {
            "full_name": [row["name"]],
            "reference": [row.get("driver_ref", "").replace("_", " ")],
            "code": [row.get("code") or ""],
            "component": [row.get("forename", ""), row.get("surname", "")],
        }
    if kind == "constructors":
        return {
            "full_name": [row["name"]],
            "reference": [row.get("constructor_ref", "").replace("_", " ")],
            "component": [],
        }
    return {
        "full_name": [row["name"]],
        "reference": [row.get("circuit_ref", "").replace("_", " ")],
        "component": [row.get("country", "")],
    }


def _contains_phrase(text, phrase):
    phrase = normalize(phrase).strip()
    if not phrase:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _current_texts(variants):
    return [normalize(v.text) for v in variants if v.source in {"original", "corrected"}]


def _mention_position(texts, aliases):
    positions = []
    for text in texts:
        for values in aliases.values():
            for value in values:
                token = normalize(value).strip()
                if token and (position := text.find(token)) >= 0:
                    positions.append(position)
    return min(positions, default=10_000)


def _race_entities(analytics, race_id):
    if race_id is None:
        return set()
    rows = analytics.rows(
        """SELECT 'drivers' AS kind, d.driver_id AS entity_id
        FROM drivers d JOIN results x USING(driver_id) WHERE x.race_id=:race_id
        UNION
        SELECT 'constructors' AS kind, c.constructor_id AS entity_id
        FROM constructors c JOIN results x USING(constructor_id) WHERE x.race_id=:race_id
        UNION
        SELECT 'circuits' AS kind, c.circuit_id AS entity_id
        FROM circuits c JOIN races r USING(circuit_id) WHERE r.race_id=:race_id""",
        race_id=race_id,
    )
    return {(row["kind"], int(row["entity_id"])) for row in rows}


def rank_entities(analytics, variants, prior_entities=(), race_id=None):
    """Rank stored entity labels; leave close/shared identities for clarification."""
    catalog = entity_catalog(analytics)
    texts = _current_texts(variants)
    raw_texts = [v.text for v in variants if v.source in {"original", "corrected"}]
    words = set(re.findall(r"[a-z0-9]+", " ".join(texts)))
    followup = bool(FOLLOWUP.search(variants[0].text if variants else ""))
    race_entities = _race_entities(analytics, race_id)
    prior = {
        (
            item.kind if hasattr(item, "kind") else item.get("kind"),
            int(item.id if hasattr(item, "id") else item.get("id")),
        )
        for item in prior_entities
        if (hasattr(item, "kind") and hasattr(item, "id"))
        or (isinstance(item, dict) and item.get("kind") and item.get("id"))
    }
    scored = []
    ambiguous_names = set()
    excluded_names = set()
    surname_groups = {}
    for row in catalog["drivers"]:
        surname_groups.setdefault(normalize(row["surname"]), []).append(row)
    for surname, rows in surname_groups.items():
        if surname not in words or len(rows) < 2:
            continue
        named = [row for row in rows if normalize(row["forename"]) in words]
        if named:
            excluded_names.update(row["name"] for row in rows if row not in named)
        else:
            ambiguous_names.update(row["name"] for row in rows)
    generic_aliases = {
        "archive",
        "circuit",
        "circuits",
        "constructor",
        "constructors",
        "driver",
        "drivers",
        "race",
        "races",
        "team",
        "teams",
    }
    for kind, rows in catalog.items():
        for row in rows:
            entity_id = _row_identity(kind, row)
            aliases = _aliases(kind, row)
            score = 0.0
            reasons = []
            if any(
                _contains_phrase(text, value) for text in texts for value in aliases["full_name"]
            ):
                score = 1.0
                reasons.append("full_name")
            elif any(
                _contains_phrase(text, value)
                for text in texts
                for value in aliases.get("reference", [])
                if normalize(value) not in generic_aliases
            ):
                score = 0.92
                reasons.append("reference")
            elif any(
                re.search(rf"\b{re.escape(value)}\b", text) is not None
                for text in raw_texts
                for value in aliases.get("code", [])
                if len(value) >= 3 and value.isupper()
            ):
                score = 0.9
                reasons.append("code")
            else:
                components = [normalize(v) for v in aliases.get("component", []) if v]
                matched = [
                    value
                    for value in components
                    if value in words and len(value) >= 3 and value not in generic_aliases
                ]
                if matched:
                    is_driver_surname = (
                        kind == "drivers" and normalize(row.get("surname", "")) in matched
                    )
                    score = 0.84 if is_driver_surname or kind != "drivers" else 0.7
                    reasons.append("name_component")
                else:
                    searchable = [
                        normalize(value)
                        for values in aliases.values()
                        for value in values
                        if len(normalize(value)) >= 5
                    ]
                    similarity = max(
                        (
                            SequenceMatcher(None, word, alias).ratio()
                            for word in words
                            for alias in searchable
                            if abs(len(word) - len(alias)) <= 2
                        ),
                        default=0.0,
                    )
                    if similarity >= 0.84:
                        score = min(0.73, round(0.65 + (similarity - 0.84) * 0.5, 6))
                        reasons.append("edit_similarity")
            key = (kind, entity_id)
            if followup and key in prior:
                score = max(score, 0.88)
                reasons.append("prior_turn")
            if score and key in race_entities:
                score = min(1.0, score + 0.03)
                reasons.append("selected_race")
            if not score:
                continue
            scored.append(
                (
                    RankedEntity(
                        kind=kind,
                        id=entity_id,
                        name=row["name"],
                        score=round(score, 6),
                        reasons=list(dict.fromkeys(reasons)),
                    ),
                    _mention_position(texts, aliases),
                )
            )

    scored.sort(key=lambda pair: (-pair[0].score, pair[1], pair[0].kind, pair[0].name))
    ranked = [entity for entity, _ in scored[:20]]
    selected = [
        entity
        for entity in ranked
        if entity.score >= 0.74
        and entity.name not in ambiguous_names
        and entity.name not in excluded_names
    ][:12]
    return EntityRanking(
        selected=selected,
        ranked=ranked,
        ambiguity=sorted(ambiguous_names)[:10],
    )


SCHEMA_TERMS = {
    "drivers": {"driver", "drivers"},
    "constructors": {"constructor", "constructors", "team", "teams"},
    "circuits": {"circuit", "circuits", "track", "tracks", "country", "countries"},
    "races": {"race", "races", "season", "seasons", "year", "round", "date"},
    "seasons": {"season collection", "season range"},
    "results": {
        "win",
        "wins",
        "won",
        "winner",
        "winners",
        "podium",
        "podiums",
        "finish",
        "finished",
        "position",
        "points",
        "grid",
        "classified",
        "classification",
        "classifications",
    },
    "qualifying": {"qualifying", "qualification", "quali", "pole", "q1", "q2", "q3"},
    "constructor_results": {"constructor result", "team result"},
    "constructor_standings": {"constructor standing", "team standing"},
    "driver_standings": {"driver standing"},
    "lap_times": {"lap time", "lap times", "fastest lap"},
    "pit_stops": {"pit stop", "pit stops", "pitstop", "pitstops"},
    "sprint_results": {"sprint", "sprints"},
    "status": {"status", "dnf", "retired", "retirement", "finished"},
}


def _relationship_graph(relationships):
    graph = {name: set() for name in SCHEMA}
    for relation in relationships:
        left = relation.get("table")
        right = str(relation.get("references", "")).split(".", 1)[0]
        if left in graph and right in graph:
            graph[left].add(right)
            graph[right].add(left)
    return graph


def _shortest_path(graph, start, targets, scores):
    queue = deque([(start, [start])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        if node in targets:
            return path
        for neighbor in sorted(
            graph[node],
            key=lambda name: (
                -scores.get(name, 0),
                0 if name == "results" else 1,
                name,
            ),
        ):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return []


def rank_schema(question, entities=(), router_hints=(), relationships=None):
    """Score known tables and add the shortest stored relationship paths."""
    relationships = relationships or json.loads((ROOT / "knowledge/relationships.json").read_text())
    text = normalize(question)
    words = set(re.findall(r"[a-z0-9]+", text))
    scores = {name: 0.0 for name in SCHEMA}
    reasons = {name: [] for name in SCHEMA}

    def add(table, amount, reason):
        if table not in SCHEMA:
            return
        scores[table] += amount
        if reason not in reasons[table]:
            reasons[table].append(reason)

    for table, terms in SCHEMA_TERMS.items():
        for term in terms:
            matched = _contains_phrase(text, term) if " " in term else term in words
            if matched:
                if table == "races" and term in {"season", "seasons", "year"}:
                    reason = "season_term"
                elif table == "races":
                    reason = "race_term"
                else:
                    reason = "intent_term"
                add(table, 2.0, reason)
                break

    # Resolve standings and lap/pit phrases more precisely than column-name overlap.
    if words & {"championship", "standings", "standing"}:
        if words & {"constructor", "constructors", "team", "teams"}:
            add("constructor_standings", 3.0, "standings_intent")
        else:
            add("driver_standings", 3.0, "standings_intent")
        add("races", 1.0, "standings_snapshot")
    if re.search(r"\b(?:19|20)\d{2}\b", text):
        add("races", 2.0, "year_literal")
    if (words & {"season", "seasons"}) and (
        words
        & {
            "archive",
            "bookend",
            "bookends",
            "boundary",
            "boundaries",
            "collection",
            "earliest",
            "latest",
            "maximum",
            "minimum",
            "range",
        }
    ):
        add("seasons", 3.0, "season_boundary_intent")
    if "grand prix" in text or "grands prix" in text or "calendar" in words:
        add("races", 2.0, "race_term")
    if "chequered flag" in text or "checkered flag" in text:
        add("results", 3.0, "finish_intent")
    if any(
        phrase in text
        for phrase in ["race for", "raced for", "drive for", "drove for", "competed for"]
    ):
        add("results", 3.0, "driver_constructor_association")
    if ("pit" in words and ("stop" in words or "stops" in words)) or words & {
        "pitstop",
        "pitstops",
    }:
        add("pit_stops", 3.0, "pit_stop_intent")
    if "lap" in words or "laps" in words:
        add("lap_times", 2.5, "lap_intent")
    if words & {"dnf", "retired", "retirement"}:
        add("results", 1.5, "classification_intent")

    for entity in entities:
        kind = entity.kind if hasattr(entity, "kind") else entity.get("kind")
        table = kind if kind in {"drivers", "constructors", "circuits"} else None
        if table:
            add(table, 3.0, "entity_kind")
    has_deterministic_evidence = any(score > 0 for score in scores.values())
    for table in router_hints:
        if table in SCHEMA:
            if scores[table] > 0:
                add(table, 0.5, "router_hint")
            elif not has_deterministic_evidence:
                add(table, 2.0, "router_hint")

    active = [name for name, score in scores.items() if score > 0]
    if not active:
        return SchemaRanking(
            tables=list(SCHEMA),
            scores={name: 0.0 for name in SCHEMA},
            reasons={name: ["complete_schema_fallback"] for name in SCHEMA},
            fallback=True,
        )

    seeds = sorted(active, key=lambda name: (-scores[name], name))[:5]
    graph = _relationship_graph(relationships)
    connected = {seeds[0]}
    ordered = [seeds[0]]
    for seed in seeds[1:]:
        path = _shortest_path(graph, seed, connected, scores)
        if not path:
            path = [seed]
        for table in path:
            if table not in ordered:
                ordered.append(table)
            if len(path) > 1 and "relationship_path" not in reasons[table]:
                reasons[table].append("relationship_path")
        connected.update(path)

    # Keep direct evidence not included in a disconnected path, within a compact prompt budget.
    for seed in seeds:
        if seed not in ordered:
            ordered.append(seed)
    ordered = ordered[:7]
    return SchemaRanking(
        tables=ordered,
        scores={name: round(scores[name], 3) for name in ordered},
        reasons={name: reasons[name] for name in ordered},
    )
