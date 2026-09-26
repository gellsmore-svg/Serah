"""HTTP System One clients for Jev, Kai, and Decider.

The wire format is the documented POST /v1/systemone body:
{"model", "state", "questions"} -> {"answers": {...}}.
"""

from __future__ import annotations

import time

import httpx

from serah.engines.base import DecisionRequest, DecisionResult, EngineStatus
from serah.engines.translate import from_score_answer
from serah.errors import EngineError, EngineUnavailable


class SystemOneHttpEngine:
    def __init__(
        self,
        engine_id: str,
        display_name: str,
        base_url: str | None,
        api_key: str | None,
        model: str,
        *,
        key_required: bool,
        timeout: float = 60.0,
    ):
        self.engine_id = engine_id
        self.display_name = display_name
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.model = model
        self.key_required = key_required
        self.timeout = timeout

    def status(self) -> EngineStatus:
        if not self.base_url or (self.key_required and not self.api_key):
            detail = "endpoint is not configured" if not self.base_url else "API key is not configured"
            return EngineStatus(self.engine_id, self.display_name, "NOT_CONFIGURED", "remote", detail)
        return EngineStatus(
            self.engine_id,
            self.display_name,
            "REMOTE",
            "remote",
            "endpoint configured; health is not probed until a score run",
        )

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        return self.evaluate_batch([request])[0]

    def evaluate_batch(self, requests: list[DecisionRequest]) -> list[DecisionResult]:
        if not self.base_url or (self.key_required and not self.api_key):
            raise EngineUnavailable(f"{self.engine_id} is not configured")
        grouped: dict[str, list[DecisionRequest]] = {}
        for request in requests:
            grouped.setdefault(request.episode_id, []).append(request)
        by_id: dict[str, DecisionResult] = {}
        for grouped_requests in grouped.values():
            by_id.update(self._score_episode(grouped_requests))
        return [by_id[request.request_id] for request in requests]

    def _score_episode(self, requests: list[DecisionRequest]) -> dict[str, DecisionResult]:
        questions = {}
        for request in requests:
            questions.update(request.questions)
        started = time.perf_counter()
        payload = self._post(requests[0].state, questions)
        elapsed = (time.perf_counter() - started) * 1000.0
        answers = payload.get("answers") if isinstance(payload, dict) else None
        if not isinstance(answers, dict):
            raise EngineError(f"{self.engine_id} response did not contain answers")
        version = payload.get("model") if isinstance(payload.get("model"), str) else self.model
        share = elapsed / max(1, len(requests))
        results = {}
        for request in requests:
            answer = answers.get(request.concept_id)
            if not isinstance(answer, dict):
                raise EngineError(f"{self.engine_id} omitted a requested concept")
            translated = from_score_answer(answer, source=self.engine_id)
            results[request.request_id] = DecisionResult(
                request_id=request.request_id,
                episode_id=request.episode_id,
                concept_id=request.concept_id,
                concept_version=request.concept_version,
                question_version=request.question_version,
                model_id=self.model,
                model_version=version,
                latency_ms=share,
                raw_response={"model": version, "answer": answer},
                usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
                **translated,
            )
        return results

    def _post(self, state: dict, questions: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = httpx.post(
                f"{self.base_url}/v1/systemone",
                json={"model": self.model, "state": state, "questions": questions},
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise EngineError(f"{self.engine_id} request failed: {type(exc).__name__}") from exc
        if response.status_code in {401, 403}:
            raise EngineError(f"{self.engine_id} authentication failed")
        if response.status_code >= 400:
            raise EngineError(f"{self.engine_id} returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise EngineError(f"{self.engine_id} returned non-JSON") from exc
        if not isinstance(payload, dict):
            raise EngineError(f"{self.engine_id} returned an unexpected payload")
        return payload
