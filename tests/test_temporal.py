from datetime import datetime, timezone

from serah.temporal import ObservationPoint, apply_decay, apply_update, replay_concept


def test_decay_forms():
    assert apply_decay(80, 72, "exponential", 72) == 40
    assert apply_decay(80, 0, "exponential", 72) == 80
    assert apply_decay(80, 5, "none", 72) == 80
    assert apply_decay(80, 72, "linear", 72) == 40
    assert apply_decay(80, 144, "linear", 72) == 0


def test_low_observation_does_not_erase_and_stays_bounded():
    topped = apply_update(80, 10, 0.35, "bounded_saturating")
    assert topped > 80
    assert 0 <= topped <= 100
    assert apply_update(0, 100, 1, "bounded_saturating") == 100
    assert apply_update(100, 100, 1, "bounded_saturating") == 100
    assert apply_update(40, 0, 0.35, "bounded_saturating") == 40


def test_no_observation_decays_and_low_observation_does_not():
    start = datetime(2024, 3, 1, 12, tzinfo=timezone.utc)
    later = datetime(2024, 3, 2, 12, tzinfo=timezone.utc)
    quiet, _events = replay_concept(
        [ObservationPoint(start, 80)],
        start.date(),
        later.date(),
        decay_type="exponential",
        half_life_hours=72,
        gain=0.35,
        algorithm="bounded_saturating",
    )
    low, _events = replay_concept(
        [ObservationPoint(start, 80), ObservationPoint(later, 10)],
        start.date(),
        later.date(),
        decay_type="exponential",
        half_life_hours=72,
        gain=0.35,
        algorithm="bounded_saturating",
    )
    assert quiet[1].observed is False
    assert low[1].observed is True
    assert low[1].level > quiet[1].level
    assert quiet[1].level < quiet[0].level


def test_intraday_events_are_not_averaged():
    morning = datetime(2024, 3, 3, 9, tzinfo=timezone.utc)
    evening = datetime(2024, 3, 3, 21, tzinfo=timezone.utc)
    sequential, _events = replay_concept(
        [ObservationPoint(morning, 80), ObservationPoint(evening, 30)],
        morning.date(),
        morning.date(),
        decay_type="none",
        half_life_hours=72,
        gain=1,
        algorithm="bounded_saturating",
    )
    averaged, _events = replay_concept(
        [ObservationPoint(evening, 55)],
        morning.date(),
        morning.date(),
        decay_type="none",
        half_life_hours=72,
        gain=1,
        algorithm="bounded_saturating",
    )
    assert sequential[0].level != averaged[0].level
    assert sequential[0].observation_count == 2
