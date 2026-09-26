"""Score episodes with one engine. Observations are immutable and cached."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from serah.clock import utc_now
from serah.config import Settings
from serah.engines.base import DecisionEngine, DecisionRequest, DecisionResult
from serah.errors import EngineError, EngineUnavailable
from serah.ids import new_id
from serah.models import (
    Episode,
    EpisodeRelevance,
    InferenceCache,
    ModelObservation,
    StageMark,
    TaxonomyConcept,
    TaxonomyConceptVersion,
)
from serah.questions import ensure_question
from serah.temporal import UTC, utc_day


def evidence_hash(user_text: str, context_text: str) -> str:
    return hashlib.sha256(f"{user_text}\n---\n{context_text}".encode()).hexdigest()


def cache_key(
    engine_id: str,
    fingerprint: str,
    digest: str,
    concept_id: str,
    concept_version: int,
    question_version: int,
    instructions: str,
) -> str:
    payload = json.dumps(
        {
            "engine_id": engine_id,
            "fingerprint": fingerprint,
            "evidence_hash": digest,
            "concept_id": concept_id,
            "concept_version": concept_version,
            "question_version": question_version,
            "instructions": instructions,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def fingerprint_for(engine_id: str, settings: Settings) -> str:
    if engine_id == "mock":
        return "bias:1"
    if engine_id == "mock_conservative":
        return "bias:0.82"
    if engine_id == "laya":
        return f"device:{settings.laya_device}|checkpoint:{settings.laya_checkpoint}"
    if engine_id == "jev":
        return f"model:{settings.jev_model}|url:{settings.jev_base_url}"
    if engine_id == "kai":
        return f"model:{settings.kai_model}|url:{settings.kai_base_url}"
    if engine_id == "decider":
        return f"model:{settings.decider_model}|url:{settings.decider_base_url}"
    if engine_id == "keziah":
        return f"model:{settings.keziah_model}|url:{settings.keziah_base_url}"
    if engine_id == "llm_baseline":
        return f"model:{settings.llm_model}|url:{settings.llm_base_url}"
    return engine_id


def score_engine(
    session: Session,
    engine: DecisionEngine,
    settings: Settings,
    mode: str,
    run_id: str,
) -> dict:
    status = engine.status()
    if status.availability == "NOT_CONFIGURED":
        raise EngineUnavailable(status.detail)
    if mode not in {"relevant", "all-core"}:
        raise ValueError("scoring mode must be relevant or all-core")
    episodes = session.scalars(
        select(Episode).where(Episode.excluded.is_(False)).order_by(Episode.timestamp_start, Episode.id)
    ).all()
    fingerprint = fingerprint_for(engine.engine_id, settings)
    stats = {"scored": 0, "cached": 0, "skipped": 0, "failed": 0}
    for episode in episodes:
        for concept_id in _targets(session, episode, mode):
            stage = f"score:{engine.engine_id}:{mode}"
            key = f"{episode.id}:{concept_id}"
            if _marked(session, stage, key):
                stats["skipped"] += 1
                continue
            day = _episode_day(episode)
            version = _version_on(session, concept_id, day)
            if version is None:
                continue
            question = ensure_question(session, concept_id)
            if question.concept_version != version.version:
                question = _question_for_version(session, concept_id, version.version) or question
            digest = evidence_hash(episode.user_text, episode.context_text)
            key_hash = cache_key(
                engine.engine_id,
                fingerprint,
                digest,
                concept_id,
                version.version,
                question.version,
                question.instructions,
            )
            already = session.scalar(
                select(ModelObservation).where(
                    ModelObservation.episode_id == episode.id,
                    ModelObservation.concept_id == concept_id,
                    ModelObservation.engine_id == engine.engine_id,
                    ModelObservation.concept_version == version.version,
                    ModelObservation.question_version == question.version,
                )
            )
            if already is not None:
                if not _marked(session, stage, key):
                    session.add(
                        StageMark(
                            id=new_id(),
                            stage=stage,
                            key=key,
                            run_id=run_id,
                            created_at=utc_now(),
                        )
                    )
                stats["skipped"] += 1
                continue
            request = DecisionRequest(
                request_id=new_id(),
                engine_id=engine.engine_id,
                episode_id=episode.id,
                concept_id=concept_id,
                concept_version=version.version,
                question_version=question.version,
                state=_engine_state(engine.engine_id, episode),
                questions={
                    concept_id: {
                        "type": "score",
                        "instructions": question.instructions,
                        "criteria": question.criteria,
                    }
                },
                evidence_hash=digest,
                cache_key=key_hash,
            )
            cached = session.get(InferenceCache, key_hash)
            if cached is not None:
                _store_observation(
                    session, request, _result_from_cache(request, cached.result), run_id, mode, cache_hit=True
                )
                stats["cached"] += 1
                stats["scored"] += 1
                session.commit()
                continue
            try:
                result = engine.evaluate_batch([request])[0]
            except EngineUnavailable:
                raise
            except EngineError:
                stats["failed"] += 1
                session.commit()
                raise
            session.add(
                InferenceCache(
                    request_hash=request.cache_key,
                    engine_id=engine.engine_id,
                    model_id=result.model_id,
                    created_at=utc_now(),
                    result=_cache_payload(result),
                    latency_ms=result.latency_ms,
                )
            )
            _store_observation(session, request, result, run_id, mode, cache_hit=False)
            stats["scored"] += 1
            session.commit()
    return stats


def _engine_state(engine_id: str, episode: Episode):
    """System-1 models score the user text alone. The LLM baseline may see context."""
    if engine_id == "llm_baseline":
        return {
            "user_evidence": episode.user_text,
            "context": episode.context_text,
            "evidence_rule": (
                "Judge only user_evidence. Context may explain what the user is answering. "
                "Do not score an assistant interpretation unless the user endorses it."
            ),
        }
    return episode.user_text


def _targets(session: Session, episode: Episode, mode: str) -> list[str]:
    from serah.taxonomy import active_ids

    day = _episode_day(episode)
    active = active_ids(session, day)
    relevant = [
        concept_id
        for concept_id in session.scalars(
            select(EpisodeRelevance.concept_id).where(EpisodeRelevance.episode_id == episode.id)
        ).all()
        if concept_id in active
    ]
    if mode == "relevant":
        return sorted(set(relevant))
    locked = {
        concept_id
        for concept_id in session.scalars(
            select(TaxonomyConcept.id).where(TaxonomyConcept.locked.is_(True))
        ).all()
    }
    return sorted((locked & active) | set(relevant))


def _version_on(session: Session, concept_id: str, day: str) -> TaxonomyConceptVersion | None:
    return session.scalar(
        select(TaxonomyConceptVersion)
        .where(TaxonomyConceptVersion.concept_id == concept_id, TaxonomyConceptVersion.effective_on <= day)
        .order_by(TaxonomyConceptVersion.version.desc())
    )


def _question_for_version(session: Session, concept_id: str, concept_version: int):
    from serah.models import MeasurementQuestion

    return session.scalar(
        select(MeasurementQuestion).where(
            MeasurementQuestion.concept_id == concept_id,
            MeasurementQuestion.concept_version == concept_version,
        )
    )


def _episode_day(episode: Episode) -> str:
    moment = datetime.fromisoformat(episode.timestamp_start)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return utc_day(moment).isoformat()


def _marked(session: Session, stage: str, key: str) -> bool:
    return session.scalar(select(StageMark).where(StageMark.stage == stage, StageMark.key == key)) is not None


def _store_observation(
    session: Session,
    request: DecisionRequest,
    result: DecisionResult,
    run_id: str,
    mode: str,
    *,
    cache_hit: bool,
) -> None:
    existing = session.scalar(
        select(ModelObservation).where(
            ModelObservation.episode_id == request.episode_id,
            ModelObservation.concept_id == request.concept_id,
            ModelObservation.engine_id == request.engine_id,
            ModelObservation.concept_version == request.concept_version,
            ModelObservation.question_version == request.question_version,
        )
    )
    if existing is None:
        session.add(
            ModelObservation(
                id=new_id(),
                episode_id=request.episode_id,
                concept_id=request.concept_id,
                concept_version=request.concept_version,
                engine_id=request.engine_id,
                model_id=result.model_id,
                question_version=request.question_version,
                native_output_type=result.native_output_type,
                normalisation_method=result.normalisation_method,
                raw_response=result.raw_response,
                distribution=result.distribution,
                expected_intensity=result.expected_intensity,
                provider_confidence=result.provider_confidence,
                distribution_concentration=result.distribution_concentration,
                distribution_entropy=result.distribution_entropy,
                modal_bin=result.modal_bin,
                spread=result.spread,
                provider_reported=result.provider_reported,
                processing_run_id=run_id,
                created_at=utc_now(),
                latency_ms=result.latency_ms,
                cache_hit=cache_hit,
                evidence_hash=request.evidence_hash,
            )
        )
    stage = f"score:{request.engine_id}:{mode}"
    key = f"{request.episode_id}:{request.concept_id}"
    if not _marked(session, stage, key):
        session.add(
            StageMark(
                id=new_id(),
                stage=stage,
                key=key,
                run_id=run_id,
                created_at=utc_now(),
            )
        )


def _cache_payload(result: DecisionResult) -> dict:
    return {
        "native_output_type": result.native_output_type,
        "normalisation_method": result.normalisation_method,
        "raw_response": result.raw_response,
        "distribution": result.distribution,
        "expected_intensity": result.expected_intensity,
        "provider_confidence": result.provider_confidence,
        "distribution_concentration": result.distribution_concentration,
        "distribution_entropy": result.distribution_entropy,
        "modal_bin": result.modal_bin,
        "spread": result.spread,
        "model_id": result.model_id,
        "model_version": result.model_version,
        "provider_reported": result.provider_reported,
        "latency_ms": result.latency_ms,
    }


def _result_from_cache(request: DecisionRequest, payload: dict) -> DecisionResult:
    return DecisionResult(
        request_id=request.request_id,
        episode_id=request.episode_id,
        concept_id=request.concept_id,
        concept_version=request.concept_version,
        question_version=request.question_version,
        native_output_type=payload["native_output_type"],
        normalisation_method=payload["normalisation_method"],
        raw_response=payload.get("raw_response") or {},
        distribution=payload.get("distribution"),
        expected_intensity=payload.get("expected_intensity"),
        provider_confidence=payload.get("provider_confidence"),
        distribution_concentration=payload.get("distribution_concentration"),
        distribution_entropy=payload.get("distribution_entropy"),
        modal_bin=payload.get("modal_bin"),
        spread=payload.get("spread"),
        model_id=payload.get("model_id") or request.engine_id,
        model_version=payload.get("model_version"),
        latency_ms=0.0,
        provider_reported=payload.get("provider_reported") or {},
        cache_hit=True,
    )
