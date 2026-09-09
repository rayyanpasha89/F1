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
