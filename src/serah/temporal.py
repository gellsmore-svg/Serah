"""Experimental reservoir decay and top-up.

These are instrument parameters. Nothing here is a psychological constant.
A low observation tops the reservoir up by a small amount. It does not pull
the reservoir down. Only decay reduces a reservoir. Absence of an observation
is not passed to the update function at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

UTC = timezone.utc


def utc_day(moment: datetime) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).date()


def start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def end_of_day(day: date) -> datetime:
    """Next UTC midnight. The snapshot clock shared by every concept and engine."""
    return start_of_day(day + timedelta(days=1))


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def apply_decay(previous: float, delta_hours: float, decay_type: str, half_life_hours: float) -> float:
    if delta_hours < 0:
        raise ValueError("elapsed time cannot be negative")
    if delta_hours == 0 or decay_type == "none":
        return float(previous)
    if decay_type not in {"exponential", "linear"}:
        raise ValueError(f"unknown decay type: {decay_type}")
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    if decay_type == "exponential":
        return float(previous) * (0.5 ** (delta_hours / half_life_hours))
    factor = 1.0 - 0.5 * (delta_hours / half_life_hours)
    return max(0.0, float(previous) * factor)


def apply_update(decayed: float, observation: float, gain: float, algorithm: str) -> float:
    """Top up a decayed reservoir. ``replace`` exists only as an explicit contrast."""
    decayed = min(100.0, max(0.0, float(decayed)))
    observation = min(100.0, max(0.0, float(observation)))
    gain = min(1.0, max(0.0, float(gain)))
    if algorithm == "replace":
        return observation
    if algorithm != "bounded_saturating":
        raise ValueError(f"unknown reservoir update: {algorithm}")
    effective = gain * observation
    updated = 100.0 * (1.0 - (1.0 - decayed / 100.0) * (1.0 - effective / 100.0))
    return min(100.0, max(0.0, updated))


@dataclass(frozen=True)
class ObservationPoint:
    at: datetime
    intensity: float
    observation_id: str | None = None
    episode_id: str | None = None


@dataclass(frozen=True)
class ReservoirEvent:
    at: datetime
    kind: str
    previous_level: float | None
    level_after: float
    delta_hours: float
    observation_id: str | None
    episode_id: str | None
    observation_intensity: float | None


@dataclass(frozen=True)
class DaySnapshot:
    day: date
    level: float | None
    observed: bool
    observation_count: int


def replay_concept(
    observations: list[ObservationPoint],
    day_from: date,
    day_to: date,
    *,
    decay_type: str,
    half_life_hours: float,
    gain: float,
    algorithm: str,
) -> tuple[list[DaySnapshot], list[ReservoirEvent]]:
    """Replay one concept for one engine. Identical inputs produce identical output."""
    if day_to < day_from:
        raise ValueError("day_to is before day_from")
    ordered = sorted(observations, key=lambda item: (item.at, item.observation_id or ""))
    by_day: dict[date, list[ObservationPoint]] = {}
    for item in ordered:
        moment = item.at if item.at.tzinfo else item.at.replace(tzinfo=UTC)
        by_day.setdefault(utc_day(moment), []).append(
            ObservationPoint(moment, item.intensity, item.observation_id, item.episode_id)
        )

    level: float | None = None
    last_time: datetime | None = None
    snapshots: list[DaySnapshot] = []
    events: list[ReservoirEvent] = []
    day = day_from
    while day <= day_to:
        midnight = end_of_day(day)
        todays = by_day.get(day, [])
        if level is None and not todays:
            snapshots.append(DaySnapshot(day, None, False, 0))
            day += timedelta(days=1)
            continue
        if todays:
            for item in todays:
                if level is None or last_time is None:
                    updated = apply_update(0.0, item.intensity, gain, algorithm)
                    events.append(
                        ReservoirEvent(
                            item.at, "activation", 0.0, updated, 0.0,
                            item.observation_id, item.episode_id, item.intensity,
                        )
                    )
                    level = updated
                    last_time = item.at
                else:
                    delta = hours_between(last_time, item.at)
                    decayed = apply_decay(level, delta, decay_type, half_life_hours)
                    if delta > 0:
                        events.append(
                            ReservoirEvent(
                                item.at, "decay", level, decayed, delta,
                                None, None, None,
                            )
                        )
                    updated = apply_update(decayed, item.intensity, gain, algorithm)
                    events.append(
                        ReservoirEvent(
                            item.at, "activation", decayed, updated, 0.0,
                            item.observation_id, item.episode_id, item.intensity,
                        )
                    )
                    level = updated
                    last_time = item.at
        assert level is not None and last_time is not None
        delta = hours_between(last_time, midnight)
        decayed = apply_decay(level, delta, decay_type, half_life_hours)
        if delta > 0:
            events.append(
                ReservoirEvent(
                    midnight, "decay_to_midnight" if todays else "no_observation_decay",
                    level, decayed, delta, None, None, None,
                )
            )
        level = decayed
        last_time = midnight
        snapshots.append(DaySnapshot(day, level, bool(todays), len(todays)))
        day += timedelta(days=1)
    return snapshots, events
