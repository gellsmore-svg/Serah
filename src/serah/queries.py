"""Read models for the API and CLI. These do not call decision engines."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from serah.errors import SerahError
from serah.models import (
    Annotation,
    DailySnapshot,
    Episode,
    EpisodeMessage,
    Experiment,
    Message,
    ModelObservation,
    ReservoirEventRow,
    SelfRating,
    TaxonomyConcept,
    TaxonomyConceptVersion,
    TaxonomyEvent,
    TaxonomyRelationship,
)


def list_concepts(session: Session, status: str | None = None) -> list[dict]:
    query = select(TaxonomyConcept).order_by(TaxonomyConcept.family, TaxonomyConcept.name)
    if status:
        query = query.where(TaxonomyConcept.status == status)
    return [_concept_summary(session, concept) for concept in session.scalars(query).all()]


def concept_detail(session: Session, concept_id: str) -> dict:
    concept = session.get(TaxonomyConcept, concept_id)
    if concept is None:
        raise SerahError("unknown concept")
    version = _latest_version(session, concept_id)
    relationships = session.scalars(
        select(TaxonomyRelationship).where(
            (TaxonomyRelationship.source_concept_id == concept_id)
            | (TaxonomyRelationship.target_concept_id == concept_id),
            TaxonomyRelationship.removed_on.is_(None),
        )
    ).all()
    events = session.scalars(
        select(TaxonomyEvent)
        .where(TaxonomyEvent.concept_id == concept_id)
        .order_by(TaxonomyEvent.effective_on, TaxonomyEvent.sequence)
    ).all()
    from serah.models import ConceptSupport

    supports = session.scalars(select(ConceptSupport).where(ConceptSupport.concept_id == concept_id)).all()
    episodes = []
    for support in supports:
        episode = session.get(Episode, support.episode_id)
        if episode is None:
            continue
        episodes.append(
            {
                "episode_id": episode.id,
                "timestamp": episode.timestamp_start,
                "excerpt": episode.user_text[:240],
            }
        )
    summary = _concept_summary(session, concept)
    summary.update(
        {
            "definition": version.definition if version else "",
            "inclusion": version.inclusion_guidance if version else "",
            "exclusion": version.exclusion_guidance if version else "",
            "version": version.version if version else None,
            "relationships": [
                {
                    "source": row.source_concept_id,
                    "target": row.target_concept_id,
                    "relation": row.relation_type,
                    "confidence": row.confidence,
                    "created_on": row.created_on,
                    "rationale": row.rationale,
                    "evidence_episode_ids": row.evidence_episode_ids,
                }
                for row in relationships
            ],
            "history": [
                {
                    "event_type": event.event_type,
                    "effective_on": event.effective_on,
                    "actor": event.actor,
                    "rationale": event.rationale,
                    "payload": event.payload,
                    "causal_mode": event.causal_mode,
                }
                for event in events
            ],
            "episodes": episodes,
        }
    )
    return summary


def list_experiments(session: Session) -> list[dict]:
    rows = session.scalars(select(Experiment).order_by(Experiment.created_at)).all()
    return [_experiment(row) for row in rows]


def series(session: Session, experiment_id: str, concept_id: str, mode: str) -> dict:
    experiment = _require_experiment(session, experiment_id)
    if mode not in {"raw", "reservoir"}:
        raise SerahError("mode must be raw or reservoir")
    lines = []
    for engine_id in experiment.engines:
        if mode == "reservoir":
            points = _reservoir_points(session, experiment.id, engine_id, concept_id)
        else:
            points = _raw_points(session, experiment, engine_id, concept_id)
        lines.append({"engine_id": engine_id, "points": points})
    return {"concept_id": concept_id, "mode": mode, "experiment": _experiment(experiment), "series": lines}


def multi_series(session: Session, experiment_id: str, engine_id: str, concept_ids: list[str], mode: str) -> dict:
    experiment = _require_experiment(session, experiment_id)
    lines = []
    for concept_id in concept_ids:
        if mode == "raw":
            points = _raw_points(session, experiment, engine_id, concept_id)
        else:
            points = _reservoir_points(session, experiment.id, engine_id, concept_id)
        lines.append({"concept_id": concept_id, "points": points})
    return {
        "engine_id": engine_id,
        "mode": mode,
        "experiment": _experiment(experiment),
        "series": lines,
    }


def day_view(session: Session, experiment_id: str, engine_id: str, day: str) -> dict:
    experiment = _require_experiment(session, experiment_id)
    snapshot = session.scalar(
        select(DailySnapshot).where(
            DailySnapshot.experiment_id == experiment.id,
            DailySnapshot.engine_id == engine_id,
            DailySnapshot.day == day,
        )
    )
    concepts = {concept.id: concept for concept in session.scalars(select(TaxonomyConcept)).all()}
    states = []
    raw = snapshot.states if snapshot else {}
    for concept_id, payload in sorted(raw.items()):
        concept = concepts.get(concept_id)
        states.append(
            {
                "concept_id": concept_id,
                "name": concept.name if concept else concept_id,
                "family": concept.family if concept else "",
                "level": payload.get("level"),
                "observed": payload.get("observed"),
                "observation_count": payload.get("observation_count", 0),
            }
        )
    episodes = []
    for episode in session.scalars(select(Episode).order_by(Episode.timestamp_start)).all():
        if episode.timestamp_start[:10] != day:
            continue
        episodes.append(
            {
                "episode_id": episode.id,
                "timestamp": episode.timestamp_start,
                "excerpt": episode.user_text[:240],
                "excluded": episode.excluded,
                "direct_states": episode.direct_states,
            }
        )
    observations = []
    for observation in session.scalars(
        select(ModelObservation).where(ModelObservation.engine_id == engine_id)
    ).all():
        episode = session.get(Episode, observation.episode_id)
        if episode is None or not episode.timestamp_start.startswith(day):
            continue
        concept = concepts.get(observation.concept_id)
        observations.append(
            {
                "observation_id": observation.id,
                "concept_id": observation.concept_id,
                "name": concept.name if concept else observation.concept_id,
                "expected_intensity": observation.expected_intensity,
                "episode_id": episode.id,
                "excerpt": episode.user_text[:180],
                "native_output_type": observation.native_output_type,
            }
        )
    annotations = [
        {"id": row.id, "text": row.text}
        for row in session.scalars(select(Annotation).where(Annotation.day == day)).all()
    ]
    ratings = [
        {"id": row.id, "concept_id": row.concept_id, "rating": row.rating, "note": row.note}
        for row in session.scalars(select(SelfRating).where(SelfRating.day == day)).all()
    ]
    return {
        "day": day,
        "engine_id": engine_id,
        "experiment": _experiment(experiment),
        "states": states,
        "episodes": episodes,
        "episode_count": snapshot.episode_count if snapshot else len(episodes),
        "user_word_count": snapshot.user_word_count if snapshot else 0,
        "annotations": annotations,
        "self_ratings": ratings,
        "observations": observations,
        "epistemic": (
            "Levels are derived from this engine, this concept version, and this experiment's "
            "temporal model. They are not a clinical measurement."
        ),
    }


def observation_detail(session: Session, observation_id: str, experiment_id: str | None) -> dict:
    observation = session.get(ModelObservation, observation_id)
    if observation is None:
        raise SerahError("unknown observation")
    episode = session.get(Episode, observation.episode_id)
    version = session.scalar(
        select(TaxonomyConceptVersion).where(
            TaxonomyConceptVersion.concept_id == observation.concept_id,
            TaxonomyConceptVersion.version == observation.concept_version,
        )
    )
    concept = session.get(TaxonomyConcept, observation.concept_id)
    message_links = []
    if episode is not None:
        links = session.scalars(
            select(EpisodeMessage).where(EpisodeMessage.episode_id == episode.id)
        ).all()
        for link in links:
            message = session.get(Message, link.message_id)
            if message is None:
                continue
            message_links.append(
                {
                    "message_id": message.id,
                    "role": message.role,
                    "role_in_episode": link.role_in_episode,
                    "timestamp": message.timestamp,
                    "text": message.text,
                    "on_current_branch": message.on_current_branch,
                }
            )
    events = []
    if experiment_id:
        rows = session.scalars(
            select(ReservoirEventRow).where(
                ReservoirEventRow.experiment_id == experiment_id,
                ReservoirEventRow.observation_id == observation.id,
            )
        ).all()
        events = [
            {
                "event_time": row.event_time,
                "event_kind": row.event_kind,
                "previous_level": row.previous_level,
                "level_after": row.level_after,
                "observation_intensity": row.observation_intensity,
            }
            for row in rows
        ]
    return {
        "observation": {
            "id": observation.id,
            "episode_id": observation.episode_id,
            "concept_id": observation.concept_id,
            "engine_id": observation.engine_id,
            "model_id": observation.model_id,
            "question_version": observation.question_version,
            "concept_version": observation.concept_version,
            "native_output_type": observation.native_output_type,
            "normalisation_method": observation.normalisation_method,
            "distribution": observation.distribution,
            "expected_intensity": observation.expected_intensity,
            "provider_confidence": observation.provider_confidence,
            "distribution_concentration": observation.distribution_concentration,
            "distribution_entropy": observation.distribution_entropy,
            "modal_bin": observation.modal_bin,
            "spread": observation.spread,
            "flagged": observation.flagged,
            "flag_note": observation.flag_note,
            "excluded": observation.excluded,
            "cache_hit": observation.cache_hit,
            "latency_ms": observation.latency_ms,
            "created_at": observation.created_at,
        },
        "episode": None
        if episode is None
        else {
            "id": episode.id,
            "timestamp_start": episode.timestamp_start,
            "user_text": episode.user_text,
            "context_text": episode.context_text,
            "extraction_confidence": episode.extraction_confidence,
            "extractor_id": episode.extractor_id,
            "prompt_version": episode.prompt_version,
            "direct_states": episode.direct_states,
            "bodily_signals": episode.bodily_signals,
            "excluded": episode.excluded,
        },
        "messages": message_links,
        "concept": {
            "id": observation.concept_id,
            "name": concept.name if concept else observation.concept_id,
            "family": concept.family if concept else "",
            "definition": version.definition if version else "",
            "version": observation.concept_version,
        },
        "reservoir_events": events,
    }


def density(session: Session, experiment_id: str | None) -> list[dict]:
    if experiment_id:
        rows = session.scalars(
            select(DailySnapshot)
            .where(DailySnapshot.experiment_id == experiment_id)
            .order_by(DailySnapshot.day)
        ).all()
        seen = {}
        for row in rows:
            seen.setdefault(
                row.day,
                {
                    "day": row.day,
                    "episode_count": row.episode_count,
                    "user_word_count": row.user_word_count,
                    "observation_count": row.observation_count,
                },
            )
        return list(seen.values())
    return []


def _reservoir_points(session, experiment_id, engine_id, concept_id) -> list[dict]:
    rows = session.scalars(
        select(DailySnapshot)
        .where(DailySnapshot.experiment_id == experiment_id, DailySnapshot.engine_id == engine_id)
        .order_by(DailySnapshot.day)
    ).all()
    points = []
    for row in rows:
        payload = (row.states or {}).get(concept_id)
        if not payload:
            continue
        points.append(
            {
                "t": row.day,
                "level": payload.get("level"),
                "observed": payload.get("observed"),
                "observation_count": payload.get("observation_count", 0),
                "evidence_episodes": row.episode_count,
                "user_word_count": row.user_word_count,
            }
        )
    return points


def _raw_points(session, experiment: Experiment, engine_id: str, concept_id: str) -> list[dict]:
    from serah.models import EpisodeRelevance

    rows = session.scalars(
        select(ModelObservation)
        .where(ModelObservation.engine_id == engine_id, ModelObservation.concept_id == concept_id)
        .order_by(ModelObservation.created_at)
    ).all()
    points = []
    for observation in rows:
        episode = session.get(Episode, observation.episode_id)
        if episode is None or episode.excluded or observation.excluded:
            continue
        if experiment.core_scoring_mode == "relevant":
            linked = session.scalar(
                select(EpisodeRelevance).where(
                    EpisodeRelevance.episode_id == episode.id,
                    EpisodeRelevance.concept_id == concept_id,
                )
            )
            if linked is None:
                continue
        points.append(
            {
                "t": episode.timestamp_start,
                "level": observation.expected_intensity,
                "observation_id": observation.id,
                "episode_id": episode.id,
                "concentration": observation.distribution_concentration,
                "concept_version": observation.concept_version,
                "question_version": observation.question_version,
                "native_output_type": observation.native_output_type,
            }
        )
    points.sort(key=lambda item: item["t"])
    return points


def _concept_summary(session: Session, concept: TaxonomyConcept) -> dict:
    version = _latest_version(session, concept.id)
    return {
        "id": concept.id,
        "name": concept.name,
        "family": concept.family,
        "status": concept.status,
        "locked": concept.locked,
        "first_seen": concept.first_observed_on,
        "support_count": concept.support_count,
        "version": version.version if version else None,
        "definition": version.definition if version else "",
    }


def _latest_version(session: Session, concept_id: str) -> TaxonomyConceptVersion | None:
    return session.scalar(
        select(TaxonomyConceptVersion)
        .where(TaxonomyConceptVersion.concept_id == concept_id)
        .order_by(TaxonomyConceptVersion.version.desc())
    )


def _experiment(row: Experiment) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "engines": row.engines,
        "decay_type": row.decay_type,
        "half_life_hours": row.half_life_hours,
        "reservoir_update": row.reservoir_update,
        "activation_gain": row.activation_gain,
        "core_scoring_mode": row.core_scoring_mode,
        "created_at": row.created_at,
        "notes": row.notes,
    }


def _require_experiment(session: Session, experiment_id: str) -> Experiment:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise SerahError("unknown experiment")
    return experiment
