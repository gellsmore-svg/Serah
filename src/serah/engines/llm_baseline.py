"""Optional LLM measurement baseline. It is not the main scoring architecture."""

from __future__ import annotations

import time

from serah.config import Settings, get_settings
from serah.engines.base import DecisionRequest, DecisionResult, EngineStatus
from serah.engines.translate import from_bin_distribution
from serah.errors import CuratorError, EngineError, EngineUnavailable
from serah.llm_client import ChatClient, complete_model
from serah.prompts import load_prompt
from serah.schemas import LLMDistributionPayload


class LLMBaselineEngine:
    engine_id = "llm_baseline"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def status(self) -> EngineStatus:
        if not self.settings.llm_base_url or not self.settings.llm_model:
            return EngineStatus(
                "llm_baseline",
                "LLM baseline",
                "NOT_CONFIGURED",
                "remote",
                "SERAH_LLM_BASE_URL and SERAH_LLM_MODEL are not set",
            )
        return EngineStatus(
            "llm_baseline",
            "LLM baseline",
            "REMOTE",
            "remote",
            f"configured model {self.settings.llm_model}",
        )

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        return self.evaluate_batch([request])[0]

    def evaluate_batch(self, requests: list[DecisionRequest]) -> list[DecisionResult]:
        if not self.settings.llm_base_url or not self.settings.llm_model:
            raise EngineUnavailable("llm baseline is not configured")
        client = ChatClient(
            self.settings.llm_base_url,
            self.settings.llm_model,
            self.settings.resolved_llm_key(),
        )
        system = load_prompt("measurement_question", "v1.md")
        results = []
        for request in requests:
            started = time.perf_counter()
            import json

            user = json.dumps(
                {
                    "state": request.state,
                    "question": request.questions.get(request.concept_id, {}),
                },
                ensure_ascii=False,
            )
            try:
                payload = complete_model(client, system, user, LLMDistributionPayload)
            except CuratorError as exc:
                raise EngineError("llm baseline did not return a valid measurement") from exc
            translated = _translate(payload)
            results.append(
                DecisionResult(
                    request_id=request.request_id,
                    episode_id=request.episode_id,
                    concept_id=request.concept_id,
                    concept_version=request.concept_version,
                    question_version=request.question_version,
                    model_id=self.settings.llm_model,
                    model_version=self.settings.llm_model,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    raw_response=payload.model_dump(),
                    **translated,
                )
            )
        return results


def _translate(payload: LLMDistributionPayload) -> dict:
    if payload.bins:
        return from_bin_distribution(payload.bins, method="llm_instrument_bins")
    if payload.intensity is None:
        raise EngineError("llm baseline returned neither bins nor an intensity")
    intensity = max(0.0, min(100.0, float(payload.intensity)))
    return {
        "native_output_type": "scalar_score",
        "normalisation_method": "llm_scalar_0_100",
        "distribution": None,
        "expected_intensity": intensity,
        "provider_confidence": None,
        "distribution_concentration": None,
        "distribution_entropy": None,
        "modal_bin": None,
        "spread": None,
        "provider_reported": {"rationale": payload.rationale},
    }


