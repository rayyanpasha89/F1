"""Black-box verification for an immutable public F1 release."""

import argparse
import gzip
import json
import math
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


SCHEMA_VERSION = "f1-public-release-verification-v1"
MODEL_VERSION_PATTERN = re.compile(r"^EXP-[0-9]{3}\+podium-count-v1$")
REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HASHED_ASSET_PATTERN = re.compile(r"^/assets/.+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$")
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
CHAT_QUESTION = "Total 2024 podium finishes for Max Verstapen?"
KNOWN_TABLES = {
    "circuits",
    "constructor_results",
    "constructor_standings",
    "constructors",
    "driver_standings",
    "drivers",
    "lap_times",
    "pit_stops",
    "qualifying",
    "races",
    "results",
    "seasons",
    "sprint_results",
    "status",
}
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
}
CSP_DIRECTIVES = (
    "default-src 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "connect-src 'self'",
    "base-uri 'self'",
)


class VerificationError(RuntimeError):
    """A public response failed an allowlisted release assertion."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(condition, code):
    if not condition:
        raise VerificationError(code)


def _mapping(value, code):
    _require(isinstance(value, dict), code)
    return value


def _sequence(value, code):
    _require(isinstance(value, list), code)
    return value


def _number(value, code):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), code)
    _require(math.isfinite(value), code)
    return float(value)


def _integer(value, code):
    _require(isinstance(value, int) and not isinstance(value, bool), code)
    return value


class _DocumentMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_parts = []
        self.description = None
        self.assets = []

    @property
    def title(self):
        return "".join(self.title_parts).strip()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content")
        if tag == "script" and values.get("src"):
            self.assets.append(values["src"])
        if tag == "link" and values.get("href"):
            self.assets.append(values["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)


class _Verifier:
    def __init__(self, base_url: str, timeout: float):
        parsed = urlsplit(base_url)
        _require(parsed.scheme in {"http", "https"}, "base_url_scheme")
        _require(bool(parsed.hostname), "base_url_host")
        _require(not parsed.username and not parsed.password, "base_url_credentials")
        _require(not parsed.query and not parsed.fragment, "base_url_suffix")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_ids = []
        self.gzip_responses = 0
        self.response_count = 0

    def _request(self, path, *, cache, data=None, headers=None):
        request_headers = {
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Encoding": "gzip",
            "User-Agent": "f1-release-verifier/1",
            "X-Request-ID": "verifier-untrusted",
        }
        request_headers.update(headers or {})
        request = Request(self.base_url + path, data=data, headers=request_headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = response.status
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            raise VerificationError(f"http_status_{error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise VerificationError("network_request") from None

        _require(status == 200, "http_status")
        _require(len(raw) <= MAX_RESPONSE_BYTES, "response_size")
        self._assert_delivery(response_headers, cache)
        if response_headers.get("content-encoding", "").lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except (gzip.BadGzipFile, EOFError, OSError):
                raise VerificationError("gzip_body") from None
            _require(len(raw) <= MAX_RESPONSE_BYTES, "response_size")
            self.gzip_responses += 1
        self.response_count += 1
        return raw, response_headers

    def _assert_delivery(self, headers, cache):
        request_id = headers.get("x-request-id", "")
        _require(bool(REQUEST_ID_PATTERN.fullmatch(request_id)), "request_id")
        _require(request_id != "verifier-untrusted", "request_id_reflection")
        _require(request_id not in self.request_ids, "request_id_reuse")
        self.request_ids.append(request_id)
        for name, expected in SECURITY_HEADERS.items():
            _require(headers.get(name) == expected, f"security_header_{name}")
        csp = headers.get("content-security-policy", "")
        _require(all(directive in csp for directive in CSP_DIRECTIVES), "security_header_csp")
        _require(headers.get("cache-control") == cache, "cache_control")

    def json(self, path, *, cache="public, max-age=300", data=None, headers=None):
        raw, response_headers = self._request(path, cache=cache, data=data, headers=headers)
        _require("application/json" in response_headers.get("content-type", ""), "json_type")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise VerificationError("json_body") from None
        return _mapping(value, "json_object")

    def html(self, path):
        raw, response_headers = self._request(path, cache="no-cache")
        _require("text/html" in response_headers.get("content-type", ""), "html_type")
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise VerificationError("html_body") from None
        metadata = _DocumentMetadata()
        metadata.feed(html)
        _require(
            metadata.title == "F1 Race Strategist | Historical Analytics",
            "html_title",
        )
        _require(
            isinstance(metadata.description, str) and 50 <= len(metadata.description) <= 160,
            "html_description",
        )
        return metadata


def _verify_readiness(verifier):
    payload = verifier.json("/api/health/ready", cache="no-store")
    checks = _mapping(payload.get("checks"), "readiness_checks")
    _require(payload.get("status") == "ready", "readiness_status")
    _require(payload.get("archive_through") == 2024, "readiness_archive")
    version = payload.get("model_version")
    _require(isinstance(version, str) and MODEL_VERSION_PATTERN.fullmatch(version), "model_version")
    _require(
        checks == {"database": "ok", "model_bundle": "verified", "model_card": "verified"},
        "readiness_checks",
    )
    return {
        "status": "passed",
        "archive_through": 2024,
        "model_version": version,
        "database": "ok",
        "model_bundle": "verified",
        "model_card": "verified",
    }


def _verify_archive(verifier):
    seasons = _sequence(verifier.json("/api/seasons").get("data"), "season_rows")
    years = [_integer(_mapping(row, "season_row").get("year"), "season_year") for row in seasons]
    _require(years == list(range(2024, 1949, -1)), "season_coverage")
    races = _sequence(verifier.json("/api/races?year=2024").get("data"), "race_rows")
    _require(len(races) == 24, "race_count")
    parsed_races = [_mapping(race, "race_row") for race in races]
    _require(
        len({_integer(row.get("race_id"), "race_id") for row in parsed_races}) == 24, "race_ids"
    )
    selected = next((row for row in parsed_races if row.get("name") == "Monaco Grand Prix"), None)
    _require(selected is not None, "monaco_race")
    race_id = _integer(selected.get("race_id"), "race_id")
    identity = verifier.json(f"/api/races/{race_id}")
    _require(identity.get("race_id") == race_id, "race_identity")
    _require(identity.get("year") == 2024, "race_year")
    _require(identity.get("name") == "Monaco Grand Prix", "race_name")
    for field in ("date", "circuit_name", "country"):
        _require(isinstance(identity.get(field), str) and identity[field], f"race_{field}")
    return {
        "status": "passed",
        "season_count": len(years),
        "first_year": min(years),
        "last_year": max(years),
        "race_count_2024": len(races),
        "race_id": race_id,
        "race_name": "Monaco Grand Prix",
    }


def _verify_prediction(verifier, race_id, model_version):
    payload = verifier.json(f"/api/predictions/{race_id}")
    _require(payload.get("race_id") == race_id, "prediction_race")
    _require(payload.get("model_version") == model_version, "prediction_model")
    postprocessing = _mapping(payload.get("postprocessing"), "prediction_postprocessor")
    _require(postprocessing.get("method") == "race_logit_offset", "prediction_postprocessor")
    _require(postprocessing.get("expected_podiums") == 3, "prediction_expected_count")
    selected = _mapping(postprocessing.get("selected"), "prediction_selected_projection")
    _require(
        math.isclose(
            _number(selected.get("adjusted_sum"), "prediction_adjusted_sum"), 3, abs_tol=1e-9
        ),
        "prediction_adjusted_sum",
    )
    rows = _sequence(payload.get("predictions"), "prediction_rows")
    _require(2 <= len(rows) <= 40, "prediction_row_count")
    driver_ids = []
    probabilities = []
    for item in rows:
        row = _mapping(item, "prediction_row")
        driver_ids.append(_integer(row.get("driver_id"), "prediction_driver"))
        probability = _number(row.get("probability"), "prediction_probability")
        _require(0 < probability < 1, "prediction_probability")
        probabilities.append(probability)
    _require(len(set(driver_ids)) == len(driver_ids), "prediction_driver_uniqueness")
    _require(probabilities == sorted(probabilities, reverse=True), "prediction_order")
    probability_sum = sum(probabilities)
    _require(math.isclose(probability_sum, 3, abs_tol=1e-9), "prediction_probability_sum")
    return payload, {
        "status": "passed",
        "race_id": race_id,
        "driver_count": len(rows),
        "model_version": model_version,
        "postprocessor": "race_logit_offset",
        "probability_sum": round(probability_sum, 12),
    }


def _verify_podium_outcomes(verifier, race_id, prediction, model_version):
    payload = verifier.json(f"/api/predictions/{race_id}/podium-outcomes?limit=12")
    _require(
        set(payload)
        == {
            "schema_version",
            "outcome_type",
            "race_id",
            "year",
            "experiment_id",
            "model_version",
            "diagnostics",
            "outcomes",
            "driver_marginals",
            "co_podium_pairs",
            "evidence_boundary",
            "notes",
        },
        "podium_outcome_fields",
    )
    _require(payload.get("schema_version") == "f1-podium-outcomes-v1", "podium_outcome_schema")
    _require(
        payload.get("outcome_type") == "derived_unordered_podium_set_distribution",
        "podium_outcome_type",
    )
    _require(payload.get("race_id") == race_id, "podium_outcome_race")
    _require(payload.get("year") == 2024, "podium_outcome_year")
    _require(payload.get("model_version") == model_version, "podium_outcome_model")
    _require(isinstance(payload.get("experiment_id"), str), "podium_outcome_experiment")

    forecast_rows = [
        _mapping(row, "podium_outcome_forecast_row")
        for row in _sequence(prediction.get("predictions"), "podium_outcome_forecast_rows")
    ]
    forecast_by_id = {
        _integer(row.get("driver_id"), "podium_outcome_driver"): _number(
            row.get("probability"), "podium_outcome_released_probability"
        )
        for row in forecast_rows
    }
    driver_count = len(forecast_rows)

    diagnostics = _mapping(payload.get("diagnostics"), "podium_outcome_diagnostics")
    _require(
        set(diagnostics)
        == {
            "method",
            "driver_count",
            "podium_size",
            "combination_count",
            "probability_sum",
            "reconstructed_marginal_sum",
            "maximum_marginal_error",
            "entropy_bits",
            "effective_outcome_count",
            "returned_outcome_count",
            "returned_probability_sum",
        },
        "podium_outcome_diagnostic_fields",
    )
    _require(
        diagnostics.get("method") == "maximum_entropy_fixed_size",
        "podium_outcome_method",
    )
    _require(
        _integer(diagnostics.get("driver_count"), "podium_outcome_driver_count") == driver_count,
        "podium_outcome_driver_count",
    )
    _require(diagnostics.get("podium_size") == 3, "podium_outcome_size")
    combination_count = _integer(
        diagnostics.get("combination_count"), "podium_outcome_combination_count"
    )
    _require(
        combination_count == math.comb(driver_count, 3),
        "podium_outcome_combination_count",
    )
    probability_sum = _number(diagnostics.get("probability_sum"), "podium_outcome_probability_sum")
    _require(
        math.isclose(probability_sum, 1, abs_tol=1e-12),
        "podium_outcome_probability_sum",
    )
    reconstructed_sum = _number(
        diagnostics.get("reconstructed_marginal_sum"),
        "podium_outcome_reconstructed_sum",
    )
    _require(
        math.isclose(reconstructed_sum, 3, abs_tol=1e-9),
        "podium_outcome_reconstructed_sum",
    )
    maximum_error = _number(
        diagnostics.get("maximum_marginal_error"), "podium_outcome_maximum_error"
    )
    _require(0 <= maximum_error <= 1e-8, "podium_outcome_maximum_error")
    entropy_bits = _number(diagnostics.get("entropy_bits"), "podium_outcome_entropy")
    _require(
        0 <= entropy_bits <= math.log2(combination_count) + 1e-10,
        "podium_outcome_entropy",
    )
    effective_count = _number(
        diagnostics.get("effective_outcome_count"), "podium_outcome_effective_count"
    )
    _require(
        1 <= effective_count <= combination_count
        and math.isclose(effective_count, 2**entropy_bits, rel_tol=1e-9, abs_tol=1e-9),
        "podium_outcome_effective_count",
    )
    returned_count = _integer(
        diagnostics.get("returned_outcome_count"), "podium_outcome_returned_count"
    )
    _require(
        returned_count == min(12, combination_count),
        "podium_outcome_returned_count",
    )
    returned_sum = _number(
        diagnostics.get("returned_probability_sum"), "podium_outcome_returned_sum"
    )
    _require(0 < returned_sum <= 1, "podium_outcome_returned_sum")

    outcomes = [
        _mapping(row, "podium_outcome_row")
        for row in _sequence(payload.get("outcomes"), "podium_outcome_rows")
    ]
    _require(len(outcomes) == returned_count, "podium_outcome_returned_count")
    outcome_keys = []
    outcome_probabilities = []
    cumulative = 0.0
    known_drivers = set(forecast_by_id)
    for rank, row in enumerate(outcomes, start=1):
        _require(
            set(row) == {"rank", "driver_ids", "probability", "cumulative_probability"},
            "podium_outcome_row_fields",
        )
        _require(row.get("rank") == rank, "podium_outcome_ranks")
        driver_ids = _sequence(row.get("driver_ids"), "podium_outcome_drivers")
        _require(
            len(driver_ids) == 3
            and all(isinstance(value, int) and not isinstance(value, bool) for value in driver_ids),
            "podium_outcome_drivers",
        )
        driver_key = tuple(driver_ids)
        _require(driver_key == tuple(sorted(driver_ids)), "podium_outcome_driver_order")
        _require(
            len(set(driver_ids)) == 3 and set(driver_ids).issubset(known_drivers),
            "podium_outcome_drivers",
        )
        probability = _number(row.get("probability"), "podium_outcome_probability")
        _require(0 < probability < 1, "podium_outcome_probability")
        outcome_keys.append(driver_key)
        outcome_probabilities.append(probability)
        cumulative = math.fsum((cumulative, probability))
        _require(
            math.isclose(
                _number(
                    row.get("cumulative_probability"),
                    "podium_outcome_cumulative_probability",
                ),
                cumulative,
                abs_tol=1e-12,
            ),
            "podium_outcome_cumulative_probability",
        )
    _require(len(set(outcome_keys)) == len(outcome_keys), "podium_outcome_uniqueness")
    _require(
        list(zip(outcome_probabilities, outcome_keys, strict=True))
        == sorted(
            zip(outcome_probabilities, outcome_keys, strict=True),
            key=lambda item: (-item[0], item[1]),
        ),
        "podium_outcome_order",
    )
    _require(math.isclose(cumulative, returned_sum, abs_tol=1e-12), "podium_outcome_returned_sum")

    marginals = [
        _mapping(row, "podium_outcome_marginal")
        for row in _sequence(payload.get("driver_marginals"), "podium_outcome_marginals")
    ]
    _require(len(marginals) == driver_count, "podium_outcome_marginal_count")
    marginal_ids = []
    released_values = []
    reconstructed_values = []
    errors = []
    for rank, (row, forecast_row) in enumerate(zip(marginals, forecast_rows, strict=True), start=1):
        _require(
            set(row)
            == {
                "driver_id",
                "forecast_rank",
                "released_probability",
                "reconstructed_probability",
                "absolute_error",
            },
            "podium_outcome_marginal_fields",
        )
        driver_id = _integer(row.get("driver_id"), "podium_outcome_driver")
        _require(
            driver_id == forecast_row.get("driver_id") and row.get("forecast_rank") == rank,
            "podium_outcome_marginal_order",
        )
        released = _number(row.get("released_probability"), "podium_outcome_released_probability")
        reconstructed = _number(
            row.get("reconstructed_probability"),
            "podium_outcome_reconstructed_probability",
        )
        error = _number(row.get("absolute_error"), "podium_outcome_marginal_error")
        _require(
            math.isclose(released, forecast_by_id[driver_id], abs_tol=1e-12),
            "podium_outcome_released_probability",
        )
        _require(
            abs(reconstructed - released) <= 1e-8
            and math.isclose(error, abs(reconstructed - released), abs_tol=1e-15),
            "podium_outcome_marginal_reconstruction",
        )
        marginal_ids.append(driver_id)
        released_values.append(released)
        reconstructed_values.append(reconstructed)
        errors.append(error)
    _require(len(set(marginal_ids)) == driver_count, "podium_outcome_marginal_uniqueness")
    _require(
        math.isclose(math.fsum(released_values), 3, abs_tol=1e-9), "podium_outcome_released_sum"
    )
    _require(
        math.isclose(math.fsum(reconstructed_values), reconstructed_sum, abs_tol=1e-9),
        "podium_outcome_reconstructed_sum",
    )
    _require(
        math.isclose(max(errors), maximum_error, abs_tol=1e-15),
        "podium_outcome_maximum_error",
    )

    pairs = [
        _mapping(row, "podium_outcome_pair")
        for row in _sequence(payload.get("co_podium_pairs"), "podium_outcome_pairs")
    ]
    pair_count = min(10, math.comb(driver_count, 2))
    _require(len(pairs) == pair_count, "podium_outcome_pair_count")
    pair_keys = []
    pair_probabilities = []
    for rank, row in enumerate(pairs, start=1):
        _require(
            set(row) == {"rank", "driver_ids", "probability"},
            "podium_outcome_pair_fields",
        )
        _require(row.get("rank") == rank, "podium_outcome_pair_ranks")
        driver_ids = _sequence(row.get("driver_ids"), "podium_outcome_pair_drivers")
        _require(
            len(driver_ids) == 2
            and all(isinstance(value, int) and not isinstance(value, bool) for value in driver_ids),
            "podium_outcome_pair_drivers",
        )
        pair_key = tuple(driver_ids)
        _require(pair_key == tuple(sorted(driver_ids)), "podium_outcome_pair_order")
        _require(
            len(set(driver_ids)) == 2 and set(driver_ids).issubset(known_drivers),
            "podium_outcome_pair_drivers",
        )
        probability = _number(row.get("probability"), "podium_outcome_pair_probability")
        first, second = (forecast_by_id[driver_id] for driver_id in driver_ids)
        _require(
            max(0, first + second - 1) - 1e-12 <= probability <= min(first, second) + 1e-12,
            "podium_outcome_pair_probability",
        )
        pair_keys.append(pair_key)
        pair_probabilities.append(probability)
    _require(len(set(pair_keys)) == pair_count, "podium_outcome_pair_uniqueness")
    _require(
        list(zip(pair_probabilities, pair_keys, strict=True))
        == sorted(
            zip(pair_probabilities, pair_keys, strict=True),
            key=lambda item: (-item[0], item[1]),
        ),
        "podium_outcome_pair_order",
    )

    boundary = _mapping(payload.get("evidence_boundary"), "podium_outcome_boundary")
    _require(
        set(boundary)
        == {
            "derived_from",
            "outcome_data_used",
            "separately_trained_joint_model",
            "joint_forecast_validated",
            "causal",
            "ordering",
            "statement",
        },
        "podium_outcome_boundary_fields",
    )
    _require(
        boundary.get("derived_from") == "released race-level marginal podium probabilities",
        "podium_outcome_boundary_source",
    )
    _require(boundary.get("outcome_data_used") is False, "podium_outcome_boundary_outcomes")
    _require(
        boundary.get("separately_trained_joint_model") is False,
        "podium_outcome_boundary_training",
    )
    _require(
        boundary.get("joint_forecast_validated") is False,
        "podium_outcome_boundary_validation",
    )
    _require(boundary.get("causal") is False, "podium_outcome_boundary_causal")
    _require(boundary.get("ordering") == "unordered_podium_set", "podium_outcome_boundary_order")
    _require(
        isinstance(boundary.get("statement"), str) and bool(boundary["statement"]),
        "podium_outcome_boundary_statement",
    )
    notes = _sequence(payload.get("notes"), "podium_outcome_notes")
    _require(
        1 <= len(notes) <= 4 and all(isinstance(note, str) and note for note in notes),
        "podium_outcome_notes",
    )
    return {
        "status": "passed",
        "race_id": race_id,
        "driver_count": driver_count,
        "combination_count": combination_count,
        "returned_outcome_count": returned_count,
        "probability_sum": round(probability_sum, 12),
        "reconstructed_marginal_sum": round(reconstructed_sum, 12),
        "maximum_marginal_error": maximum_error,
        "ordering": "unordered_podium_set",
    }


def _verify_scenario(verifier, race_id, prediction, model_version):
    forecast_rows = _sequence(prediction.get("predictions"), "scenario_forecast_rows")
    _require(len(forecast_rows) >= 2, "scenario_forecast_rows")
    selected_ids = [
        _integer(_mapping(row, "scenario_forecast_row").get("driver_id"), "scenario_driver")
        for row in forecast_rows[:2]
    ]
    body = json.dumps(
        {"driver_a_id": selected_ids[0], "driver_b_id": selected_ids[1]},
        separators=(",", ":"),
    ).encode()
    payload = verifier.json(
        f"/api/predictions/{race_id}/scenario",
        cache="no-store",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    _require(
        set(payload)
        == {
            "schema_version",
            "scenario_type",
            "race_id",
            "year",
            "experiment_id",
            "model_version",
            "modification",
            "postprocessing",
            "predictions",
            "evidence_boundary",
            "notes",
        },
        "scenario_fields",
    )
    _require(payload.get("schema_version") == "f1-grid-scenario-v1", "scenario_schema")
    _require(payload.get("scenario_type") == "counterfactual_grid_swap", "scenario_type")
    _require(payload.get("race_id") == race_id, "scenario_race")
    _require(payload.get("year") == 2024, "scenario_year")
    _require(payload.get("model_version") == model_version, "scenario_model")
    _require(isinstance(payload.get("experiment_id"), str), "scenario_experiment")

    modification = _mapping(payload.get("modification"), "scenario_modification")
    _require(set(modification) == {"kind", "drivers"}, "scenario_modification_fields")
    _require(
        modification.get("kind") == "swap_recorded_grid_positions",
        "scenario_modification_kind",
    )
    changes = [
        _mapping(change, "scenario_change")
        for change in _sequence(modification.get("drivers"), "scenario_changes")
    ]
    _require(len(changes) == 2, "scenario_change_count")
    _require(
        all(
            set(change)
            == {
                "driver_id",
                "recorded_grid_position",
                "scenario_grid_position",
                "original_grid_input",
                "scenario_grid_input",
            }
            for change in changes
        ),
        "scenario_change_fields",
    )
    changed_ids = [_integer(change.get("driver_id"), "scenario_driver") for change in changes]
    _require(changed_ids == selected_ids, "scenario_changed_drivers")
    recorded_positions = [
        _integer(change.get("recorded_grid_position"), "scenario_recorded_grid")
        for change in changes
    ]
    scenario_positions = [
        _integer(change.get("scenario_grid_position"), "scenario_grid") for change in changes
    ]
    _require(all(0 <= value <= 40 for value in recorded_positions), "scenario_recorded_grid")
    _require(scenario_positions == list(reversed(recorded_positions)), "scenario_grid_swap")
    original_inputs = [
        _integer(change.get("original_grid_input"), "scenario_original_grid_input")
        for change in changes
    ]
    scenario_inputs = [
        _integer(change.get("scenario_grid_input"), "scenario_grid_input") for change in changes
    ]
    _require(all(1 <= value <= 40 for value in original_inputs), "scenario_original_grid_input")
    _require(scenario_inputs == list(reversed(original_inputs)), "scenario_grid_input_swap")
    _require(original_inputs[0] != original_inputs[1], "scenario_grid_change")

    postprocessor = _mapping(payload.get("postprocessing"), "scenario_postprocessor")
    _require(
        set(postprocessor) == {"method", "expected_podiums", "original_sum", "scenario_sum"},
        "scenario_postprocessor_fields",
    )
    _require(postprocessor.get("method") == "race_logit_offset", "scenario_postprocessor")
    _require(postprocessor.get("expected_podiums") == 3, "scenario_expected_count")

    rows = [
        _mapping(row, "scenario_row")
        for row in _sequence(payload.get("predictions"), "scenario_rows")
    ]
    _require(len(rows) == len(forecast_rows), "scenario_row_count")
    required_row_fields = {
        "driver_id",
        "constructor_id",
        "recorded_grid_position",
        "scenario_grid_position",
        "original_grid_input",
        "scenario_grid_input",
        "original_rank",
        "scenario_rank",
        "original_probability",
        "scenario_probability",
        "probability_delta",
        "starting_grid_contribution",
    }
    _require(all(set(row) == required_row_fields for row in rows), "scenario_row_fields")
    forecast_by_id = {
        _integer(row.get("driver_id"), "scenario_driver"): (
            rank,
            _number(row.get("probability"), "scenario_original_probability"),
        )
        for rank, row in enumerate(
            (_mapping(item, "scenario_forecast_row") for item in forecast_rows), start=1
        )
    }
    scenario_driver_ids = []
    original_ranks = []
    scenario_ranks = []
    original_probabilities = []
    scenario_probabilities = []
    deltas = []
    changes_by_id = {change["driver_id"]: change for change in changes}
    for row in rows:
        driver_id = _integer(row.get("driver_id"), "scenario_driver")
        scenario_driver_ids.append(driver_id)
        _integer(row.get("constructor_id"), "scenario_constructor")
        original_rank = _integer(row.get("original_rank"), "scenario_original_rank")
        scenario_rank = _integer(row.get("scenario_rank"), "scenario_rank")
        original_ranks.append(original_rank)
        scenario_ranks.append(scenario_rank)
        original_probability = _number(
            row.get("original_probability"), "scenario_original_probability"
        )
        scenario_probability = _number(row.get("scenario_probability"), "scenario_probability")
        delta = _number(row.get("probability_delta"), "scenario_probability_delta")
        _require(0 < original_probability < 1, "scenario_original_probability")
        _require(0 < scenario_probability < 1, "scenario_probability")
        _require(
            driver_id in forecast_by_id
            and original_rank == forecast_by_id[driver_id][0]
            and math.isclose(original_probability, forecast_by_id[driver_id][1], abs_tol=1e-12),
            "scenario_original_consistency",
        )
        _require(
            math.isclose(scenario_probability - original_probability, delta, abs_tol=1e-12),
            "scenario_probability_delta",
        )
        recorded_grid = _integer(row.get("recorded_grid_position"), "scenario_recorded_grid")
        scenario_grid = _integer(row.get("scenario_grid_position"), "scenario_grid")
        original_grid_input = _integer(
            row.get("original_grid_input"), "scenario_original_grid_input"
        )
        scenario_grid_input = _integer(row.get("scenario_grid_input"), "scenario_grid_input")
        _require(
            0 <= recorded_grid <= 40
            and 0 <= scenario_grid <= 40
            and 1 <= original_grid_input <= 40
            and 1 <= scenario_grid_input <= 40,
            "scenario_grid_bounds",
        )
        if driver_id in changes_by_id:
            change = changes_by_id[driver_id]
            _require(
                recorded_grid == change["recorded_grid_position"]
                and scenario_grid == change["scenario_grid_position"]
                and original_grid_input == change["original_grid_input"]
                and scenario_grid_input == change["scenario_grid_input"]
                and original_grid_input != scenario_grid_input,
                "scenario_changed_grid",
            )
        else:
            _require(
                recorded_grid == scenario_grid and original_grid_input == scenario_grid_input,
                "scenario_unchanged_grid",
            )
        contribution = _mapping(row.get("starting_grid_contribution"), "scenario_grid_contribution")
        _require(
            set(contribution) == {"original", "scenario", "delta"},
            "scenario_grid_contribution_fields",
        )
        contribution_original = _number(contribution.get("original"), "scenario_grid_contribution")
        contribution_scenario = _number(contribution.get("scenario"), "scenario_grid_contribution")
        contribution_delta = _number(contribution.get("delta"), "scenario_grid_contribution")
        _require(
            math.isclose(
                contribution_scenario - contribution_original,
                contribution_delta,
                abs_tol=1e-12,
            ),
            "scenario_grid_contribution_delta",
        )
        original_probabilities.append(original_probability)
        scenario_probabilities.append(scenario_probability)
        deltas.append(delta)

    row_count = len(rows)
    _require(set(scenario_driver_ids) == set(forecast_by_id), "scenario_driver_set")
    _require(set(original_ranks) == set(range(1, row_count + 1)), "scenario_original_ranks")
    _require(scenario_ranks == list(range(1, row_count + 1)), "scenario_ranks")
    _require(
        scenario_probabilities == sorted(scenario_probabilities, reverse=True),
        "scenario_probability_order",
    )
    original_sum = sum(original_probabilities)
    scenario_sum = sum(scenario_probabilities)
    _require(math.isclose(original_sum, 3, abs_tol=1e-9), "scenario_original_sum")
    _require(math.isclose(scenario_sum, 3, abs_tol=1e-9), "scenario_probability_sum")
    _require(math.isclose(sum(deltas), 0, abs_tol=1e-9), "scenario_delta_sum")
    _require(
        math.isclose(
            _number(postprocessor.get("original_sum"), "scenario_original_sum"),
            original_sum,
            abs_tol=1e-9,
        )
        and math.isclose(
            _number(postprocessor.get("scenario_sum"), "scenario_probability_sum"),
            scenario_sum,
            abs_tol=1e-9,
        ),
        "scenario_postprocessor_sums",
    )
    boundary = _mapping(payload.get("evidence_boundary"), "scenario_boundary")
    _require(
        set(boundary)
        == {"input_scope", "outcome_data_used", "causal", "validated_forecast", "statement"},
        "scenario_boundary_fields",
    )
    _require(
        boundary.get("input_scope") == "recorded pre-race features with two grid positions swapped",
        "scenario_input_scope",
    )
    _require(boundary.get("outcome_data_used") is False, "scenario_outcome_boundary")
    _require(boundary.get("causal") is False, "scenario_causal_boundary")
    _require(boundary.get("validated_forecast") is False, "scenario_validation_boundary")
    _require(
        isinstance(boundary.get("statement"), str) and bool(boundary["statement"]),
        "scenario_boundary_statement",
    )
    notes = _sequence(payload.get("notes"), "scenario_notes")
    _require(
        1 <= len(notes) <= 4 and all(isinstance(note, str) for note in notes), "scenario_notes"
    )
    return {
        "status": "passed",
        "race_id": race_id,
        "driver_count": row_count,
        "changed_driver_count": len(changes),
        "scenario_kind": "grid_swap",
        "original_probability_sum": round(original_sum, 12),
        "scenario_probability_sum": round(scenario_sum, 12),
    }


def _verify_review(verifier, race_id, prediction, model_version):
    payload = verifier.json(f"/api/predictions/{race_id}/review")
    _require(payload.get("review_type") == "post_race_review", "review_type")
    _require(_mapping(payload.get("race"), "review_race").get("race_id") == race_id, "review_race")
    _require(payload.get("model_version") == model_version, "review_model")
    postprocessor = _mapping(payload.get("postprocessor"), "review_postprocessor")
    _require(
        postprocessor == {"method": "race_logit_offset", "expected_podiums": 3},
        "review_postprocessor",
    )
    predicted = _sequence(payload.get("predicted_podium"), "review_predicted")
    recorded = _sequence(payload.get("recorded_podium"), "review_recorded")
    _require(len(predicted) == len(recorded) == 3, "review_podium_count")
    predicted_ids = [
        _integer(_mapping(row, "review_podium").get("driver_id"), "review_driver")
        for row in predicted
    ]
    recorded_ids = [
        _integer(_mapping(row, "review_podium").get("driver_id"), "review_driver")
        for row in recorded
    ]
    forecast_ids = [row["driver_id"] for row in prediction["predictions"][:3]]
    _require(predicted_ids == forecast_ids, "review_forecast_order")
    _require(len(set(recorded_ids)) == 3, "review_recorded_uniqueness")
    hits = _integer(payload.get("top_three_hits"), "review_hits")
    expected_hits = len(set(predicted_ids) & set(recorded_ids))
    _require(hits == expected_hits, "review_hits")
    _require(payload.get("exact_podium_set") is (hits == 3), "review_exact_set")
    drivers = _sequence(payload.get("drivers"), "review_drivers")
    _require(len(drivers) == len(prediction["predictions"]), "review_driver_count")
    driver_ids = [
        _integer(_mapping(row, "review_driver").get("driver_id"), "review_driver")
        for row in drivers
    ]
    _require(
        set(driver_ids) == {row["driver_id"] for row in prediction["predictions"]},
        "review_driver_set",
    )
    brier = _number(payload.get("brier_score"), "review_brier")
    mae = _number(payload.get("mean_absolute_error"), "review_mae")
    _require(0 <= brier <= 1 and 0 <= mae <= 1, "review_metrics")
    return {
        "status": "passed",
        "race_id": race_id,
        "driver_count": len(drivers),
        "top_three_hits": hits,
        "exact_podium_set": hits == 3,
        "brier_score": brier,
        "mean_absolute_error": mae,
    }


def _verify_model_card(verifier, model_version):
    payload = verifier.json("/api/model-card")
    _require(payload.get("schema_version") == "f1-public-model-card-v1", "model_card_schema")
    identity = _mapping(payload.get("identity"), "model_card_identity")
    _require(identity.get("model_version") == model_version, "model_card_version")
    boundary = _mapping(payload.get("evidence_boundary"), "model_card_boundary")
    _require(boundary.get("status") == "post_test_iterative_evidence", "model_card_boundary")
    _require(boundary.get("unseen_holdout") is False, "model_card_unseen_boundary")
    lineage = _mapping(payload.get("lineage"), "model_card_lineage")
    hashes = []
    for group_name in ("artifacts", "evidence"):
        group = _mapping(lineage.get(group_name), "model_card_hashes")
        hashes.extend(group.values())
    _require(len(hashes) == 6, "model_card_hash_count")
    _require(
        all(isinstance(value, str) and SHA256_PATTERN.fullmatch(value) for value in hashes),
        "model_card_hashes",
    )
    coverage = _mapping(payload.get("source_coverage"), "model_card_coverage")
    _require(coverage.get("archive_years") == [1950, 2024], "model_card_archive")
    _require(coverage.get("races") == 1125, "model_card_races")
    _require(coverage.get("audited_tables") == 14, "model_card_tables")
    postprocessor = _mapping(payload.get("postprocessor"), "model_card_postprocessor")
    _require(
        postprocessor == {"name": "race_logit_offset", "version": "v1", "expected_count": 3},
        "model_card_postprocessor",
    )
    seasons = _mapping(payload.get("per_season"), "model_card_seasons")
    _require(set(seasons) == {str(year) for year in range(2019, 2025)}, "model_card_seasons")
    return {
        "status": "passed",
        "schema_version": "f1-public-model-card-v1",
        "model_version": model_version,
        "hash_count": len(hashes),
        "archive_years": [1950, 2024],
        "archive_races": 1125,
        "audited_tables": 14,
        "season_evidence_count": len(seasons),
        "unseen_holdout": False,
    }


def _load_access_code(path):
    try:
        source = Path(path)
        _require(source.is_file() and source.stat().st_size <= 4096, "access_code_file")
        value = source.read_text(encoding="utf-8").strip()
    except OSError:
        raise VerificationError("access_code_file") from None
    _require(1 <= len(value) <= 512 and "\x00" not in value, "access_code")
    return value


def _verify_chat(verifier, access_code):
    body = json.dumps({"question": CHAT_QUESTION}, separators=(",", ":")).encode()
    payload = verifier.json(
        "/api/chat",
        cache="no-store",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Chat-Access-Code": access_code,
        },
    )
    _require(payload.get("intent") == "statistics", "chat_intent")
    _require(payload.get("status") == "executed", "chat_status")
    corrections = _sequence(payload.get("corrections"), "chat_corrections")
    repaired = any(
        isinstance(item, dict)
        and str(item.get("original", "")).lower() == "verstapen"
        and str(item.get("corrected", "")).lower() == "verstappen"
        for item in corrections
    )
    _require(repaired, "chat_typo_repair")
    trace = _mapping(payload.get("trace"), "chat_trace")
    _require(trace.get("route") == "statistics", "chat_route")
    calls = _integer(trace.get("provider_call_count"), "chat_calls")
    repairs = _integer(trace.get("repair_count"), "chat_repairs")
    _require(1 <= calls <= 3, "chat_call_budget")
    _require(0 <= repairs <= 1, "chat_repair_budget")
    tables = _sequence(trace.get("tables"), "chat_tables")
    _require(
        all(isinstance(table, str) and table in KNOWN_TABLES for table in tables),
        "chat_tables",
    )
    _require({"drivers", "results", "races"}.issubset(tables), "chat_grounding")
    return {
        "status": "passed",
        "intent": "statistics",
        "correction_verified": True,
        "provider_call_count": calls,
        "repair_count": repairs,
    }


def verify_release(base_url, output, *, access_code_file=None, timeout=15):
    """Verify the public release and atomically refuse any existing output path."""

    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    _require(isinstance(timeout, (int, float)) and 0 < timeout <= 60, "timeout")
    started_at = perf_counter()
    verifier = _Verifier(str(base_url), float(timeout))

    root_metadata = verifier.html("/")
    model_metadata = verifier.html("/model")
    _require(model_metadata.title == root_metadata.title, "deep_link_shell")
    hashed_assets = sorted(
        {
            urlsplit(asset).path
            for asset in root_metadata.assets
            if HASHED_ASSET_PATTERN.fullmatch(urlsplit(asset).path)
        }
    )
    _require(bool(hashed_assets), "hashed_asset")
    asset_body, asset_headers = verifier._request(
        hashed_assets[0], cache="public, max-age=31536000, immutable"
    )
    _require(bool(asset_body), "asset_body")
    _require(
        any(
            content_type in asset_headers.get("content-type", "")
            for content_type in ("javascript", "text/css", "font/")
        ),
        "asset_type",
    )

    readiness = _verify_readiness(verifier)
    archive = _verify_archive(verifier)
    prediction_payload, prediction = _verify_prediction(
        verifier, archive["race_id"], readiness["model_version"]
    )
    podium_outcomes = _verify_podium_outcomes(
        verifier, archive["race_id"], prediction_payload, readiness["model_version"]
    )
    scenario = _verify_scenario(
        verifier, archive["race_id"], prediction_payload, readiness["model_version"]
    )
    review = _verify_review(
        verifier, archive["race_id"], prediction_payload, readiness["model_version"]
    )
    model_card = _verify_model_card(verifier, readiness["model_version"])
    _require(verifier.gzip_responses >= 1, "gzip_delivery")

    checks = {
        "spa": {
            "status": "passed",
            "title": root_metadata.title,
            "description_length": len(root_metadata.description),
            "model_deep_link": True,
            "immutable_asset": True,
        },
        "readiness": readiness,
        "archive": archive,
        "prediction": prediction,
        "podium_outcomes": podium_outcomes,
        "scenario": scenario,
        "review": review,
        "model_card": model_card,
    }
    if access_code_file is not None:
        checks["chat"] = _verify_chat(verifier, _load_access_code(access_code_file))
    checks["delivery"] = {
        "status": "passed",
        "response_count": verifier.response_count,
        "request_ids_unique": len(set(verifier.request_ids)) == verifier.response_count,
        "server_generated_request_ids": True,
        "security_headers": True,
        "gzip_responses": verifier.gzip_responses,
        "cache_policy": True,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": verifier.base_url,
        "status": "passed",
        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
        "checks": checks,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--access-code-file", type=Path)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        report = verify_release(
            args.base_url,
            args.output,
            access_code_file=args.access_code_file,
            timeout=args.timeout,
        )
    except FileExistsError:
        print(json.dumps({"status": "failed", "error_code": "output_exists"}), file=sys.stderr)
        return 1
    except VerificationError as error:
        print(
            json.dumps({"status": "failed", "error_code": error.code}),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "schema_version": report["schema_version"],
                "output": str(args.output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
