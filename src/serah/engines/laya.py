"""Laya adapter.

Laya 0.3 Router.predict(state, questions) and Router.predict_batch answer
choice, score, and noul questions. Serah asks a 10-level score question.
Weights load on the first score, not during status.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from serah.config import Settings, get_settings
from serah.engines.base import DecisionRequest, DecisionResult, EngineStatus
from serah.engines.translate import from_score_answer
from serah.errors import EngineError, EngineUnavailable


class LayaDecisionEngine:
    engine_id = "laya"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._router: Any = None
        self._lock = threading.Lock()
        self._version: str | None = None

    def status(self) -> EngineStatus:
        try:
            import laya
        except ImportError:
            return EngineStatus("laya", "Laya", "NOT_CONFIGURED", "local", "laya is not installed")
        self._version = getattr(laya, "__version__", None)
        loaded = "weights loaded" if self._router is not None else "weights load on first score"
        return EngineStatus("laya", "Laya", "LOCAL", "local", f"laya {self._version} importable; {loaded}")

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        return self.evaluate_batch([request])[0]

    def evaluate_batch(self, requests: list[DecisionRequest]) -> list[DecisionResult]:
        if not requests:
            return []
        router = self._router_or_raise()
        grouped: dict[str, list[DecisionRequest]] = {}
        for request in requests:
            grouped.setdefault(request.episode_id, []).append(request)
        payload = []
        order: list[list[DecisionRequest]] = []
        for grouped_requests in grouped.values():
            questions: dict = {}
            for request in grouped_requests:
                questions.update(request.questions)
            item: dict[str, Any] = {"state": grouped_requests[0].state, "questions": questions}
            if self.settings.laya_checkpoint:
                item["model"] = self.settings.laya_checkpoint
            payload.append(item)
            order.append(grouped_requests)
        started = time.perf_counter()
        try:
            with self._lock:
                raws = router.predict_batch(payload)
        except Exception as exc:
            raise EngineError(f"laya inference failed: {type(exc).__name__}") from exc
        elapsed = (time.perf_counter() - started) * 1000.0
        by_id: dict[str, DecisionResult] = {}
        for raw, grouped_requests in zip(raws, order, strict=True):
            answers = raw.get("answers") if isinstance(raw, dict) else None
            if not isinstance(answers, dict):
                raise EngineError("laya returned no answers")
            share = elapsed / max(1, len(requests))
            routing = raw.get("routing") if isinstance(raw.get("routing"), dict) else {}
            version = f"laya-{self._version or 'unknown'}"
            if routing.get("model"):
                version = f"{version}+{routing['model']}"
            for request in grouped_requests:
                answer = answers.get(request.concept_id)
                if not isinstance(answer, dict):
                    raise EngineError("laya omitted a requested concept")
                translated = from_score_answer(answer, source="laya")
                by_id[request.request_id] = DecisionResult(
                    request_id=request.request_id,
                    episode_id=request.episode_id,
                    concept_id=request.concept_id,
                    concept_version=request.concept_version,
                    question_version=request.question_version,
                    model_id=version,
                    model_version=version,
                    latency_ms=share,
                    raw_response={"routing": routing, "answer": answer, "usage": raw.get("usage")},
                    usage=raw.get("usage") if isinstance(raw.get("usage"), dict) else None,
                    **translated,
                )
        return [by_id[request.request_id] for request in requests]

    def _router_or_raise(self):
        with self._lock:
            if self._router is not None:
                return self._router
            try:
                import laya
                from laya import Router
            except ImportError as exc:
                raise EngineUnavailable("laya is not installed") from exc
            self._version = getattr(laya, "__version__", None)
            try:
                self._router = Router(device=self.settings.laya_device, preload=False)
            except Exception as exc:
                raise EngineUnavailable(f"laya failed to initialise: {type(exc).__name__}") from exc
            return self._router
