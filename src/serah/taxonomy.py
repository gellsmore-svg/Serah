"""Causal taxonomy events, candidate lifecycle, and reconstruction.

The live tables are the state after the latest causal day. Events are the
history. A date T is reconstructed only from events with effective_on <= T
and causal_mode = causal.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from serah.clock import utc_now
from serah.config import Settings
from serah.core_taxonomy import OBLIGATION_PRESSURE, RELATION_TYPES
from serah.errors import CuratorError, SerahError
from serah.ids import new_id
from serah.lexicon import concept_hits, obligation_marker_count
from serah.llm_client import ChatClient, complete_model
from serah.models import (
    ConceptSupport,
    Episode,
    EpisodeRelevance,
    TaxonomyConcept,
    TaxonomyConceptVersion,
    TaxonomyEvent,
    TaxonomyRelationship,
)
from serah.prompts import load_prompt
from serah.questions import ensure_question
from serah.schemas import (
    ConceptProposal,
    RelationshipProposal,
    RelevantConcept,
    TaxonomyReviewPayload,
)

CONCEPT_ID_RE = re.compile(r"^(emotion|compression)\.[a-z][a-z0-9_]{1,64}$")
PROMPT_VERSION = "taxonomy_review/v1"


def reconstruct(session: Session, day: str) -> dict[str, dict]:
    events = session.scalars(
        select(TaxonomyEvent)
        .where(TaxonomyEvent.effective_on <= day, TaxonomyEvent.causal_mode == "causal")
        .order_by(TaxonomyEvent.effective_on, TaxonomyEvent.sequence, TaxonomyEvent.id)
    ).all()
    state: dict[str, dict] = {}
    for event in events:
        _apply_reconstructed(state, event)
    return state


def _apply_reconstructed(state: dict[str, dict], event: TaxonomyEvent) -> None:
    payload = event.payload or {}
    concept_id = event.concept_id
    if event.event_type == "CONCEPT_PROPOSED" and concept_id:
        state[concept_id] = {**payload, "status": payload.get("status", "proposed"), "id": concept_id}
    elif event.event_type == "CONCEPT_ACTIVATED" and concept_id:
        current = state.get(concept_id, {"id": concept_id})
        current.update(payload)
        current["status"] = "active"
        state[concept_id] = current
    elif event.event_type == "CONCEPT_STATUS_CHANGED" and concept_id and concept_id in state:
        state[concept_id]["status"] = payload.get("status", state[concept_id].get("status"))
    elif event.event_type == "CONCEPT_DEFINITION_REVISED" and concept_id and concept_id in state:
        state[concept_id].update(
            {
                "definition": payload.get("definition", state[concept_id].get("definition")),
                "version": payload.get("version", state[concept_id].get("version")),
                "inclusion_guidance": payload.get(
                    "inclusion_guidance", state[concept_id].get("inclusion_guidance")
                ),
                "exclusion_guidance": payload.get(
                    "exclusion_guidance", state[concept_id].get("exclusion_guidance")
                ),
            }
        )
    elif event.event_type == "CONCEPT_DEPRECATED" and concept_id and concept_id in state:
        state[concept_id]["status"] = payload.get("status", "deprecated")
    elif event.event_type == "CONCEPT_MERGED" and concept_id and concept_id in state:
        state[concept_id]["status"] = "deprecated"
        state[concept_id]["merged_into"] = payload.get("target_concept_id")
    elif event.event_type == "CONCEPT_RENAMED" and concept_id and concept_id in state:
        state[concept_id]["name"] = payload.get("name", state[concept_id].get("name"))
    elif event.event_type == "RELATIONSHIP_ADDED":
        state.setdefault("_relationships", [])
        state["_relationships"].append(payload)
    elif event.event_type == "RELATIONSHIP_REMOVED":
        rows = state.get("_relationships", [])
        state["_relationships"] = [
            row
            for row in rows
            if not (
                row.get("source_concept_id") == payload.get("source_concept_id")
                and row.get("target_concept_id") == payload.get("target_concept_id")
                and row.get("relation_type") == payload.get("relation_type")
            )
        ]


def review_day(session: Session, day: str, episodes: list[Episode], settings: Settings) -> TaxonomyReviewPayload:
    if settings.curator == "llm":
        if not settings.llm_base_url or not settings.llm_model:
            raise CuratorError("SERAH_CURATOR=llm requires SERAH_LLM_BASE_URL and SERAH_LLM_MODEL")
        client = ChatClient(settings.llm_base_url, settings.llm_model, settings.resolved_llm_key())
        return _llm_review(session, day, episodes, client)
    return _mock_review(episodes)


def _mock_review(episodes: list[Episode]) -> TaxonomyReviewPayload:
    relevant: list[RelevantConcept] = []
    obligation: list[str] = []
    for episode in episodes:
        for concept_id in sorted(concept_hits(episode.user_text)):
            relevant.append(
                RelevantConcept(
                    episode_id=episode.id,
                    concept_id=concept_id,
                    rationale="Mock lexicon matched this concept in the user text.",
                )
            )
        if obligation_marker_count(episode.user_text) >= 3:
            obligation.append(episode.id)
    proposals: list[ConceptProposal] = []
    if obligation:
        proposals.append(
            ConceptProposal(
                taxonomy_id=OBLIGATION_PRESSURE.taxonomy_id,
                name=OBLIGATION_PRESSURE.name,
                family="compression",
                definition=OBLIGATION_PRESSURE.definition,
                inclusion_guidance=OBLIGATION_PRESSURE.inclusion,
                exclusion_guidance=OBLIGATION_PRESSURE.exclusion,
                rationale=(
                    "The same cluster of duty, bodily tightness, urgency, and relief "
                    "recurred in the user evidence."
                ),
                confidence=0.62,
                nearest_concept_ids=["emotion.fear", "emotion.anxiety"],
                supporting_episode_ids=obligation,
            )
        )
    return TaxonomyReviewPayload(
        relevant=relevant,
        proposals=proposals,
        rationale="Mock curator preferred existing concepts and watched one compression pattern.",
    )


def _llm_review(session: Session, day: str, episodes: list[Episode], client: ChatClient) -> TaxonomyReviewPayload:
    concepts = session.scalars(select(TaxonomyConcept)).all()
    catalog = []
    for concept in concepts:
        version = session.scalar(
            select(TaxonomyConceptVersion)
            .where(TaxonomyConceptVersion.concept_id == concept.id)
            .order_by(TaxonomyConceptVersion.version.desc())
        )
        catalog.append(
            {
                "id": concept.id,
                "name": concept.name,
                "family": concept.family,
                "status": concept.status,
                "locked": concept.locked,
                "definition": version.definition if version else "",
                "support_count": concept.support_count,
            }
        )
    import json

    system = load_prompt("taxonomy_review", "v1.md")
    user = json.dumps(
        {
            "day": day,
            "taxonomy": catalog,
            "episodes": [
                {
                    "episode_id": episode.id,
                    "user_evidence": episode.user_text,
                    "context": episode.context_text,
                    "extractor_direct_states": episode.direct_states,
                }
                for episode in episodes
            ],
        },
        ensure_ascii=False,
    )
    return complete_model(client, system, user, TaxonomyReviewPayload)


def apply_review(
    session: Session,
    day: str,
    episodes: list[Episode],
    review: TaxonomyReviewPayload,
    settings: Settings,
    run_id: str,
    *,
    actor: str,
    model_id: str | None,
) -> dict:
    """Apply one day's review. Thresholds, not the model, decide activation."""
    known_episode_ids = {episode.id for episode in episodes}
    stats = {"relevant": 0, "proposed": 0, "activated": 0, "suggestions": 0}
    sequence = 0
    for item in review.relevant:
        if item.episode_id not in known_episode_ids:
            continue
        concept = session.get(TaxonomyConcept, item.concept_id)
        if concept is None or concept.status != "active":
            continue
        _add_relevance(session, item.episode_id, item.concept_id, day, item.rationale)
        stats["relevant"] += 1
    proposals = review.proposals[: settings.max_proposals_per_day]
    for proposal in proposals:
        sequence = _apply_proposal(
            session, day, proposal, known_episode_ids, settings, run_id, actor, model_id, sequence, stats
        )
    for suggestion in review.definition_suggestions:
        sequence = _apply_suggestion(
            session, day, suggestion, run_id, actor, model_id, sequence, stats
        )
    for relationship in review.relationships:
        sequence = _apply_relationship(
            session, day, relationship, known_episode_ids, run_id, actor, model_id, sequence
        )
    _event(
        session,
        "TAXONOMY_REVIEWED",
        None,
        {"relevant": stats["relevant"], "proposals": len(proposals)},
        day,
        actor,
        model_id,
        review.rationale,
        None,
        run_id,
        sequence,
    )
    return stats


def _apply_proposal(
    session, day, proposal: ConceptProposal, known_ids, settings, run_id, actor, model_id, sequence, stats
) -> int:
    if not CONCEPT_ID_RE.match(proposal.taxonomy_id):
        return sequence
    if proposal.family not in {"emotion", "compression"}:
        return sequence
    support_ids = [item for item in proposal.supporting_episode_ids if item in known_ids]
    if not support_ids:
        return sequence
    existing_by_name = session.scalar(
        select(TaxonomyConcept).where(func.lower(TaxonomyConcept.name) == proposal.name.lower())
    )
    concept = session.get(TaxonomyConcept, proposal.taxonomy_id)
    if concept is None and existing_by_name is not None:
        concept = existing_by_name
    if concept is None:
        concept = TaxonomyConcept(
            id=proposal.taxonomy_id,
            name=proposal.name,
            family=proposal.family,
            status="proposed",
            locked=False,
            first_observed_on=day,
            support_count=0,
            confidence=proposal.confidence,
            nearest_concepts=proposal.nearest_concept_ids,
            rationale=proposal.rationale,
            created_at=utc_now(),
        )
        session.add(concept)
        session.add(
            TaxonomyConceptVersion(
                id=new_id(),
                concept_id=concept.id,
                version=1,
                definition=proposal.definition,
                inclusion_guidance=proposal.inclusion_guidance,
                exclusion_guidance=proposal.exclusion_guidance,
                source=actor,
                effective_on=day,
                created_at=utc_now(),
            )
        )
        sequence += 1
        _event(
            session,
            "CONCEPT_PROPOSED",
            concept.id,
            {
                "status": "proposed",
                "name": concept.name,
                "family": concept.family,
                "definition": proposal.definition,
                "inclusion_guidance": proposal.inclusion_guidance,
                "exclusion_guidance": proposal.exclusion_guidance,
                "version": 1,
            },
            day,
            actor,
            model_id,
            proposal.rationale,
            proposal.confidence,
            run_id,
            sequence,
        )
        session.flush()
        ensure_question(session, concept.id)
        stats["proposed"] += 1
    for episode_id in support_ids:
        already = session.scalar(
            select(ConceptSupport).where(
                ConceptSupport.concept_id == concept.id,
                ConceptSupport.episode_id == episode_id,
            )
        )
        if already is None:
            session.add(
                ConceptSupport(id=new_id(), concept_id=concept.id, episode_id=episode_id, day=day)
            )
    session.flush()
    days = session.scalars(
        select(ConceptSupport.day).where(ConceptSupport.concept_id == concept.id).distinct()
    ).all()
    concept.support_count = len(set(days))
    concept.confidence = proposal.confidence
    if concept.locked:
        return sequence
    if concept.status in {"proposed", "candidate", "dormant"} and concept.support_count >= settings.active_days:
        concept.status = "active"
        sequence += 1
        _event(
            session,
            "CONCEPT_ACTIVATED",
            concept.id,
            {"status": "active", "support_count": concept.support_count},
            day,
            actor,
            model_id,
            proposal.rationale,
            proposal.confidence,
            run_id,
            sequence,
        )
        stats["activated"] += 1
        for target in proposal.nearest_concept_ids:
            if session.get(TaxonomyConcept, target) is None:
                continue
            sequence = _add_relationship(
                session,
                concept.id,
                target,
                "ASSOCIATED_WITH",
                proposal.confidence,
                day,
                support_ids,
                actor,
                proposal.rationale,
                run_id,
                model_id,
                sequence,
            )
    elif concept.status == "proposed" and concept.support_count >= settings.candidate_days:
        concept.status = "candidate"
        sequence += 1
        _event(
            session,
            "CONCEPT_STATUS_CHANGED",
            concept.id,
            {"status": "candidate", "support_count": concept.support_count},
            day,
            actor,
            model_id,
            proposal.rationale,
            proposal.confidence,
            run_id,
            sequence,
        )
    if concept.status == "active":
        for episode_id in support_ids:
            _add_relevance(session, episode_id, concept.id, day, proposal.rationale)
    return sequence


def _apply_suggestion(session, day, suggestion, run_id, actor, model_id, sequence, stats) -> int:
    concept = session.get(TaxonomyConcept, suggestion.concept_id)
    if concept is None:
        return sequence
    if actor != "human" and concept.locked:
        # Locked copy changes only through an explicit human revision.
        sequence += 1
        _event(
            session,
            "CONCEPT_DEFINITION_SUGGESTED",
            concept.id,
            {
                "definition": suggestion.definition,
                "inclusion_guidance": suggestion.inclusion_guidance,
                "exclusion_guidance": suggestion.exclusion_guidance,
            },
            day,
            actor,
            model_id,
            suggestion.rationale,
            None,
            run_id,
            sequence,
        )
        stats["suggestions"] += 1
        return sequence
    revise_definition(
        session,
        concept.id,
        suggestion.definition,
        suggestion.inclusion_guidance,
        suggestion.exclusion_guidance,
        suggestion.rationale,
        actor=actor,
        day=day,
        run_id=run_id,
        model_id=model_id,
    )
    return sequence


def revise_definition(
    session: Session,
    concept_id: str,
    definition: str,
    inclusion: str,
    exclusion: str,
    rationale: str,
    *,
    actor: str,
    day: str,
    run_id: str | None,
    model_id: str | None,
) -> TaxonomyConceptVersion:
    concept = session.get(TaxonomyConcept, concept_id)
    if concept is None:
        raise SerahError("unknown concept")
    current = session.scalar(
        select(TaxonomyConceptVersion)
        .where(TaxonomyConceptVersion.concept_id == concept_id)
        .order_by(TaxonomyConceptVersion.version.desc())
    )
    number = 1 if current is None else current.version + 1
    row = TaxonomyConceptVersion(
        id=new_id(),
        concept_id=concept_id,
        version=number,
        definition=definition,
        inclusion_guidance=inclusion,
        exclusion_guidance=exclusion,
        source=actor,
        effective_on=day,
        created_at=utc_now(),
    )
    session.add(row)
    _event(
        session,
        "CONCEPT_DEFINITION_REVISED",
        concept_id,
        {
            "version": number,
            "definition": definition,
            "inclusion_guidance": inclusion,
            "exclusion_guidance": exclusion,
        },
        day,
        actor,
        model_id,
        rationale,
        None,
        run_id,
        0,
    )
    session.flush()
    ensure_question(session, concept_id)
    return row


def _apply_relationship(session, day, relationship: RelationshipProposal, known_ids, run_id, actor, model_id, sequence):
    if relationship.relation_type not in RELATION_TYPES:
        return sequence
    if session.get(TaxonomyConcept, relationship.source_concept_id) is None:
        return sequence
    if session.get(TaxonomyConcept, relationship.target_concept_id) is None:
        return sequence
    support = [item for item in relationship.supporting_episode_ids if item in known_ids]
    return _add_relationship(
        session,
        relationship.source_concept_id,
        relationship.target_concept_id,
        relationship.relation_type,
        relationship.confidence,
        day,
        support,
        actor,
        relationship.rationale,
        run_id,
        model_id,
        sequence,
    )


def _add_relationship(
    session, source_id, target_id, relation_type, confidence, day, evidence_ids, actor, rationale, run_id, model_id, sequence
) -> int:
    existing = session.scalar(
        select(TaxonomyRelationship).where(
            TaxonomyRelationship.source_concept_id == source_id,
            TaxonomyRelationship.target_concept_id == target_id,
            TaxonomyRelationship.relation_type == relation_type,
            TaxonomyRelationship.removed_on.is_(None),
        )
    )
    if existing is not None:
        return sequence
    version = session.scalar(
        select(TaxonomyConceptVersion.version)
        .where(TaxonomyConceptVersion.concept_id == source_id)
        .order_by(TaxonomyConceptVersion.version.desc())
    )
    session.add(
        TaxonomyRelationship(
            id=new_id(),
            source_concept_id=source_id,
            target_concept_id=target_id,
            relation_type=relation_type,
            confidence=confidence,
            concept_version=version or 1,
            evidence_episode_ids=evidence_ids,
            created_on=day,
            removed_on=None,
            created_by=actor,
            rationale=rationale,
        )
    )
    sequence += 1
    _event(
        session,
        "RELATIONSHIP_ADDED",
        source_id,
        {
            "source_concept_id": source_id,
            "target_concept_id": target_id,
            "relation_type": relation_type,
            "confidence": confidence,
            "evidence_episode_ids": evidence_ids,
        },
        day,
        actor,
        model_id,
        rationale,
        confidence,
        run_id,
        sequence,
    )
    return sequence


def _add_relevance(session: Session, episode_id: str, concept_id: str, day: str, rationale: str) -> None:
    existing = session.scalar(
        select(EpisodeRelevance).where(
            EpisodeRelevance.episode_id == episode_id,
            EpisodeRelevance.concept_id == concept_id,
        )
    )
    if existing is None:
        session.add(
            EpisodeRelevance(
                id=new_id(),
                episode_id=episode_id,
                concept_id=concept_id,
                day=day,
                rationale=rationale,
            )
        )


def _event(
    session, event_type, concept_id, payload, day, actor, model_id, rationale, confidence, run_id, sequence
) -> None:
    session.add(
        TaxonomyEvent(
            id=new_id(),
            event_type=event_type,
            concept_id=concept_id,
            payload=payload,
            effective_on=day,
            causal_mode="causal",
            created_at=utc_now(),
            actor=actor,
            model_id=model_id,
            prompt_version=PROMPT_VERSION if actor == "llm" else None,
            rationale=rationale or "",
            confidence=confidence,
            processing_run_id=run_id,
            sequence=sequence,
        )
    )
