"""Versioned measurement questions. Editing the wording creates a new version."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from serah.clock import utc_now
from serah.distributions import LEVEL_DESCRIPTIONS
from serah.ids import new_id
from serah.models import MeasurementQuestion, TaxonomyConcept, TaxonomyConceptVersion

QUESTION_TEMPLATE = """Based only on the supplied user evidence, how strongly is {name} present in the user's expressed emotional state?

Definition: {definition}
Count as present when: {inclusion}
Do not count when: {exclusion}

Assistant text may appear as context. Do not treat an assistant's interpretation as the user's emotion unless the user's own words endorse it.
If the concept is not expressed in the user's evidence, use the low end of the scale. Silence is not a high score.
The scale runs from absent to the concept saturating the user's expressed state in this evidence."""


def render_instructions(name: str, definition: str, inclusion: str, exclusion: str) -> str:
    return QUESTION_TEMPLATE.format(
        name=name,
        definition=definition,
        inclusion=inclusion,
        exclusion=exclusion,
    )


def current_version(session: Session, concept_id: str) -> TaxonomyConceptVersion | None:
    rows = session.scalars(
        select(TaxonomyConceptVersion)
        .where(TaxonomyConceptVersion.concept_id == concept_id)
        .order_by(TaxonomyConceptVersion.version.desc())
    ).all()
    return rows[0] if rows else None


def version_on(session: Session, concept_id: str, day: str) -> TaxonomyConceptVersion | None:
    rows = session.scalars(
        select(TaxonomyConceptVersion)
        .where(
            TaxonomyConceptVersion.concept_id == concept_id,
            TaxonomyConceptVersion.effective_on <= day,
        )
        .order_by(TaxonomyConceptVersion.version.desc())
    ).all()
    return rows[0] if rows else None


def current_question(session: Session, concept_id: str) -> MeasurementQuestion | None:
    rows = session.scalars(
        select(MeasurementQuestion)
        .where(MeasurementQuestion.concept_id == concept_id)
        .order_by(MeasurementQuestion.version.desc())
    ).all()
    return rows[0] if rows else None


def ensure_question(session: Session, concept_id: str) -> MeasurementQuestion:
    """Create a question version when the concept version has no matching question yet."""
    concept = session.get(TaxonomyConcept, concept_id)
    version = current_version(session, concept_id)
    if concept is None or version is None:
        raise ValueError(f"concept {concept_id} has no definition to measure")
    existing = session.scalars(
        select(MeasurementQuestion).where(
            MeasurementQuestion.concept_id == concept_id,
            MeasurementQuestion.concept_version == version.version,
        )
    ).first()
    if existing is not None:
        return existing
    previous = current_question(session, concept_id)
    number = 1 if previous is None else previous.version + 1
    row = MeasurementQuestion(
        id=new_id(),
        concept_id=concept_id,
        version=number,
        concept_version=version.version,
        instructions=render_instructions(
            concept.name,
            version.definition,
            version.inclusion_guidance,
            version.exclusion_guidance,
        ),
        criteria=list(LEVEL_DESCRIPTIONS),
        created_at=utc_now(),
    )
    session.add(row)
    session.flush()
    return row
