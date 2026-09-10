"""Deterministic retrieval context for the bounded F1 chat pipeline."""

import re
from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.ai.grounding import entity_catalog, normalize


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
    surname_hits = {}
    for kind, rows in catalog.items():
        for row in rows:
            entity_id = _row_identity(kind, row)
            aliases = _aliases(kind, row)
            score = 0.0
            reasons = []
            if any(_contains_phrase(text, value) for text in texts for value in aliases["full_name"]):
                score = 1.0
                reasons.append("full_name")
            elif any(
                _contains_phrase(text, value)
                for text in texts
                for value in aliases.get("reference", [])
            ):
                score = 0.92
                reasons.append("reference")
            elif any(
                _contains_phrase(text, value)
                for text in texts
                for value in aliases.get("code", [])
                if len(value) >= 3
            ):
                score = 0.9
                reasons.append("code")
            else:
                components = [normalize(v) for v in aliases.get("component", []) if v]
                matched = [value for value in components if value in words and len(value) >= 3]
                if matched:
                    score = 0.84
                    reasons.append("name_component")
                    if kind == "drivers" and normalize(row.get("surname", "")) in matched:
                        surname_hits.setdefault(normalize(row["surname"]), []).append(row)
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
                        score = round(0.72 + (similarity - 0.84) * 0.75, 6)
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

    ambiguous_names = set()
    for surname, rows in surname_hits.items():
        if len(rows) < 2:
            continue
        for row in rows:
            if not any(normalize(row.get("forename", "")) in words for _ in [0]):
                ambiguous_names.add(row["name"])
    scored.sort(key=lambda pair: (-pair[0].score, pair[1], pair[0].kind, pair[0].name))
    ranked = [entity for entity, _ in scored[:20]]
    selected = [
        entity
        for entity in ranked
        if entity.score >= 0.74 and entity.name not in ambiguous_names
    ][:12]
    return EntityRanking(
        selected=selected,
        ranked=ranked,
        ambiguity=sorted(ambiguous_names)[:10],
    )
