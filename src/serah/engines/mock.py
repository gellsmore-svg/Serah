"""Deterministic lexicon engines. They are instruments for tests and demos."""

from __future__ import annotations

from serah.distributions import metrics, peaked_distribution
from serah.engines.base import DecisionRequest, DecisionResult, EngineStatus
from serah.lexicon import concept_hits, obligation_marker_count

MOCK_MODEL = "mock-lexicon-1"
CONSERVATIVE_MODEL = "mock-lexicon-conservative-1"


class MockDecisionEngine:
    def __init__(self, engine_id: str = "mock", bias: float = 1.0, display_name: str = "Mock"):
        self.engine_id = engine_id
        self.bias = bias
        self.display_name = display_name
        self.model_id = MOCK_MODEL if engine_id == "mock" else CONSERVATIVE_MODEL

    def status(self) -> EngineStatus:
        return EngineStatus(self.engine_id, self.display_name, "AVAILABLE", "mock", "deterministic local instrument")

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        state = request.state
        text = state if isinstance(state, str) else str((state or {}).get("user_evidence") or "")
        if request.concept_id == "compression.obligation_pressure":
            intensity = 78.0 if obligation_marker_count(text) >= 3 else 6.0
        else:
            intensity = float(concept_hits(text).get(request.concept_id, 0.0))
        intensity = max(0.0, min(100.0, intensity * self.bias))
        distribution = peaked_distribution(intensity)
        summary = metrics(distribution)
        stored = {str(bin_value): probability for bin_value, probability in distribution.items()}
        return DecisionResult(
            request_id=request.request_id,
            episode_id=request.episode_id,
            concept_id=request.concept_id,
            concept_version=request.concept_version,
            question_version=request.question_version,
            native_output_type="ordinal_distribution",
            normalisation_method="mock_peaked_instrument_bins",
            raw_response={"bins": stored, "anchor_intensity": intensity, "bias": self.bias},
            distribution=stored,
            expected_intensity=summary.expected,
            provider_confidence=None,
            distribution_concentration=summary.concentration,
            distribution_entropy=summary.entropy,
            modal_bin=summary.modal_bin,
            spread=summary.spread,
            model_id=self.model_id,
            model_version=self.model_id,
            latency_ms=0.0,
            provider_reported={"mock_anchor_intensity": intensity},
        )

    def evaluate_batch(self, requests: list[DecisionRequest]) -> list[DecisionResult]:
        return [self.evaluate(request) for request in requests]
