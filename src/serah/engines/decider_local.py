"""Optional local Decider adapter.

The documented Python entry point is ``decider.infer.Decider`` and
``Decider.system_one(state, questions)``, the same shape as POST /v1/systemone.
Serah does not download weights. If the package or DECIDER_MODEL is absent,
the engine reports NOT_CONFIGURED.
"""

from __future__ import annotations

import time

from serah.config import Settings, get_settings
from serah.engines.base import DecisionRequest, DecisionResult, EngineStatus
from serah.engines.translate import from_score_answer
from serah.errors import EngineError, EngineUnavailable


class DeciderLocalEngine:
    engine_id = "decider"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._model = None

    def status(self) -> EngineStatus:
        if self.settings.decider_base_url:
            return EngineStatus(
                "decider",
                "Decider",
                "REMOTE",
                "remote",
                "DECIDER_BASE_URL is set; the HTTP adapter is used instead",
            )
        if not self.settings.decider_model:
            return EngineStatus(
                "decider",
                "Decider",
                "NOT_CONFIGURED",
                "local",
                "DECIDER_MODEL is not set and no DECIDER_BASE_URL is configured",
            )
        try:
            import decider.infer  # noqa: F401
        except ImportError:
            return EngineStatus("decider", "Decider", "NOT_CONFIGURED", "local", "decider is not installed")
        return EngineStatus(
            "decider",
            "Decider",
            "LOCAL",
            "local",
            f"decider.infer.Decider available for {self.settings.decider_model}",
        )

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        return self.evaluate_batch([request])[0]

    def evaluate_batch(self, requests: list[DecisionRequest]) -> list[DecisionResult]:
        model = self._load()
        results = []
        for request in requests:
            started = time.perf_counter()
            try:
                raw = model.system_one(request.state, request.questions)
            except Exception as exc:
                raise EngineError(f"decider inference failed: {type(exc).__name__}") from exc
            payload = raw if isinstance(raw, dict) else {"answers": getattr(raw, "answers", None)}
            answers = payload.get("answers") if isinstance(payload, dict) else None
            if not isinstance(answers, dict) or not isinstance(answers.get(request.concept_id), dict):
                raise EngineError("decider response did not contain the requested score")
            translated = from_score_answer(answers[request.concept_id], source="decider")
            results.append(
                DecisionResult(
                    request_id=request.request_id,
                    episode_id=request.episode_id,
                    concept_id=request.concept_id,
                    concept_version=request.concept_version,
                    question_version=request.question_version,
                    model_id=self.settings.decider_model or "decider",
                    model_version=self.settings.decider_model,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    raw_response={"answer": answers[request.concept_id]},
                    **translated,
                )
            )
        return results

    def _load(self):
        if self._model is not None:
            return self._model
        if not self.settings.decider_model:
            raise EngineUnavailable("DECIDER_MODEL is not set")
        try:
            from decider.infer import Decider
        except ImportError as exc:
            raise EngineUnavailable("decider is not installed") from exc
        try:
            self._model = Decider(self.settings.decider_model)
        except Exception as exc:
            raise EngineUnavailable(f"decider failed to initialise: {type(exc).__name__}") from exc
        return self._model
