"""Engine contract. Provider payloads do not leak past DecisionResult."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class EngineStatus:
    engine_id: str
    display_name: str
    availability: str
    kind: str
    detail: str


@dataclass
class DecisionRequest:
    request_id: str
    episode_id: str
    concept_id: str
    concept_version: int
    question_version: int
    engine_id: str
    state: dict
    questions: dict
    evidence_hash: str
    cache_key: str


@dataclass
class DecisionResult:
    request_id: str
    episode_id: str
    concept_id: str
    concept_version: int
    question_version: int
    native_output_type: str
    normalisation_method: str
    raw_response: dict
    distribution: dict[str, float] | None
    expected_intensity: float | None
    provider_confidence: float | None
    distribution_concentration: float | None
    distribution_entropy: float | None
    modal_bin: float | None
    spread: float | None
    model_id: str
    model_version: str | None
    latency_ms: float
    provider_reported: dict = field(default_factory=dict)
    usage: dict | None = None
    cache_hit: bool = False


class DecisionEngine(Protocol):
    engine_id: str

    def status(self) -> EngineStatus: ...

    def evaluate(self, request: DecisionRequest) -> DecisionResult: ...

    def evaluate_batch(self, requests: list[DecisionRequest]) -> list[DecisionResult]: ...


def sequential_batch(engine: DecisionEngine, requests: list[DecisionRequest]) -> list[DecisionResult]:
    return [engine.evaluate(request) for request in requests]
