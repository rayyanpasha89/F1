"""Retrieve entity labels from the database, never a hand-written F1 answer catalog."""

import re
import unicodedata
from difflib import SequenceMatcher


def normalize(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c)
    )


def entity_context(analytics, question):
    tokens = set(re.findall(r"[a-z0-9]{3,}", normalize(question))) - {
        "the",
        "and",
        "for",
        "race",
        "races",
        "driver",
        "drivers",
        "constructor",
        "constructors",
        "circuit",
        "circuits",
        "name",
        "names",
        "what",
        "which",
        "from",
        "with",
        "were",
        "was",
        "how",
        "many",
        "return",
        "full",
        "archive",
        "grand",
        "prix",
    }
    queries = {
        "drivers": "SELECT driver_id,driver_ref,forename || ' ' || surname AS name FROM drivers",
        "constructors": "SELECT constructor_id,constructor_ref,name FROM constructors",
        "circuits": "SELECT circuit_id,circuit_ref,name,country FROM circuits",
    }
    matches = {}
    for table, sql in queries.items():
        ranked = []
        for row in analytics.rows(sql):
            words = set(
                re.findall(r"[a-z0-9]{3,}", normalize(" ".join(str(v) for v in row.values())))
            )
            score = len(tokens & words)
            if score:
                ranked.append((score, row))
        ranked.sort(key=lambda pair: -pair[0])
        matches[table] = [row for _, row in ranked[:15]]
    return matches


def resolve_entities(analytics, question):
    """Conservative spelling repair against stored names, with explicit ambiguity."""
    catalog = {
        "drivers": analytics.rows(
            "SELECT driver_id,driver_ref,forename,surname,forename || ' ' || surname AS name FROM drivers"
        ),
        "constructors": analytics.rows(
            "SELECT constructor_id,constructor_ref,name FROM constructors"
        ),
        "circuits": analytics.rows("SELECT circuit_id,circuit_ref,name,country FROM circuits"),
    }
    aliases = {}
    for kind, rows in catalog.items():
        for row in rows:
            for key, value in row.items():
                if key.endswith("_id") or not isinstance(value, str):
                    continue
                for word in re.findall(r"[a-z]+", normalize(value)):
                    if len(word) >= 3:
                        aliases.setdefault(word, []).append((kind, row))
    # Ordinary question vocabulary must never be 'corrected' to a competitor's name.
    common = set(
        "archive sprint sprints records record earliest latest descending ascending display information statistics statistical podiums lookup countries country hosted having table database result elapsed seconds duration milliseconds laps stops timing round rounds grand prix average averages combined minimum maximum winning winner winners losing loser fastest comparison season championship which where when whose driver drivers constructor constructors circuit circuits race races racing season seasons points podium podiums position positions results history historical fastest slowest average total count compare comparison explain prediction predictions probability probabilities qualifying starting finished finish wins winning recent career scored performed performance during before after their there those these most least first second third last show return number many best worst about please against between championship standings".split()
    )
    corrections = []
    ambiguity = []
    replacements = {}
    for match in re.finditer(r"[^\W\d_]+", question, re.UNICODE):
        original = match.group()
        token = normalize(original)
        if len(token) < 5 or token in aliases or token in common:
            continue
        scores = sorted(
            (
                (SequenceMatcher(None, token, alias).ratio(), alias)
                for alias in aliases
                if abs(len(token) - len(alias)) <= 2 and len(alias) >= 5
            ),
            reverse=True,
        )
        if not scores or scores[0][0] < 0.82:
            continue
        best = scores[0][0]
        candidates = [alias for score, alias in scores if best - score < 0.055]
        question_words = set(re.findall(r"[a-z]+", normalize(question)))
        qualified = [
            alias
            for alias in candidates
            if any(
                kind == "drivers" and normalize(row.get("forename", "")) in question_words
                for kind, row in aliases[alias]
            )
        ]
        if qualified:
            candidates = qualified
        if len(candidates) != 1:
            ambiguity.extend(row["name"] for alias in candidates for _, row in aliases[alias])
            continue
        alias = candidates[0]
        replacements[(match.start(), match.end())] = alias
        corrections.append({"original": original, "corrected": alias})
    corrected = question
    for (start, end), value in sorted(replacements.items(), reverse=True):
        corrected = corrected[:start] + value + corrected[end:]
    context = entity_context(analytics, corrected)
    # A shared surname alone is not an identity (e.g. members of a racing family).
    words = set(re.findall(r"[a-z]+", normalize(corrected)))
    surname_groups = {}
    for row in catalog["drivers"]:
        surname = normalize(row["surname"])
        if surname in words:
            surname_groups.setdefault(surname, []).append(row)
    for rows in surname_groups.values():
        if len(rows) > 1 and not any(normalize(r["forename"]) in words for r in rows):
            ambiguity.extend(r["name"] for r in rows)
    return {
        "question": corrected,
        "corrections": corrections,
        "candidates": context,
        "ambiguity": sorted(set(ambiguity))[:10],
    }
