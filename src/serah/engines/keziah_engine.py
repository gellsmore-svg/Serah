"""Score through a Keziah server.

Keziah's synchronous call is POST /v1/systemone. The job result carries the
System-1 answers at ``response["answers"]``. Serah uses the keziah client when
that package is installed, and the same JSON body over httpx otherwise.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from serah.config import Settings, get_settings
from serah.engines.base import DecisionRequest, DecisionResult, EngineStatus
from serah.engines.translate import from_score_answer
from serah.errors import EngineError, EngineUnavailable


class KeziahDecisionEngine:
    engine_id = "keziah"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def status(self) -> EngineStatus:
        if not self.settings.keziah_base_url:
            return EngineStatus(
                "keziah",
                "Keziah",
                "NOT_CONFIGURED",
                "remote",
                "SERAH_KEZIAH_BASE_URL is not set",
            )
        return EngineStatus(
            "keziah",
            "Keziah",
            "REMOTE",
            "remote",
            f"{self.settings.keziah_base_url} model {self.settings.keziah_model}",
        )

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        return self.evaluate_batch([request])[0]

    def evaluate_batch(self, requests: list[DecisionRequest]) -> list[DecisionResult]:
        if not self.settings.keziah_base_url:
            raise EngineUnavailable("Keziah is not configured")
        grouped: dict[str, list[DecisionRequest]] = {}
        for request in requests:
            grouped.setdefault(request.episode_id, []).append(request)
        by_id: dict[str, DecisionResult] = {}
        for episode_requests in grouped.values():
            by_id.update(self._score_episode(episode_requests))
        return [by_id[request.request_id] for request in requests]

    def _score_episode(self, requests: list[DecisionRequest]) -> dict[str, DecisionResult]:
        questions: dict[str, Any] = {}
        for request in requests:
            questions.update(request.questions)
        state = requests[0].state
        started = time.perf_counter()
        payload = self._systemone(state, questions)
        elapsed = (time.perf_counter() - started) * 1000.0
        if payload.get("status") not in {None, "succeeded"}:
            raise EngineError("Keziah did not succeed")
        body = payload.get("response") if isinstance(payload.get("response"), dict) else {}
        answers = body.get("answers") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            raise EngineError("Keziah response did not contain answers")
        version = payload.get("model_version") or self.settings.keziah_model
        share = elapsed / max(1, len(requests))
        results = {}
        for request in requests:
            answer = answers.get(request.concept_id)
            if not isinstance(answer, dict):
                raise EngineError("Keziah omitted a requested concept")
            translated = from_score_answer(answer, source="keziah")
            results[request.request_id] = DecisionResult(
                request_id=request.request_id,
                episode_id=request.episode_id,
                concept_id=request.concept_id,
                concept_version=request.concept_version,
                question_version=request.question_version,
                model_id=str(payload.get("resolved_model") or self.settings.keziah_model),
                model_version=str(version),
                latency_ms=share,
                raw_response={"answer": answer, "job_id": payload.get("job_id")},
                **translated,
            )
        return results

    def _systemone(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        model = self.settings.keziah_model
        timeout_s = self.settings.keziah_timeout_s
        try:
            from keziah import Client
        except ImportError:
            Client = None  # type: ignore[assignment]
        if Client is not None:
            with Client(self.settings.keziah_base_url or "", api_key=self.settings.keziah_api_key, timeout=timeout_s) as client:
                result = client.systemone(
                    model=model,
                    state=state,
                    questions=questions,
                    timeout_s=timeout_s,
                    client_id="serah",
                )
            return {
                "status": result.status,
                "job_id": result.job_id,
                "resolved_model": result.resolved_model,
                "model_version": result.model_version,
                "response": result.response,
            }
        headers = {"Content-Type": "application/json"}
        if self.settings.keziah_api_key:
            headers["Authorization"] = f"Bearer {self.settings.keziah_api_key}"
        try:
            response = httpx.post(
                f"{self.settings.keziah_base_url.rstrip('/')}/v1/systemone",
                json={
                    "model": model,
                    "state": state,
                    "questions": questions,
                    "timeout_s": timeout_s,
                    "client_id": "serah",
                },
                headers=headers,
                timeout=timeout_s + 5,
            )
        except httpx.HTTPError as exc:
            raise EngineError(f"Keziah request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise EngineError(f"Keziah returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise EngineError("Keziah returned non-JSON") from exc
        if not isinstance(payload, dict):
            raise EngineError("Keziah returned an unexpected payload")
        return payload
