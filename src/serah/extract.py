"""Episode extraction. User text is evidence. Assistant text is context."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from serah.clock import utc_now
from serah.config import Settings
from serah.core_taxonomy import CORE_BY_ID
from serah.ids import new_id
from serah.lexicon import body_signals, concept_hits, obligation_marker_count
from serah.llm_client import ChatClient, complete_model
from serah.models import Episode, EpisodeMessage, Message, StageMark
from serah.prompts import load_prompt
from serah.schemas import ExtractionPayload

PROMPT_VERSION = "episode_extraction/v1"


def _marked(session: Session, key: str) -> bool:
    return (
        session.scalar(select(StageMark).where(StageMark.stage == "extract", StageMark.key == key))
        is not None
    )


def _mark(session: Session, key: str, run_id: str) -> None:
    session.add(
        StageMark(id=new_id(), stage="extract", key=key, run_id=run_id, created_at=utc_now())
    )


def extract_pending(session: Session, settings: Settings, run_id: str) -> dict:
    messages = session.scalars(select(Message).order_by(Message.timestamp, Message.ordinal)).all()
    by_conversation: dict[str, list[Message]] = {}
    for message in messages:
        by_conversation.setdefault(message.conversation_id, []).append(message)
    stats = {"episodes": 0, "skipped": 0, "already": 0}
    client = None
    if settings.extractor == "llm":
        if not settings.llm_base_url or not settings.llm_model:
            raise RuntimeError("SERAH_EXTRACTOR=llm requires SERAH_LLM_BASE_URL and SERAH_LLM_MODEL")
        client = ChatClient(settings.llm_base_url, settings.llm_model, settings.resolved_llm_key())
    for grouped in by_conversation.values():
        previous_assistant: Message | None = None
        for message in grouped:
            if not message.on_current_branch:
                continue
            if message.role == "assistant":
                previous_assistant = message
                continue
            if message.role != "user":
                continue
            if _marked(session, message.id):
                stats["already"] += 1
                continue
            context = previous_assistant.text if previous_assistant is not None else ""
            if settings.extractor == "llm":
                payload = _llm_extract(client, message.text, context, session)
            else:
                payload = _mock_extract(message.text)
            if payload is None or not payload.is_emotional:
                stats["skipped"] += 1
                _mark(session, message.id, run_id)
                continue
            episode_id = new_id()
            session.add(
                Episode(
                    id=episode_id,
                    conversation_id=message.conversation_id,
                    timestamp_start=message.timestamp or utc_now(),
                    timestamp_end=message.timestamp or utc_now(),
                    user_text=message.text,
                    context_text=context,
                    extraction_confidence=payload.confidence,
                    source_type="chatgpt",
                    extractor_id=settings.extractor,
                    prompt_version=PROMPT_VERSION if settings.extractor == "llm" else "mock-lexicon-1",
                    model_id=settings.llm_model if settings.extractor == "llm" else "mock-lexicon-1",
                    direct_states=payload.direct_states,
                    bodily_signals=payload.bodily_signals,
                    trigger_text=payload.trigger,
                    regulation_text=payload.regulation,
                    excluded=False,
                    processing_run_id=run_id,
                    created_at=utc_now(),
                )
            )
            session.add(
                EpisodeMessage(
                    episode_id=episode_id,
                    message_id=message.id,
                    role_in_episode="evidence",
                )
            )
            if previous_assistant is not None:
                session.add(
                    EpisodeMessage(
                        episode_id=episode_id,
                        message_id=previous_assistant.id,
                        role_in_episode="context",
                    )
                )
            _mark(session, message.id, run_id)
            stats["episodes"] += 1
    return stats


def _mock_extract(user_text: str) -> ExtractionPayload | None:
    hits = concept_hits(user_text)
    bodies = body_signals(user_text)
    markers = obligation_marker_count(user_text)
    if not hits and not bodies and markers < 3:
        return ExtractionPayload(is_emotional=False, confidence=0.2, rationale="No mock lexicon hit.")
    confidence = min(0.9, 0.35 + 0.08 * max(1, len(hits)))
    regulation = "relief after the demand" if "relief" in user_text.lower() else None
    return ExtractionPayload(
        is_emotional=True,
        direct_states=sorted(hits),
        bodily_signals=bodies,
        trigger=None,
        regulation=regulation,
        confidence=confidence,
        rationale="Mock lexicon matched user text only.",
    )


def _llm_extract(client: ChatClient | None, user_text: str, context: str, session: Session) -> ExtractionPayload:
    if client is None:
        raise RuntimeError("llm extractor is not configured")
    catalog = [
        {"id": concept.taxonomy_id, "name": concept.name, "definition": concept.definition}
        for concept in CORE_BY_ID.values()
    ]
    # Include active discovered concepts so the extractor can name them, still from the user text.
    from serah.models import TaxonomyConcept

    extra = session.scalars(
        select(TaxonomyConcept).where(TaxonomyConcept.status == "active", TaxonomyConcept.locked.is_(False))
    ).all()
    for concept in extra:
        catalog.append({"id": concept.id, "name": concept.name, "definition": concept.rationale})
    system = load_prompt("episode_extraction", "v1.md")
    user = json_dumps(
        {
            "taxonomy": catalog,
            "user_evidence": user_text,
            "context": context,
        }
    )
    payload = complete_model(client, system, user, ExtractionPayload)
    known = {item["id"] for item in catalog}
    payload.direct_states = [item for item in payload.direct_states if item in known]
    return payload


def json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)
