"""Engine registry. One missing provider does not remove the others."""

from __future__ import annotations

import os

from serah.config import Settings, get_settings
from serah.engines.base import DecisionEngine, EngineStatus
from serah.engines.decider_local import DeciderLocalEngine
from serah.engines.laya import LayaDecisionEngine
from serah.engines.llm_baseline import LLMBaselineEngine
from serah.engines.mock import MockDecisionEngine
from serah.engines.systemone import SystemOneHttpEngine


def _secret(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def build_engines(settings: Settings | None = None) -> dict[str, DecisionEngine]:
    settings = settings or get_settings()
    jev = SystemOneHttpEngine(
        "jev",
        "Jev",
        settings.jev_base_url,
        _secret("TYPESAFE_API_KEY", "JEV_API_KEY"),
        settings.jev_model,
        key_required=True,
    )
    kai = SystemOneHttpEngine(
        "kai",
        "Kai",
        settings.kai_base_url,
        settings.kai_api_key or _secret("KAI_API_KEY"),
        settings.kai_model,
        key_required=False,
    )
    if settings.decider_base_url:
        decider: DecisionEngine = SystemOneHttpEngine(
            "decider",
            "Decider",
            settings.decider_base_url,
            settings.decider_api_key or _secret("DECIDER_API_KEY"),
            settings.decider_model or "decider",
            key_required=False,
        )
    else:
        decider = DeciderLocalEngine(settings)
    return {
        "mock": MockDecisionEngine("mock", 1.0, "Mock"),
        "mock_conservative": MockDecisionEngine("mock_conservative", 0.82, "Mock conservative"),
        "laya": LayaDecisionEngine(settings),
        "jev": jev,
        "kai": kai,
        "decider": decider,
        "llm_baseline": LLMBaselineEngine(settings),
    }


def engine_statuses(settings: Settings | None = None) -> list[EngineStatus]:
    return [engine.status() for engine in build_engines(settings).values()]


def require_engine(engine_id: str, settings: Settings | None = None) -> DecisionEngine:
    engines = build_engines(settings)
    if engine_id not in engines:
        known = ", ".join(sorted(engines))
        raise KeyError(f"unknown engine {engine_id}. Known engines: {known}")
    return engines[engine_id]
