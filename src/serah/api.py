"""Local research API. It binds to loopback unless the operator says otherwise."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from serah import __version__
from serah.engines.registry import engine_statuses
from serah.errors import SerahError
from serah.manual import (
    add_annotation,
    add_concept,
    add_self_rating,
    exclude_episode,
    flag_observation,
    human_revise,
    merge_concepts,
    set_candidate_status,
)
from serah.pipeline import (
    create_experiment,
    doctor_report,
    open_session,
    run_replay,
    status_report,
)
from serah.queries import (
    concept_detail,
    day_view,
    density,
    list_concepts,
    list_experiments,
    multi_series,
    observation_detail,
    series,
)

app = FastAPI(title="Serah", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    session = open_session()
    try:
        yield session
    finally:
        session.close()


def _guard(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except SerahError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ExperimentIn(BaseModel):
    name: str
    engines: list[str]
    decay_type: str = "exponential"
    half_life_hours: float = 72
    activation_gain: float = 0.35
    reservoir_update: str = "bounded_saturating"
    core_scoring_mode: str = "relevant"
    notes: str = ""


class ConceptIn(BaseModel):
    taxonomy_id: str
    name: str
    family: str
    definition: str
    inclusion: str
    exclusion: str
    status: str = "active"
    day: str
    rationale: str = ""


class StatusIn(BaseModel):
    status: str
    rationale: str = ""
    day: str


class ReviseIn(BaseModel):
    definition: str
    inclusion: str
    exclusion: str
    rationale: str
    day: str


class MergeIn(BaseModel):
    source_id: str
    target_id: str
    rationale: str
    day: str


class NoteIn(BaseModel):
    note: str = ""
    day: str | None = None


class FlagIn(BaseModel):
    note: str = ""
    exclude: bool = False


class AnnotationIn(BaseModel):
    day: str
    text: str


class RatingIn(BaseModel):
    day: str
    concept_id: str
    rating: float = Field(ge=0, le=100)
    note: str = ""


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/status")
def status(db: Session = Depends(get_db)) -> dict:
    return status_report(db)


@app.get("/api/doctor")
def doctor() -> dict:
    return doctor_report()


@app.get("/api/models")
def models() -> dict:
    return {
        "engines": [
            {
                "engine_id": item.engine_id,
                "display_name": item.display_name,
                "availability": item.availability,
                "kind": item.kind,
                "detail": item.detail,
            }
            for item in engine_statuses()
        ]
    }


@app.get("/api/taxonomy")
def taxonomy(status: str | None = None, db: Session = Depends(get_db)) -> dict:
    return {"concepts": list_concepts(db, status)}


@app.get("/api/taxonomy/{concept_id}")
def taxonomy_one(concept_id: str, db: Session = Depends(get_db)) -> dict:
    return _guard(concept_detail, db, concept_id)


@app.post("/api/taxonomy")
def taxonomy_add(body: ConceptIn, db: Session = Depends(get_db)) -> dict:
    concept = _guard(add_concept, db, **body.model_dump())
    return {"id": concept.id, "status": concept.status}


@app.post("/api/taxonomy/{concept_id}/status")
def taxonomy_status(concept_id: str, body: StatusIn, db: Session = Depends(get_db)) -> dict:
    _guard(set_candidate_status, db, concept_id, body.status, body.rationale, body.day)
    return {"ok": True}


@app.post("/api/taxonomy/{concept_id}/revise")
def taxonomy_revise(concept_id: str, body: ReviseIn, db: Session = Depends(get_db)) -> dict:
    _guard(human_revise, db, concept_id, body.definition, body.inclusion, body.exclusion, body.rationale, body.day)
    return {"ok": True}


@app.post("/api/taxonomy/merge")
def taxonomy_merge(body: MergeIn, db: Session = Depends(get_db)) -> dict:
    _guard(merge_concepts, db, body.source_id, body.target_id, body.rationale, body.day)
    return {"ok": True}


@app.get("/api/experiments")
def experiments(db: Session = Depends(get_db)) -> dict:
    return {"experiments": list_experiments(db)}


@app.post("/api/experiments")
def experiments_create(body: ExperimentIn, db: Session = Depends(get_db)) -> dict:
    experiment = _guard(create_experiment, db, **body.model_dump())
    return {"id": experiment.id}


@app.post("/api/experiments/{experiment_id}/replay")
def experiments_replay(experiment_id: str, db: Session = Depends(get_db)) -> dict:
    return _guard(run_replay, db, experiment_id)


@app.get("/api/series")
def series_route(
    experiment_id: str,
    concept_id: str,
    mode: str = "reservoir",
    db: Session = Depends(get_db),
) -> dict:
    return _guard(series, db, experiment_id, concept_id, mode)


@app.get("/api/compare")
def compare_route(
    experiment_id: str,
    engine_id: str,
    concept_ids: str,
    mode: str = "reservoir",
    db: Session = Depends(get_db),
) -> dict:
    return _guard(multi_series, db, experiment_id, engine_id, [item for item in concept_ids.split(",") if item], mode)


@app.get("/api/days/{day}")
def day_route(day: str, experiment_id: str, engine_id: str, db: Session = Depends(get_db)) -> dict:
    return _guard(day_view, db, experiment_id, engine_id, day)


@app.get("/api/observations/{observation_id}")
def observation_route(
    observation_id: str,
    experiment_id: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return _guard(observation_detail, db, observation_id, experiment_id)


@app.post("/api/episodes/{episode_id}/exclude")
def episode_exclude(episode_id: str, body: NoteIn, db: Session = Depends(get_db)) -> dict:
    _guard(exclude_episode, db, episode_id, body.note)
    return {"ok": True}


@app.post("/api/observations/{observation_id}/flag")
def observation_flag(observation_id: str, body: FlagIn, db: Session = Depends(get_db)) -> dict:
    _guard(flag_observation, db, observation_id, body.note, body.exclude)
    return {"ok": True}


@app.get("/api/density")
def density_route(experiment_id: str, db: Session = Depends(get_db)) -> dict:
    return {"days": density(db, experiment_id)}


@app.get("/api/annotations")
def annotations(db: Session = Depends(get_db)) -> dict:
    from serah.models import Annotation

    rows = db.query(Annotation).all()
    return {"annotations": [{"id": row.id, "day": row.day, "text": row.text} for row in rows]}


@app.post("/api/annotations")
def annotations_add(body: AnnotationIn, db: Session = Depends(get_db)) -> dict:
    row = add_annotation(db, body.day, body.text)
    return {"id": row.id}


@app.get("/api/self-ratings")
def ratings(db: Session = Depends(get_db)) -> dict:
    from serah.models import SelfRating

    rows = db.query(SelfRating).all()
    return {
        "ratings": [
            {"id": row.id, "day": row.day, "concept_id": row.concept_id, "rating": row.rating, "note": row.note}
            for row in rows
        ]
    }


@app.post("/api/self-ratings")
def ratings_add(body: RatingIn, db: Session = Depends(get_db)) -> dict:
    row = _guard(add_self_rating, db, body.day, body.concept_id, body.rating, body.note)
    return {"id": row.id}


def _frontend_dist() -> Path | None:
    candidates = [
        Path.cwd() / "frontend" / "dist",
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


_dist = _frontend_dist()
if _dist is not None:
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_dist / "index.html")
