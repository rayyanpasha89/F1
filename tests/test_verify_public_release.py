import gzip
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from urllib.parse import urlsplit

import pytest

from scripts.verify_public_release import VerificationError, verify_release


MODEL_VERSION = "EXP-007+podium-count-v1"
SHA = "a" * 64


class _LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer's reverse DNS lookup can block on isolated developer machines.
        TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


def _podium(rank, driver_id, name, probability):
    return {
        "rank": rank,
        "driver_id": driver_id,
        "driver_name": name,
        "constructor_name": "Test team",
        "probability": probability,
    }


def _payloads():
    predictions = [
        {"driver_id": 1, "probability": 0.9},
        {"driver_id": 2, "probability": 0.8},
        {"driver_id": 3, "probability": 0.7},
        {"driver_id": 4, "probability": 0.6},
    ]
    races_2024 = [
        {
            "race_id": 1128 if round_number == 8 else 1100 + round_number,
            "year": 2024,
            "round": round_number,
            "name": "Monaco Grand Prix" if round_number == 8 else f"Race {round_number}",
        }
        for round_number in range(1, 25)
    ]
    return {
        "/": """<!doctype html><html><head>
        <meta name="description" content="A complete historical Formula 1 analytics application with accountable podium forecasts.">
        <title>F1 Race Strategist | Historical Analytics</title>
        <script type="module" src="/assets/index-AbCd1234.js"></script>
        </head><body><div id="root"></div></body></html>""",
        "/model": """<!doctype html><html><head>
        <meta name="description" content="A complete historical Formula 1 analytics application with accountable podium forecasts.">
        <title>F1 Race Strategist | Historical Analytics</title>
        <script type="module" src="/assets/index-AbCd1234.js"></script>
        </head><body><div id="root"></div></body></html>""",
        "/assets/index-AbCd1234.js": "console.log('verified release');" * 30,
        "/api/health/ready": {
            "status": "ready",
            "archive_through": 2024,
            "model_version": MODEL_VERSION,
            "checks": {
                "database": "ok",
                "model_bundle": "verified",
                "model_card": "verified",
            },
        },
        "/api/seasons": {"data": [{"year": year} for year in range(2024, 1949, -1)]},
        "/api/races": {"data": races_2024},
        "/api/races/1128": {
            "race_id": 1128,
            "year": 2024,
            "round": 8,
            "name": "Monaco Grand Prix",
            "date": "2024-05-26",
            "circuit_name": "Circuit de Monaco",
            "country": "Monaco",
        },
        "/api/predictions/1128": {
            "race_id": 1128,
            "year": 2024,
            "model_version": MODEL_VERSION,
            "postprocessing": {
                "method": "race_logit_offset",
                "expected_podiums": 3,
                "selected": {"adjusted_sum": 3.0},
            },
            "predictions": predictions,
        },
        "/api/predictions/1128/scenario": {
            "schema_version": "f1-grid-scenario-v1",
            "scenario_type": "counterfactual_grid_swap",
            "race_id": 1128,
            "year": 2024,
            "experiment_id": "EXP-007",
            "model_version": MODEL_VERSION,
            "modification": {
                "kind": "swap_recorded_grid_positions",
                "drivers": [
                    {
                        "driver_id": 1,
                        "recorded_grid_position": 1,
                        "scenario_grid_position": 2,
                        "original_grid_input": 1,
                        "scenario_grid_input": 2,
                    },
                    {
                        "driver_id": 2,
                        "recorded_grid_position": 2,
                        "scenario_grid_position": 1,
                        "original_grid_input": 2,
                        "scenario_grid_input": 1,
                    },
                ],
            },
            "postprocessing": {
                "method": "race_logit_offset",
                "expected_podiums": 3,
                "original_sum": 3.0,
                "scenario_sum": 3.0,
            },
            "predictions": [
                {
                    "driver_id": driver_id,
                    "constructor_id": driver_id,
                    "recorded_grid_position": driver_id,
                    "scenario_grid_position": 3 - driver_id if driver_id <= 2 else driver_id,
                    "original_grid_input": driver_id,
                    "scenario_grid_input": 3 - driver_id if driver_id <= 2 else driver_id,
                    "original_rank": driver_id,
                    "scenario_rank": driver_id,
                    "original_probability": original_probability,
                    "scenario_probability": scenario_probability,
                    "probability_delta": scenario_probability - original_probability,
                    "starting_grid_contribution": {
                        "original": 0.3 - driver_id * 0.05,
                        "scenario": 0.3 - (3 - driver_id if driver_id <= 2 else driver_id) * 0.05,
                        "delta": (
                            (0.3 - (3 - driver_id if driver_id <= 2 else driver_id) * 0.05)
                            - (0.3 - driver_id * 0.05)
                        ),
                    },
                }
                for driver_id, original_probability, scenario_probability in (
                    (1, 0.9, 0.85),
                    (2, 0.8, 0.85),
                    (3, 0.7, 0.7),
                    (4, 0.6, 0.6),
                )
            ],
            "evidence_boundary": {
                "input_scope": "recorded pre-race features with two grid positions swapped",
                "outcome_data_used": False,
                "causal": False,
                "validated_forecast": False,
                "statement": "Frozen-model sensitivity only.",
            },
            "notes": ["Only two grid inputs changed."],
        },
        "/api/predictions/1128/review": {
            "review_type": "post_race_review",
            "race": {"race_id": 1128},
            "model_version": MODEL_VERSION,
            "postprocessor": {"method": "race_logit_offset", "expected_podiums": 3},
            "predicted_podium": [
                _podium(1, 1, "Driver One", 0.9),
                _podium(2, 2, "Driver Two", 0.8),
                _podium(3, 3, "Driver Three", 0.7),
            ],
            "recorded_podium": [
                _podium(1, 1, "Driver One", 0.9),
                _podium(2, 2, "Driver Two", 0.8),
                _podium(3, 3, "Driver Three", 0.7),
            ],
            "top_three_hits": 3,
            "exact_podium_set": True,
            "brier_score": 0.05,
            "mean_absolute_error": 0.1,
            "drivers": [{"driver_id": row["driver_id"]} for row in predictions],
        },
        "/api/model-card": {
            "schema_version": "f1-public-model-card-v1",
            "identity": {"model_version": MODEL_VERSION},
            "lineage": {
                "artifacts": {"selected_model": SHA, "grid_baseline": SHA},
                "evidence": {
                    "model_selection": SHA,
                    "final_test_metrics": SHA,
                    "data_audit": SHA,
                    "race_constraint_evaluation": SHA,
                },
            },
            "source_coverage": {
                "archive_years": [1950, 2024],
                "races": 1125,
                "audited_tables": 14,
            },
            "postprocessor": {
                "name": "race_logit_offset",
                "version": "v1",
                "expected_count": 3,
            },
            "per_season": {str(year): {} for year in range(2019, 2025)},
            "evidence_boundary": {
                "status": "post_test_iterative_evidence",
                "unseen_holdout": False,
            },
        },
        "/api/chat": {
            "intent": "statistics",
            "status": "executed",
            "answer": "podiums: 14",
            "sql": "SELECT secret_query_text",
            "corrections": [{"original": "Verstapen", "corrected": "verstappen"}],
            "provider_calls": [{"credential": "server-returned-secret"}],
            "trace": {
                "route": "statistics",
                "provider_call_count": 2,
                "repair_count": 0,
                "tables": ["drivers", "results", "races"],
            },
        },
    }


@contextmanager
def _release_server():
    payloads = _payloads()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._serve("GET")

        def do_POST(self):
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length)
            self._serve("POST", body)

        def _serve(self, method, body=b""):
            path = urlsplit(self.path).path
            self.server.requests.append(
                {
                    "method": method,
                    "path": path,
                    "request_id": self.headers.get("x-request-id"),
                    "access_code": self.headers.get("x-chat-access-code"),
                    "body": body,
                }
            )
            post_paths = {"/api/chat", "/api/predictions/1128/scenario"}
            if path not in self.server.payloads or (method == "POST") != (path in post_paths):
                self.send_error(404)
                return
            payload = self.server.payloads[path]
            is_json = isinstance(payload, dict)
            raw = (
                json.dumps(payload, separators=(",", ":")).encode() if is_json else payload.encode()
            )
            encoded = gzip.compress(raw)
            self.server.counter += 1
            self.send_response(200)
            self.send_header(
                "Content-Type", "application/json" if is_json else self._content_type(path)
            )
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("X-Request-ID", f"{self.server.counter:032x}")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
            )
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
                "connect-src 'self'; base-uri 'self'",
            )
            if path in {"/", "/model"}:
                cache = "no-cache"
            elif path.startswith("/assets/"):
                cache = "public, max-age=31536000, immutable"
            elif path in {
                "/api/health/ready",
                "/api/chat",
                "/api/predictions/1128/scenario",
            }:
                cache = "no-store"
            else:
                cache = "public, max-age=300"
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(encoded)

        @staticmethod
        def _content_type(path):
            return "application/javascript" if path.endswith(".js") else "text/html"

        def log_message(self, _format, *_args):
            return

    server = _LocalHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.counter = 0
    server.payloads = payloads
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_verifier_checks_public_contract_and_writes_allowlisted_report(tmp_path):
    output = tmp_path / "release.json"
    with _release_server() as (server, base_url):
        report = verify_release(base_url, output, timeout=2)

    assert report["status"] == "passed"
    assert report["checks"]["readiness"]["archive_through"] == 2024
    assert report["checks"]["archive"]["race_id"] == 1128
    assert report["checks"]["prediction"]["probability_sum"] == 3.0
    assert report["checks"]["scenario"] == {
        "status": "passed",
        "race_id": 1128,
        "driver_count": 4,
        "changed_driver_count": 2,
        "scenario_kind": "grid_swap",
        "original_probability_sum": 3.0,
        "scenario_probability_sum": 3.0,
    }
    assert report["checks"]["review"]["top_three_hits"] == 3
    assert report["checks"]["model_card"]["unseen_holdout"] is False
    assert report["checks"]["delivery"]["request_ids_unique"] is True
    assert "chat" not in report["checks"]
    assert json.loads(output.read_text()) == report
    assert {request["path"] for request in server.requests} >= {
        "/",
        "/model",
        "/assets/index-AbCd1234.js",
        "/api/health/ready",
        "/api/seasons",
        "/api/races",
        "/api/races/1128",
        "/api/predictions/1128",
        "/api/predictions/1128/scenario",
        "/api/predictions/1128/review",
        "/api/model-card",
    }
    assert all(request["request_id"] == "verifier-untrusted" for request in server.requests)
    scenario_request = next(
        request for request in server.requests if request["path"].endswith("/scenario")
    )
    assert scenario_request["method"] == "POST"
    assert json.loads(scenario_request["body"]) == {"driver_a_id": 1, "driver_b_id": 2}


def test_optional_chat_verifies_typo_repair_without_persisting_sensitive_content(tmp_path):
    secret = "chat-access-SENTINEL"
    access_file = tmp_path / "access-code.txt"
    access_file.write_text(secret + "\n")
    output = tmp_path / "release-chat.json"

    with _release_server() as (server, base_url):
        report = verify_release(base_url, output, access_code_file=access_file, timeout=2)

    event = report["checks"]["chat"]
    assert event == {
        "status": "passed",
        "intent": "statistics",
        "correction_verified": True,
        "provider_call_count": 2,
        "repair_count": 0,
    }
    chat_request = next(request for request in server.requests if request["path"] == "/api/chat")
    assert chat_request["access_code"] == secret
    assert b"Verstapen" in chat_request["body"]
    serialized = output.read_text()
    for forbidden in (secret, "Verstapen", "SELECT", "server-returned-secret"):
        assert forbidden not in serialized


def test_verifier_refuses_to_overwrite_before_network_access(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("keep me")
    with _release_server() as (server, base_url):
        with pytest.raises(FileExistsError):
            verify_release(base_url, output, timeout=2)
    assert output.read_text() == "keep me"
    assert server.requests == []


def test_invalid_probability_contract_fails_closed_without_report(tmp_path):
    output = tmp_path / "invalid.json"
    with _release_server() as (server, base_url):
        server.payloads["/api/predictions/1128"]["predictions"][0]["probability"] = 0.4
        with pytest.raises(VerificationError):
            verify_release(base_url, output, timeout=2)
    assert not output.exists()
    assert any(request["path"] == "/api/predictions/1128" for request in server.requests)


def test_invalid_grid_scenario_contract_fails_closed_without_report(tmp_path):
    output = tmp_path / "invalid-scenario.json"
    with _release_server() as (server, base_url):
        server.payloads["/api/predictions/1128/scenario"]["predictions"][0][
            "scenario_grid_position"
        ] = 1
        with pytest.raises(VerificationError):
            verify_release(base_url, output, timeout=2)
    assert not output.exists()
    assert any(request["path"].endswith("/scenario") for request in server.requests)
