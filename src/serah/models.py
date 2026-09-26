"""Relational schema. JSON is limited to raw payloads and flexible metadata."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("source_type", "external_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    imported_at: Mapped[str] = mapped_column(String(40))
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "external_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    on_current_branch: Mapped[bool] = mapped_column(Boolean, default=True)
    parent_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class ImportWarning(Base):
    __tablename__ = "import_warnings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    external_ref: Mapped[str] = mapped_column(String(200), default="")
    warning: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    timestamp_start: Mapped[str] = mapped_column(String(40), index=True)
    timestamp_end: Mapped[str] = mapped_column(String(40))
    user_text: Mapped[str] = mapped_column(Text)
    context_text: Mapped[str] = mapped_column(Text, default="")
    extraction_confidence: Mapped[float] = mapped_column(Float)
    source_type: Mapped[str] = mapped_column(String(32))
    extractor_id: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    direct_states: Mapped[list] = mapped_column(JSON, default=list)
    bodily_signals: Mapped[list] = mapped_column(JSON, default=list)
    trigger_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))


class EpisodeMessage(Base):
    __tablename__ = "episode_messages"

    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    role_in_episode: Mapped[str] = mapped_column(String(16))


class TaxonomyConcept(Base):
    __tablename__ = "taxonomy_concepts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    family: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    first_observed_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    nearest_concepts: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


class TaxonomyConceptVersion(Base):
    __tablename__ = "taxonomy_concept_versions"
    __table_args__ = (UniqueConstraint("concept_id", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_concepts.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[str] = mapped_column(Text)
    inclusion_guidance: Mapped[str] = mapped_column(Text)
    exclusion_guidance: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    effective_on: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[str] = mapped_column(String(40))


class TaxonomyRelationship(Base):
    __tablename__ = "taxonomy_relationships"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_concept_id: Mapped[str] = mapped_column(String(80), index=True)
    target_concept_id: Mapped[str] = mapped_column(String(80), index=True)
    relation_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    concept_version: Mapped[int] = mapped_column(Integer)
    evidence_episode_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_on: Mapped[str] = mapped_column(String(10))
    removed_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    rationale: Mapped[str] = mapped_column(Text, default="")


class TaxonomyEvent(Base):
    __tablename__ = "taxonomy_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    concept_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    effective_on: Mapped[str] = mapped_column(String(10), index=True)
    causal_mode: Mapped[str] = mapped_column(String(32), default="causal")
    created_at: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class ConceptSupport(Base):
    __tablename__ = "concept_support"
    __table_args__ = (UniqueConstraint("concept_id", "episode_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    concept_id: Mapped[str] = mapped_column(String(80), index=True)
    episode_id: Mapped[str] = mapped_column(String(64))
    day: Mapped[str] = mapped_column(String(10))


class EpisodeRelevance(Base):
    __tablename__ = "episode_relevance"
    __table_args__ = (UniqueConstraint("episode_id", "concept_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(64), index=True)
    concept_id: Mapped[str] = mapped_column(String(80), index=True)
    day: Mapped[str] = mapped_column(String(10))
    rationale: Mapped[str] = mapped_column(Text, default="")


class MeasurementQuestion(Base):
    __tablename__ = "measurement_questions"
    __table_args__ = (UniqueConstraint("concept_id", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    concept_id: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer)
    concept_version: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(Text)
    criteria: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class ModelObservation(Base):
    __tablename__ = "model_observations"
    __table_args__ = (
        UniqueConstraint(
            "episode_id",
            "concept_id",
            "engine_id",
            "concept_version",
            "question_version",
            name="uq_observation_instrument",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), index=True)
    concept_id: Mapped[str] = mapped_column(String(80), index=True)
    concept_version: Mapped[int] = mapped_column(Integer)
    engine_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(160))
    question_version: Mapped[int] = mapped_column(Integer)
    native_output_type: Mapped[str] = mapped_column(String(64))
    normalisation_method: Mapped[str] = mapped_column(String(80))
    raw_response: Mapped[dict] = mapped_column(JSON, default=dict)
    distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_intensity: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    distribution_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)
    distribution_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    modal_bin: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider_reported: Mapped[dict] = mapped_column(JSON, default=dict)
    processing_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)


class InferenceCache(Base):
    __tablename__ = "inference_cache"

    request_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    engine_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict] = mapped_column(JSON)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[str] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    app_version: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class StageMark(Base):
    __tablename__ = "stage_marks"
    __table_args__ = (UniqueConstraint("stage", "key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(200))
    run_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    taxonomy_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engines: Mapped[list] = mapped_column(JSON)
    decay_type: Mapped[str] = mapped_column(String(32))
    half_life_hours: Mapped[float] = mapped_column(Float)
    reservoir_update: Mapped[str] = mapped_column(String(64))
    activation_gain: Mapped[float] = mapped_column(Float)
    core_scoring_mode: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(40))
    app_version: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")


class ReservoirEventRow(Base):
    __tablename__ = "reservoir_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    engine_id: Mapped[str] = mapped_column(String(64), index=True)
    concept_id: Mapped[str] = mapped_column(String(80), index=True)
    episode_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_time: Mapped[str] = mapped_column(String(40))
    event_kind: Mapped[str] = mapped_column(String(40))
    previous_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    level_after: Mapped[float] = mapped_column(Float)
    delta_hours: Mapped[float] = mapped_column(Float)
    observation_intensity: Mapped[float | None] = mapped_column(Float, nullable=True)


class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    __table_args__ = (UniqueConstraint("experiment_id", "engine_id", "day"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    engine_id: Mapped[str] = mapped_column(String(64))
    day: Mapped[str] = mapped_column(String(10), index=True)
    states: Mapped[dict] = mapped_column(JSON, default=dict)
    episode_count: Mapped[int] = mapped_column(Integer, default=0)
    user_word_count: Mapped[int] = mapped_column(Integer, default=0)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class SelfRating(Base):
    __tablename__ = "self_ratings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    concept_id: Mapped[str] = mapped_column(String(80), index=True)
    rating: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40))
