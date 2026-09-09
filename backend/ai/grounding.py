"""Retrieve entity labels from the database, never a hand-written F1 answer catalog."""

import re
import unicodedata


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
