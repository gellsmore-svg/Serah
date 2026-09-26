# Data model

SQLite via SQLAlchemy. `alembic upgrade head` creates the same tables as application startup (`Base.metadata.create_all` in revision `001_initial`). JSON columns hold raw provider payloads, distributions, and flexible metadata. Queryable fields are real columns.

Timestamps are ISO-8601 UTC strings. Days are `YYYY-MM-DD` in UTC.

## Evidence

- `conversations`, `messages` — source rows. Unique on `(source_type, external_id)` and `(conversation_id, external_id)`. Message ids are UUID5 over the source ids, so a repeated import is stable.
- `import_warnings` — malformed or incomplete records. The warning text does not quote the message.
- `episodes` — user text, context text, extractor, prompt version, confidence, bodily signals, exclusion flag.
- `episode_messages` — which source rows are `evidence` and which are `context`.

An excluded episode remains in the table. Replay skips it. Observations already stored for it remain.

## Taxonomy

- `taxonomy_concepts` — stable id, family (`emotion` or `compression`), status, locked flag, support day count.
- `taxonomy_concept_versions` — definition, inclusion, exclusion, source, `effective_on`.
- `taxonomy_events` — the log. Types include the brief's set plus `CONCEPT_STATUS_CHANGED`, `CONCEPT_DEFINITION_SUGGESTED`, and `TAXONOMY_REVIEWED`.
- `taxonomy_relationships` — source, target, relation, confidence, concept version, evidence ids, `created_on`, `removed_on`.
- `concept_support` — concept, episode, day. Unique per pair.
- `episode_relevance` — concepts the curator marked for an episode. This is what `relevant` scoring and replay consult.
- `measurement_questions` — rendered instructions and the ten level descriptions. A new concept version gets a new question version. Old questions are not edited.

Candidates are concepts whose status is `proposed`, `candidate`, `dormant`, `rejected`, or `deprecated`. There is not a second concept table.

## Measurement

- `model_observations` — one row per episode, concept, engine, concept version, and question version. Distribution JSON, expected intensity, entropy, concentration, spread, modal bin, provider confidence (usually null), provider-reported fields, raw response, latency, cache flag, evidence hash. `flagged` and `excluded` do not delete the row.
- `inference_cache` — keyed by the request hash.
- `processing_runs`, `stage_marks` — run stats and resume cursors. Stage marks use ids, not text.

## Derived state

- `experiments` — engines, decay, half-life, gain, update rule, scoring mode, app version.
- `reservoir_events` — decay and activation steps, with observation ids where an activation happened.
- `daily_snapshots` — end-of-UTC-day levels per engine. A concept key is absent until that concept has had an observation. After that, `observed: false` means the day contributed no observation and the level is decay only.

Snapshots are regenerable. Deleting them does not delete observations.

## Human channels

- `annotations` — a note on a day. Not an observation.
- `self_ratings` — day, concept, 0–100, note. Not written over model rows.
- `audit_events` — exclusions, flags, merges, and other explicit edits.

## Provenance

An observation points at an episode, a concept version, a question version, an engine, a model id, and a processing run. The episode points at message ids. The concept version points at a taxonomy event. The reservoir event points at the observation. The UI walks that chain.
