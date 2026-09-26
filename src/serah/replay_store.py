"""Persist a deterministic replay. Derived rows are replaced; observations are not."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from serah.ids import new_id
from serah.models import (
    DailySnapshot,
    Episode,
    EpisodeRelevance,
    Experiment,
    ModelObservation,
    ReservoirEventRow,
)
from serah.temporal import UTC, ObservationPoint, replay_concept, utc_day


def replay_experiment(session: Session, experiment: Experiment) -> dict:
    session.execute(delete(ReservoirEventRow).where(ReservoirEventRow.experiment_id == experiment.id))
    session.execute(delete(DailySnapshot).where(DailySnapshot.experiment_id == experiment.id))
    episodes = session.scalars(select(Episode).where(Episode.excluded.is_(False))).all()
    if not episodes:
        return {"days": 0, "engines": list(experiment.engines)}
    days = sorted({_day(episode.timestamp_start) for episode in episodes})
    day_from, day_to = days[0], days[-1]
    density: dict[date, dict[str, int]] = {}
    for episode in episodes:
        bucket = density.setdefault(_day(episode.timestamp_start), {"episodes": 0, "words": 0})
        bucket["episodes"] += 1
        bucket["words"] += len(episode.user_text.split())
    for engine_id in experiment.engines:
        _replay_engine(session, experiment, engine_id, episodes, day_from, day_to, density)
    session.flush()
    span = (day_to - day_from).days + 1
    return {"days": span, "engines": list(experiment.engines)}


def _replay_engine(session, experiment, engine_id, episodes, day_from, day_to, density) -> None:
    episode_by_id = {episode.id: episode for episode in episodes}
    observations = session.scalars(
        select(ModelObservation).where(
            ModelObservation.engine_id == engine_id,
            ModelObservation.excluded.is_(False),
            ModelObservation.expected_intensity.is_not(None),
        )
    ).all()
    relevant_pairs = {
        (row.episode_id, row.concept_id)
        for row in session.scalars(select(EpisodeRelevance)).all()
    }
    grouped: dict[str, list[ObservationPoint]] = {}
    for observation in observations:
        episode = episode_by_id.get(observation.episode_id)
        if episode is None:
            continue
        if experiment.core_scoring_mode == "relevant":
            if (observation.episode_id, observation.concept_id) not in relevant_pairs:
                continue
        moment = _moment(episode.timestamp_start)
        grouped.setdefault(observation.concept_id, []).append(
            ObservationPoint(
                at=moment,
                intensity=float(observation.expected_intensity),
                observation_id=observation.id,
                episode_id=episode.id,
            )
        )
    per_day: dict[date, dict] = {}
    counts: dict[date, int] = {}
    cursor = day_from
    while cursor <= day_to:
        per_day[cursor] = {}
        counts[cursor] = 0
        cursor += timedelta(days=1)
    for concept_id, points in grouped.items():
        snapshots, events = replay_concept(
            points,
            day_from,
            day_to,
            decay_type=experiment.decay_type,
            half_life_hours=experiment.half_life_hours,
            gain=experiment.activation_gain,
            algorithm=experiment.reservoir_update,
        )
        for event in events:
            session.add(
                ReservoirEventRow(
                    id=new_id(),
                    experiment_id=experiment.id,
                    engine_id=engine_id,
                    concept_id=concept_id,
                    episode_id=event.episode_id,
                    observation_id=event.observation_id,
                    event_time=event.at.isoformat(),
                    event_kind=event.kind,
                    previous_level=event.previous_level,
                    level_after=event.level_after,
                    delta_hours=event.delta_hours,
                    observation_intensity=event.observation_intensity,
                )
            )
        for snapshot in snapshots:
            if snapshot.level is None:
                continue
            per_day[snapshot.day][concept_id] = {
                "level": snapshot.level,
                "observed": snapshot.observed,
                "observation_count": snapshot.observation_count,
            }
            counts[snapshot.day] += snapshot.observation_count
    cursor = day_from
    while cursor <= day_to:
        bucket = density.get(cursor, {"episodes": 0, "words": 0})
        session.add(
            DailySnapshot(
                id=new_id(),
                experiment_id=experiment.id,
                engine_id=engine_id,
                day=cursor.isoformat(),
                states=per_day[cursor],
                episode_count=bucket["episodes"],
                user_word_count=bucket["words"],
                observation_count=counts[cursor],
            )
        )
        cursor += timedelta(days=1)


def _moment(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _day(value: str) -> date:
    return utc_day(_moment(value))
