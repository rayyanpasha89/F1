"""OpenAI-compatible Bedrock transport. No tools, arbitrary URLs or provider fallback."""

import json
import time

import httpx
from pydantic import BaseModel

from backend.config import BedrockSettings


class ProviderError(ValueError):
    pass


class BedrockClient:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or BedrockSettings.load()
        self.transport = transport

    def structured(self, system, user, schema: type[BaseModel]):
        settings = self.settings
        headers = {
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        }
        if settings.project_id:
            headers["OpenAI-Project"] = settings.project_id
        prompt = (
            system
            + "\nReturn ONLY one JSON object conforming to this schema:\n"
            + json.dumps(schema.model_json_schema())
        )
        start = time.monotonic()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(60, connect=10),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = client.post(
                    settings.base_url + "/chat/completions",
                    headers=headers,
                    json={
                        "model": settings.model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0,
                        "max_completion_tokens": 4096,
                    },
                )
                if response.status_code != 200:
                    raise ProviderError(f"Bedrock request failed (HTTP {response.status_code}).")
                payload = response.json()
                choice = payload["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ProviderError(
                        "Bedrock response exceeded its output budget; simplify the question."
                    )
                content = choice["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                result = schema.model_validate_json(content)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, AttributeError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(
                "Bedrock returned an unavailable or invalid structured response."
            ) from exc
        return result, {
            "model": settings.model,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
            "usage": payload.get("usage", {}),
        }
