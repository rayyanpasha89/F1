"""Check the secret-name contract used by cloud chat; no AWS calls in tests."""

from pathlib import Path


def test_cloud_readonly_secret_matches_chat_configuration():
    source = Path("backend/ai/chat.py").read_text()
    terraform = Path("infra/compute.tf").read_text()
    bootstrap = Path("scripts/bootstrap_aws.py").read_text()
    for content in [source, terraform, bootstrap]:
        assert "SQL_READONLY_DATABASE_URL" in content
        assert "NL2SQL_DATABASE_URL" not in content


def test_image_excludes_secret_files_and_runs_unprivileged():
    dockerfile = Path("Dockerfile").read_text()
    assert "USER app" in dockerfile
    assert "COPY . " not in dockerfile
    assert ".env" not in dockerfile
    assert Path(".dockerignore").read_text().splitlines()[0] == "*"


def test_release_image_includes_and_verifies_model_evidence():
    dockerfile = Path("Dockerfile").read_text()
    dockerignore = Path(".dockerignore").read_text()
    buildspec = Path("buildspec.yml").read_text()
    aws_release = Path("scripts/release_aws.py").read_text()
    lightsail_release = Path("scripts/release_lightsail.py").read_text()

    for path in (
        "models/manifest.json",
        "reports/model_selection.json",
        "reports/final_test_metrics.json",
        "reports/data_audit.json",
        "reports/race_constraint_evaluation.json",
    ):
        assert path in dockerfile
        assert f"!{path}" in dockerignore
    assert "verify_model_bundle" in buildspec
    assert "verify_model_bundle(ROOT)" in aws_release
    assert "verify_model_bundle(ROOT)" in lightsail_release
    assert '"path": "/api/health/ready"' in lightsail_release
