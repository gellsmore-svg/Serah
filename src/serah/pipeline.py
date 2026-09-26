"""Import, extract, curate, score, and open a database."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from serah import __version__
from serah.clock import utc_now
from serah.config import Settings, get_settings
from serah.db import init_database, session_scope
from serah.engines.registry import engine_statuses, require_engine
from serah.errors import EngineUnavailable, SerahError
from serah.extract import extract_pending
from serah.ids import new_id
from serah.ingest import import_chatgpt, import_conversations
from serah.models import (
    Episode,
    Experiment,
    ModelObservation,
    ProcessingRun,
    StageMark,
    TaxonomyConcept,
)
from serah.prompts import load_prompt
from serah.replay_store import replay_experiment
from serah.scoring import score_engine
from serah.synthetic import to_chatgpt_export
from serah.taxonomy import apply_review, review_day
from serah.temporal import UTC, utc_day


def open_session(settings: Settings | None = None) -> Session:
    return session_scope(settings or get_settings())


def run_import(session: Session, path: Path) -> dict:
    run = _start_run(session, "import", {"path": str(path)})
    stats = import_chatgpt(session, path)
    _finish_run(run, "succeeded", stats)
    session.commit()
    return stats


def run_extract(session: Session, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    run = _start_run(session, "extract", {"extractor": settings.extractor})
    try:
        stats = extract_pending(session, settings, run.id)
    except Exception as exc:
        _finish_run(run, "failed", {}, error=type(exc).__name__)
        session.commit()
        raise
    _finish_run(run, "succeeded", stats)
    session.commit()
    return stats


def run_taxonomy(session: Session, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    run = _start_run(session, "taxonomy", {"curator": settings.curator})
    episodes = session.scalars(
        select(Episode).where(Episode.excluded.is_(False)).order_by(Episode.timestamp_start, Episode.id)
    ).all()
    by_day: dict[str, list[Episode]] = {}
    for episode in episodes:
        by_day.setdefault(_episode_day(episode), []).append(episode)
    stats = {"days": 0, "skipped": 0, "proposed": 0, "activated": 0}
    try:
        for day in sorted(by_day):
            key = _taxonomy_key(day, by_day[day])
            if _marked(session, "taxonomy", key):
                stats["skipped"] += 1
                continue
            later = session.scalars(select(StageMark).where(StageMark.stage == "taxonomy")).all()
            for mark in later:
                if mark.key.split(":", 1)[0] > day:
                    session.delete(mark)
            session.flush()
            review = review_day(session, day, by_day[day], settings)
            applied = apply_review(
                session,
                day,
                by_day[day],
                review,
                settings,
                run.id,
                actor="llm" if settings.curator == "llm" else "mock",
                model_id=settings.llm_model if settings.curator == "llm" else "mock-curator-1",
            )
            session.add(
                StageMark(id=new_id(), stage="taxonomy", key=key, run_id=run.id, created_at=utc_now())
            )
            stats["days"] += 1
            stats["proposed"] += applied["proposed"]
            stats["activated"] += applied["activated"]
            session.commit()
    except Exception as exc:
        _finish_run(run, "failed", stats, error=type(exc).__name__)
        session.commit()
        raise
    _finish_run(run, "succeeded", stats)
    session.commit()
    return stats


def run_score(session: Session, engine_id: str, settings: Settings | None = None, mode: str | None = None) -> dict:
    settings = settings or get_settings()
    mode = mode or settings.scoring_mode
    try:
        engine = require_engine(engine_id, settings)
    except KeyError as exc:
        raise SerahError(str(exc)) from exc
    run = _start_run(session, "score", {"engine": engine_id, "mode": mode})
    try:
        stats = score_engine(session, engine, settings, mode, run.id)
    except EngineUnavailable as exc:
        _finish_run(run, "failed", {}, error=str(exc))
        session.commit()
        raise
    except Exception as exc:
        _finish_run(run, "failed", {}, error=type(exc).__name__)
        session.commit()
        raise
    _finish_run(run, "succeeded", stats)
    session.commit()
    return stats


def create_experiment(
    session: Session,
    *,
    name: str,
    engines: list[str],
    decay_type: str,
    half_life_hours: float,
    activation_gain: float,
    reservoir_update: str,
    core_scoring_mode: str,
    notes: str = "",
) -> Experiment:
    if decay_type not in {"exponential", "linear", "none"}:
        raise SerahError("decay_type must be exponential, linear, or none")
    if reservoir_update not in {"bounded_saturating", "replace"}:
        raise SerahError("reservoir_update must be bounded_saturating or replace")
    if core_scoring_mode not in {"relevant", "all-core"}:
        raise SerahError("core_scoring_mode must be relevant or all-core")
    if half_life_hours <= 0 and decay_type != "none":
        raise SerahError("half_life_hours must be positive")
    experiment = Experiment(
        id=new_id(),
        name=name,
        taxonomy_run_id=None,
        engines=list(engines),
        decay_type=decay_type,
        half_life_hours=half_life_hours,
        reservoir_update=reservoir_update,
        activation_gain=activation_gain,
        core_scoring_mode=core_scoring_mode,
        created_at=utc_now(),
        app_version=__version__,
        notes=notes,
    )
    session.add(experiment)
    session.commit()
    return experiment


def run_replay(session: Session, experiment_id: str) -> dict:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise SerahError("unknown experiment")
    run = _start_run(session, "replay", {"experiment_id": experiment_id})
    stats = replay_experiment(session, experiment)
    _finish_run(run, "succeeded", stats)
    session.commit()
    return stats


def run_demo(session: Session, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    imported = import_conversations(session, to_chatgpt_export())
    session.commit()
    extracted = run_extract(session, settings)
    curated = run_taxonomy(session, settings)
    scored = {
        "mock": run_score(session, "mock", settings, "relevant"),
        "mock_conservative": run_score(session, "mock_conservative", settings, "relevant"),
    }
    experiment = session.scalar(select(Experiment).where(Experiment.name == "Synthetic comparison"))
    if experiment is None:
        experiment = create_experiment(
            session,
            name="Synthetic comparison",
            engines=["mock", "mock_conservative"],
            decay_type=settings.decay,
            half_life_hours=settings.half_life_hours,
            activation_gain=settings.activation_gain,
            reservoir_update=settings.reservoir_update,
            core_scoring_mode="relevant",
            notes="Demo experiment. Shared taxonomy, shared decay, two deterministic engines.",
        )
    replayed = run_replay(session, experiment.id)
    return {
        "import": imported,
        "extract": extracted,
        "taxonomy": curated,
        "score": scored,
        "experiment_id": experiment.id,
        "replay": replayed,
    }


def status_report(session: Session) -> dict:
    concepts = session.scalars(select(TaxonomyConcept)).all()
    by_status: dict[str, int] = {}
    for concept in concepts:
        by_status[concept.status] = by_status.get(concept.status, 0) + 1
    observations = session.execute(
        select(ModelObservation.engine_id, func.count()).group_by(ModelObservation.engine_id)
    ).all()
    last = session.scalar(select(ProcessingRun).order_by(ProcessingRun.started_at.desc()))
    return {
        "version": __version__,
        "conversations": _count(session, "conversations"),
        "messages": _count(session, "messages"),
        "episodes": _count(session, "episodes"),
        "concepts": by_status,
        "observations": {engine: count for engine, count in observations},
        "experiments": _count(session, "experiments"),
        "last_run": None
        if last is None
        else {"id": last.id, "kind": last.kind, "status": last.status, "started_at": last.started_at},
    }


def doctor_report(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    checks = []
    try:
        load_prompt("taxonomy_review", "v1.md")
        checks.append({"name": "prompts", "ok": True, "detail": "packaged prompts are readable"})
    except Exception as exc:
        checks.append({"name": "prompts", "ok": False, "detail": type(exc).__name__})
    try:
        session = open_session(settings)
        session.scalar(select(func.count()).select_from(TaxonomyConcept))
        checks.append({"name": "database", "ok": True, "detail": str(settings.resolved_db_path())})
        session.close()
    except Exception as exc:
        checks.append({"name": "database", "ok": False, "detail": type(exc).__name__})
    models = []
    for status in engine_statuses(settings):
        models.append(
            {
                "engine_id": status.engine_id,
                "display_name": status.display_name,
                "availability": status.availability,
                "kind": status.kind,
                "detail": status.detail,
            }
        )
    return {"ok": all(item["ok"] for item in checks), "checks": checks, "engines": models}


def _count(session: Session, table: str) -> int:
    from serah import models as model_module

    mapping = {
        "conversations": model_module.Conversation,
        "messages": model_module.Message,
        "episodes": model_module.Episode,
        "experiments": model_module.Experiment,
    }
    model = mapping[table]
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _taxonomy_key(day: str, episodes: list[Episode]) -> str:
    digest = hashlib.sha256("\n".join(sorted(episode.id for episode in episodes)).encode()).hexdigest()[:16]
    return f"{day}:{digest}"


def _episode_day(episode: Episode) -> str:
    moment = datetime.fromisoformat(episode.timestamp_start)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return utc_day(moment).isoformat()


def _marked(session: Session, stage: str, key: str) -> bool:
    return session.scalar(select(StageMark).where(StageMark.stage == stage, StageMark.key == key)) is not None


def _start_run(session: Session, kind: str, config: dict) -> ProcessingRun:
    run = ProcessingRun(
        id=new_id(),
        kind=kind,
        status="running",
        started_at=utc_now(),
        finished_at=None,
        app_version=__version__,
        config=config,
        stats={},
        error=None,
    )
    session.add(run)
    session.flush()
    return run


def _finish_run(run: ProcessingRun, status: str, stats: dict, error: str | None = None) -> None:
    run.status = status
    run.stats = stats
    run.finished_at = utc_now()
    run.error = error


def ensure_database() -> None:
    init_database(get_settings())
