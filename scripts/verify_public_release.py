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
