"""Local dotenv support; production injects environment variables from AWS Secrets Manager."""

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv
from backend.database import ROOT


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class BedrockSettings:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    project_id: str = field(default="", repr=False)

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        key = os.environ.get("OPENAI_API_KEY", "")
        base = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
        parsed = urlparse(base)
        if not key or not base:
            raise ConfigurationError(
                "Bedrock credentials are missing; configure the project environment."
            )
        if (
            parsed.scheme != "https"
            or not re.fullmatch(r"bedrock-mantle\.[a-z0-9-]+\.api\.aws", parsed.hostname or "")
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.query
            or parsed.fragment
            or parsed.path != "/v1"
        ):
            raise ConfigurationError(
                "This project requires an AWS Bedrock Mantle HTTPS /v1 endpoint."
            )
        model = os.environ.get("OPENAI_MODEL", "openai.gpt-oss-120b")
        if model != "openai.gpt-oss-120b":
            raise ConfigurationError("The approved chat model is openai.gpt-oss-120b.")
        return cls(key, base, model, os.environ.get("OPENAI_PROJECT_ID", ""))
