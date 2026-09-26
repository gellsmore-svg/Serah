# Temporal model

Reservoirs are an experimental instrument. The half-life is a parameter, not a psychological constant. The default experiment uses exponential decay, a 72-hour half-life, gain 0.35, and the bounded saturating update.

## Decay

Elapsed time is in hours.

Exponential:

```
R = R_previous × 0.5^(Δt / half_life)
```

Linear, included for comparison: the level is halved at one half-life and reaches 0 at two.

`none` leaves the level unchanged.

## Top-up

Decay is applied up to the observation time. Then:

```
effective = gain × observation
updated = 100 × (1 - (1 - decayed / 100) × (1 - effective / 100))
```

`gain` is clamped to `[0, 1]` and the observation to `[0, 100]`. The update cannot leave `[0, 100]`, and it cannot reduce the reservoir. A low score adds a small amount. It does not mean the previous activation vanished.

`replace`, which sets the reservoir to the latest observation, is available only as an explicit experiment setting. It is not the default.

## No observation

If a concept has never been observed, the snapshot omits it. That is not a zero.

After the first observation, a day with no observation decays from the previous clock time to the next UTC midnight and sets `observed: false`. No synthetic observation of 0 is written.

Several observations on the same day are applied in time order: decay to the event, top up, decay to the next event, then decay to midnight for the daily point. They are not averaged.

## Replay

`replay_concept` is a pure function. The database replay calls it once per concept per engine, then stores events and snapshots. Running it twice on the same observations and configuration produces the same levels. Changing the half-life requires a new replay and no engine calls.

Relevant-mode experiments apply an observation only when that episode was marked relevant for the concept. All-core experiments apply every stored observation for the engine.

The first activation starts from 0. There is no decay before a reservoir exists.
