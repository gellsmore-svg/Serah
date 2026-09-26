"""OpenAI-compatible chat client for the optional semantic layer.

Responses are validated against a schema. Retries stay on the same model.
A failure is returned to the caller; Serah does not silently switch curators.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from serah.errors import CuratorError

T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class ChatClient:
    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        root = self.base_url if self.base_url.endswith("/v1") else f"{self.base_url}/v1"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = httpx.post(
                f"{root}/chat/completions",
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise CuratorError(f"llm request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise CuratorError(f"llm returned HTTP {response.status_code}")
        try:
            payload = response.json()
            return str(payload["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise CuratorError("llm response did not contain message content") from exc


def parse_json_object(text: str) -> dict:
    match = _FENCE.search(text)
    raw = match.group(1) if match else text.strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CuratorError("llm response was not valid JSON") from exc
    if not isinstance(value, dict):
        raise CuratorError("llm response JSON was not an object")
    return value


def complete_model(client: ChatClient, system: str, user: str, model: type[T], attempts: int = 3) -> T:
    prompt = user
    last = "structured output failed"
    for _ in range(attempts):
        text = client.complete(system, prompt)
        try:
            return model.model_validate(parse_json_object(text))
        except (CuratorError, ValidationError) as exc:
            last = type(exc).__name__
            prompt = (
                user
                + "\n\nThe previous reply did not match the schema. "
                + "Reply with one JSON object and nothing else."
            )
    raise CuratorError(last)
