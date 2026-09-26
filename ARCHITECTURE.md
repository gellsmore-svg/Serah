# Architecture

Serah is one Python process, one SQLite database, and a browser UI served by that process. There is no queue, no second service, and no shared remote store.

## Layers

| Layer | What it is | What it is not |
| --- | --- | --- |
| Evidence | Canonical messages and extracted user episodes | An interpretation |
| Taxonomy | Versioned concepts, candidates, and events | A score |
| Measurement | One engine's distribution or scalar for one episode and concept | A reservoir, and not an average across engines |
| Temporal state | A replay of those observations under one decay configuration | A new model call |
| Visualisation | Charts, a day view, taxonomy, and drill-down | A diagnosis |

Observations are immutable. Replay deletes and rewrites only `reservoir_events` and `daily_snapshots` for the experiment being replayed.

## Causal days

A calendar day is UTC. Processing walks days in order. The taxonomy curator for a day sees the taxonomy as it exists that morning and the episodes of that day. It does not see later days. Events store `causal_mode=causal`. The column exists so a later retrospective pass can be marked. Version 0.1 never writes `retrospective`.

Reconstruction at date T applies causal events with `effective_on <= T`.

## One taxonomy, many scorers

An experiment names the engines, the scoring mode it expects (`relevant` or `all-core`), and one temporal configuration: decay type, half-life, gain, and update rule. Those settings are identical for every engine in the experiment. Laya does not receive a different definition from Jev for the same concept version.

`relevant` scores concepts the curator marked for that episode. `all-core` also scores every locked core emotion. A relevant-mode replay ignores observations that have no relevance row, so an all-core pass does not silently fill earlier gaps with zeros.

## Engines

`DecisionEngine.evaluate` and `evaluate_batch` return a `DecisionResult`. Provider JSON stops there. The result records `native_output_type` and `normalisation_method`. Batching groups questions that share an episode. It does not reorder taxonomy days.

Identical requests are cached by a hash of engine, fingerprint, evidence, concept version, question version, and instructions. Scoring is also stage-marked, so a crash resumes after the last stored observation.

## Where text is allowed to go

The mock stack can run with no network. Configured adapters call out only when a score or a curator run asks them to. Logs and import warnings do not include message text. The local API does, because that is the point of the drill-down, and it binds to `127.0.0.1` by default.
