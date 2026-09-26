"""Explicit human edits. Model output rows are kept."""

from __future__ import annotations

from sqlalchemy.orm import Session

from serah.clock import utc_now
from serah.errors import SerahError
from serah.ids import new_id
from serah.models import (
    Annotation,
    AuditEvent,
    Episode,
    ModelObservation,
    SelfRating,
    TaxonomyConcept,
    TaxonomyConceptVersion,
    TaxonomyEvent,
)
from serah.questions import ensure_question
from serah.taxonomy import CONCEPT_ID_RE, revise_definition


def add_concept(
    session: Session,
    *,
    taxonomy_id: str,
    name: str,
    family: str,
    definition: str,
    inclusion: str,
    exclusion: str,
    status: str,
    day: str,
    rationale: str,
) -> TaxonomyConcept:
    if not CONCEPT_ID_RE.match(taxonomy_id):
        raise SerahError("concept id must look like emotion.slug or compression.slug")
    if family not in {"emotion", "compression"} or status not in {"proposed", "active"}:
        raise SerahError("family or status is not valid")
    if session.get(TaxonomyConcept, taxonomy_id) is not None:
        raise SerahError("concept already exists")
    concept = TaxonomyConcept(
        id=taxonomy_id,
        name=name,
        family=family,
        status="proposed",
        locked=False,
        first_observed_on=day,
        support_count=0,
        confidence=None,
        nearest_concepts=[],
        rationale=rationale,
        created_at=utc_now(),
    )
    session.add(concept)
    session.add(
        TaxonomyConceptVersion(
            id=new_id(),
            concept_id=taxonomy_id,
            version=1,
            definition=definition,
            inclusion_guidance=inclusion,
            exclusion_guidance=exclusion,
            source="human",
            effective_on=day,
            created_at=utc_now(),
        )
    )
    _taxonomy_event(session, "CONCEPT_PROPOSED", taxonomy_id, {"status": "proposed", "name": name}, day, rationale)
    if status == "active":
        concept.status = "active"
        _taxonomy_event(session, "CONCEPT_ACTIVATED", taxonomy_id, {"status": "active"}, day, rationale)
    session.flush()
    ensure_question(session, taxonomy_id)
    _audit(session, "concept_added", "concept", taxonomy_id, {"status": concept.status}, rationale)
    session.commit()
    return concept


def set_candidate_status(session: Session, concept_id: str, status: str, rationale: str, day: str) -> None:
    concept = session.get(TaxonomyConcept, concept_id)
    if concept is None:
        raise SerahError("unknown concept")
    if concept.locked and status in {"rejected", "deprecated", "dormant"}:
        raise SerahError("locked concepts stay in the taxonomy")
    if status not in {"active", "rejected", "dormant", "candidate"}:
        raise SerahError("unsupported status")
    previous = concept.status
    concept.status = status
    event_type = "CONCEPT_ACTIVATED" if status == "active" else "CONCEPT_DEPRECATED"
    if status == "candidate":
        event_type = "CONCEPT_STATUS_CHANGED"
    if status == "active" and previous == "deprecated":
        event_type = "CONCEPT_REACTIVATED"
    _taxonomy_event(session, event_type, concept_id, {"status": status, "previous": previous}, day, rationale)
    _audit(session, "concept_status", "concept", concept_id, {"status": status}, rationale)
    session.commit()


def merge_concepts(session: Session, source_id: str, target_id: str, rationale: str, day: str) -> None:
    source = session.get(TaxonomyConcept, source_id)
    target = session.get(TaxonomyConcept, target_id)
    if source is None or target is None:
        raise SerahError("unknown concept")
    if source.locked:
        raise SerahError("locked concepts cannot be merged away")
    source.status = "deprecated"
    _taxonomy_event(
        session,
        "CONCEPT_MERGED",
        source_id,
        {"target_concept_id": target_id, "status": "deprecated"},
        day,
        rationale,
    )
    _audit(session, "concept_merged", "concept", source_id, {"target": target_id}, rationale)
    session.commit()


def split_concept(
    session: Session,
    source_id: str,
    taxonomy_id: str,
    name: str,
    definition: str,
    inclusion: str,
    exclusion: str,
    rationale: str,
    day: str,
) -> TaxonomyConcept:
    if session.get(TaxonomyConcept, source_id) is None:
        raise SerahError("unknown concept")
    created = add_concept(
        session,
        taxonomy_id=taxonomy_id,
        name=name,
        family="emotion",
        definition=definition,
        inclusion=inclusion,
        exclusion=exclusion,
        status="active",
        day=day,
        rationale=rationale,
    )
    _taxonomy_event(
        session,
        "CONCEPT_SPLIT",
        source_id,
        {"new_concept_id": taxonomy_id},
        day,
        rationale,
    )
    session.commit()
    return created


def exclude_episode(session: Session, episode_id: str, note: str) -> None:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise SerahError("unknown episode")
    episode.excluded = True
    episode.exclusion_note = note
    _audit(session, "episode_excluded", "episode", episode_id, {}, note)
    session.commit()


def flag_observation(session: Session, observation_id: str, note: str, exclude: bool) -> None:
    observation = session.get(ModelObservation, observation_id)
    if observation is None:
        raise SerahError("unknown observation")
    observation.flagged = True
    observation.flag_note = note
    observation.excluded = exclude
    _audit(
        session,
        "observation_flagged",
        "observation",
        observation_id,
        {"excluded": exclude},
        note,
    )
    session.commit()


def add_annotation(session: Session, day: str, text: str) -> Annotation:
    row = Annotation(id=new_id(), day=day, text=text, created_at=utc_now())
    session.add(row)
    _audit(session, "annotation_created", "day", day, {}, text)
    session.commit()
    return row


def add_self_rating(session: Session, day: str, concept_id: str, rating: float, note: str) -> SelfRating:
    if session.get(TaxonomyConcept, concept_id) is None:
        raise SerahError("unknown concept")
    if rating < 0 or rating > 100:
        raise SerahError("self rating must be between 0 and 100")
    row = SelfRating(
        id=new_id(),
        day=day,
        concept_id=concept_id,
        rating=rating,
        note=note,
        created_at=utc_now(),
    )
    session.add(row)
    _audit(session, "self_rating_created", "concept", concept_id, {"day": day, "rating": rating}, note)
    session.commit()
    return row


def human_revise(session: Session, concept_id: str, definition: str, inclusion: str, exclusion: str, rationale: str, day: str):
    revise_definition(
        session,
        concept_id,
        definition,
        inclusion,
        exclusion,
        rationale,
        actor="human",
        day=day,
        run_id=None,
        model_id=None,
    )
    _audit(session, "definition_revised", "concept", concept_id, {}, rationale)
    session.commit()


def _taxonomy_event(session, event_type, concept_id, payload, day, rationale) -> None:
    session.add(
        TaxonomyEvent(
            id=new_id(),
            event_type=event_type,
            concept_id=concept_id,
            payload=payload,
            effective_on=day,
            causal_mode="causal",
            created_at=utc_now(),
            actor="human",
            model_id=None,
            prompt_version=None,
            rationale=rationale,
            confidence=None,
            processing_run_id=None,
            sequence=0,
        )
    )


def _audit(session, kind, target_type, target_id, payload, note) -> None:
    session.add(
        AuditEvent(
            id=new_id(),
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            note=note,
            created_at=utc_now(),
        )
    )
