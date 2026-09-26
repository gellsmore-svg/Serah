# Serah

Longitudinal probabilistic emotional-state observatory.

Serah takes chronological conversational text, keeps a versioned emotional taxonomy, asks pluggable System-1 decision engines the same measurement questions, and draws the resulting trajectories. A separate temporal model turns those observations into decaying reservoirs. Changing the half-life replays locally and does not call the models again.

## What it is not

Serah is not a diagnostic system, a risk score, a happiness score, or a claim that a model probability is psychological truth. A displayed value means: given this evidence, this concept definition, this question version, this engine, and this experimental temporal model, the derived intensity is this number on Serah's scale.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [DATA_MODEL.md](DATA_MODEL.md)
- [TAXONOMY.md](TAXONOMY.md)
- [TEMPORAL_MODEL.md](TEMPORAL_MODEL.md)
- [MODEL_ADAPTERS.md](MODEL_ADAPTERS.md)
- [PRIVACY.md](PRIVACY.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [SPEC_REVIEW.md](SPEC_REVIEW.md)

The sections below are completed as the implementation lands. The specification review is already recorded.
