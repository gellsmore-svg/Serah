"""Structured model-to-model payloads. Free prose is not accepted as core data."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractionPayload(BaseModel):
    is_emotional: bool
    direct_states: list[str] = Field(default_factory=list)
    bodily_signals: list[str] = Field(default_factory=list)
    trigger: str | None = None
    regulation: str | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""


class RelevantConcept(BaseModel):
    episode_id: str
    concept_id: str
    rationale: str = ""


class ConceptProposal(BaseModel):
    taxonomy_id: str
    name: str
    family: Literal["emotion", "compression"]
    definition: str
    inclusion_guidance: str
    exclusion_guidance: str
    rationale: str
    confidence: float = Field(ge=0, le=1)
    nearest_concept_ids: list[str] = Field(default_factory=list)
    supporting_episode_ids: list[str] = Field(default_factory=list)


class DefinitionSuggestion(BaseModel):
    concept_id: str
    definition: str
    inclusion_guidance: str
    exclusion_guidance: str
    rationale: str


class RelationshipProposal(BaseModel):
    source_concept_id: str
    target_concept_id: str
    relation_type: str
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""
    supporting_episode_ids: list[str] = Field(default_factory=list)


class TaxonomyReviewPayload(BaseModel):
    relevant: list[RelevantConcept] = Field(default_factory=list)
    proposals: list[ConceptProposal] = Field(default_factory=list)
    definition_suggestions: list[DefinitionSuggestion] = Field(default_factory=list)
    relationships: list[RelationshipProposal] = Field(default_factory=list)
    rationale: str = ""


class LLMDistributionPayload(BaseModel):
    bins: dict[str, float] | None = None
    intensity: float | None = None
    rationale: str = ""
