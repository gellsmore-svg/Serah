# Taxonomy

Version 0.1 starts from fourteen locked emotions:

anger, fear, anxiety, sadness, joy, love, gratitude, hope, shame, guilt, frustration, loneliness, contentment, calm.

Ids look like `emotion.anger`. Locked concepts are seeded as active from `1970-01-01`, so every later day can use them. A curator cannot deprecate a locked concept and cannot change its definition. A person can revise the definition explicitly. That writes `CONCEPT_DEFINITION_REVISED`, a new version, and a new measurement question. Old observations keep the old version.

## Emotions and compressions

An emotion is a felt state named in the user's evidence. A compression is a recurrent pattern that couples several of feelings, bodily sensations, expectations, impulses, and what happens when the demand is met. Obligation pressure is the demo compression: duty, stomach tightness, urgency, and relief after the duty is done. It is not a synonym for fear, and the name is descriptive rather than diagnostic.

Engines score a compression directly from its definition and the evidence. The score is not a formula over the component emotions.

## Candidate lifecycle

New concepts start as `proposed`. Support is counted in distinct UTC days.

- `SERAH_CANDIDATE_DAYS` (default 2) moves `proposed` to `candidate`.
- `SERAH_ACTIVE_DAYS` (default 3) moves a candidate to `active`.
- At most `SERAH_MAX_PROPOSALS_PER_DAY` (default 2) proposals are applied.
- A proposal whose name matches an existing concept adds support to that concept instead of creating a twin.
- Supporting episode ids must belong to the day being reviewed.
- Relevance for a new concept is recorded only once it is active, and only for that day's supporting episodes. Earlier days are not backfilled.

The mock curator proposes obligation pressure when at least three of its markers appear in user text. On the fictional history that is proposed on 6 March 2024, candidate on 8 March, and active on 11 March. Reconstructing 10 March does not show it as active.

A person can activate, reject, or mark dormant from the taxonomy screen or the API. Rejection of a locked concept is refused.

## Events

Evolution is appended. The live row is the latest causal state. `reconstruct(session, day)` replays events and is what tests use to prove the history.

Relationship types: `COMPOSED_OF`, `ASSOCIATED_WITH`, `AMPLIFIES`, `INHIBITS`, `PRECEDES`, `FOLLOWS`, `TRIGGERS`, `PART_OF`, `RELATED_TO`. Each stored relationship keeps confidence, the concept version, who created it, and episode ids when they exist.

## Curator

`SERAH_CURATOR=mock` is the default. `SERAH_CURATOR=llm` calls an OpenAI-compatible chat endpoint with `prompts/taxonomy_review/v1.md` and validates the JSON. A failed LLM review stops that run. It does not silently switch to the mock curator. Prompts for extraction, candidate review, compression discovery, and measurement live under `src/serah/prompts/`.

Merge and split are human actions. They record events and do not move or delete old observations. A merged concept is deprecated and stops receiving new scores. Its history stays under the old id.
