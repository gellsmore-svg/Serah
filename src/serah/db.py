"""SQLite session helpers and idempotent core-taxonomy seed."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from serah.clock import utc_now
from serah.config import Settings, get_settings
from serah.core_taxonomy import CORE_CONCEPTS
from serah.ids import new_id
from serah.models import Base, TaxonomyConcept, TaxonomyConceptVersion, TaxonomyEvent

SEED_DAY = "1970-01-01"


def make_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    path = settings.resolved_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


def init_database(settings: Settings | None = None) -> sessionmaker[Session]:
    settings = settings or get_settings()
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        seed_core(session)
        session.commit()
    return factory


def session_scope(settings: Settings | None = None) -> Session:
    factory = init_database(settings)
    return factory()


def seed_core(session: Session) -> None:
    """Insert the locked core once. Later runs leave existing rows alone."""
    existing = set(session.scalars(select(TaxonomyConcept.id)).all())
    now = utc_now()
    for item in CORE_CONCEPTS:
        if item.taxonomy_id in existing:
            from serah.questions import ensure_question

            ensure_question(session, item.taxonomy_id)
            continue
        session.add(
            TaxonomyConcept(
                id=item.taxonomy_id,
                name=item.name,
                family=item.family,
                status="active",
                locked=True,
                first_observed_on=SEED_DAY,
                support_count=0,
                confidence=None,
                nearest_concepts=[],
                rationale="Locked core concept shipped with Serah 0.1.",
                created_at=now,
            )
        )
        session.add(
            TaxonomyConceptVersion(
                id=new_id(),
                concept_id=item.taxonomy_id,
                version=1,
                definition=item.definition,
                inclusion_guidance=item.inclusion,
                exclusion_guidance=item.exclusion,
                source="locked_core",
                effective_on=SEED_DAY,
                created_at=now,
            )
        )
        session.add(
            TaxonomyEvent(
                id=new_id(),
                event_type="CONCEPT_ACTIVATED",
                concept_id=item.taxonomy_id,
                payload={
                    "status": "active",
                    "locked": True,
                    "version": 1,
                    "name": item.name,
                    "family": item.family,
                    "definition": item.definition,
                    "inclusion_guidance": item.inclusion,
                    "exclusion_guidance": item.exclusion,
                    "source": "locked_core",
                },
                effective_on=SEED_DAY,
                causal_mode="causal",
                created_at=now,
                actor="system",
                model_id=None,
                prompt_version=None,
                rationale="Initial locked core.",
                confidence=None,
                processing_run_id=None,
                sequence=0,
            )
        )
        session.flush()
        from serah.questions import ensure_question

        ensure_question(session, item.taxonomy_id)
