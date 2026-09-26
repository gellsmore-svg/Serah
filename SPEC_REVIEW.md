# Specification review

This review was done before implementation, against the Serah brief and against the providers and repository conventions actually present on 2026-09-26.

The quality vector Q1–Q14 is scored 0–100. The confidence vector C1–C14 is how well supported that quality score is, from 0 to 1. Scores are design diagnostics. They are not measurements of a running system, and stability is not verification.

Reviewer: the implementing agent, in one session. Provider behaviour was checked in the installed Laya 0.3.20 package, the local Keziah adapters, TypeSafe's public score documentation, and the Kai and Decider model cards. No separate hidden reasoning trace is stored here.

## Dimensions

| id | dimension |
| --- | --- |
| Q1 | conceptual fidelity |
| Q2 | evidence / interpretation separation |
| Q3 | dynamic taxonomy design |
| Q4 | System-1 abstraction quality |
| Q5 | probability / distribution semantics |
| Q6 | temporal reservoir semantics |
| Q7 | replay determinism |
| Q8 | provenance / traceability |
| Q9 | visual comparability |
| Q10 | privacy / data safety |
| Q11 | implementation feasibility |
| Q12 | testability |
| Q13 | extensibility without over-engineering |
| Q14 | GitHub / repository completeness |

Critical bar: no dimension below 88. Stop when, for two consecutive iterations, every absolute Q change is at most 2 and every absolute C change is at most 0.03, with no unresolved architectural contradiction. Cap: 6 iterations.

## Iteration 1 — brief read literally

The brief's layer split is sound. Implementing it literally would still collide with the engines it names.

| | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Q13 | Q14 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q | 86 | 90 | 84 | 78 | 74 | 88 | 86 | 88 | 86 | 92 | 76 | 88 | 84 | 80 |
| C | 0.72 | 0.80 | 0.74 | 0.86 | 0.88 | 0.80 | 0.70 | 0.74 | 0.72 | 0.84 | 0.82 | 0.76 | 0.74 | 0.86 |

Weakest: Q5, Q11, Q4, Q14, Q3.

Issues and corrections:

1. **Eleven intensity bins cannot be a native System-1 score question.** Laya, Jev's documented score primitive, Kai's System One interface, and Decider's score primitive accept 2–10 ordered levels. Keziah rejects score criteria outside that range. Inventing an 11-bin distribution from a 10-level answer would fabricate probabilities the model did not produce.
   Action: the shared instrument is a 10-level rubric. Level index `i` maps to intensity bin `[0, 11, 22, 33, 44, 56, 67, 78, 89, 100]`. The stored distribution is the provider's probabilities on those bins. Expected intensity is `Σ p(bin) × bin`. A generic expected-value function still accepts other bin sets, including the brief's 11-bin example, so that calculation is tested directly. A scalar score with no probabilities stays a scalar. `native_output_type` and `normalisation_method` record which path was used.

2. **Laya's field named `confidence` is normalised entropy** (`1 - H/log(k)` in `agent.py`). Copying it into `provider_confidence` would mix two names for one quantity.
   Action: `distribution_concentration` is always computed by Serah from the stored distribution. The provider's own field is kept under `provider_reported` and is not copied into `provider_confidence`.

3. **A calendar day must be UTC.** Local timezones would make the same observations replay differently across machines.
   Action: day boundaries are UTC. The daily snapshot is the reservoir at the next UTC midnight, after intraday events have been applied in order.

4. **A low score must not erase a reservoir, and a missing day must not become zero.** The bounded saturating update only adds. Decay is the only downward force in v0.1.
   Action: no observation means no observation row and no top-up. A stored low intensity is a real observation and a small top-up. The replay test covers both.

5. **Kai and Decider are not importable libraries in this environment, and their weights are large.** Kai's card says to call a System One endpoint. Decider's card documents `decider.infer.Decider` and `POST /v1/systemone`. Downloading weights would also be unsafe on a nearly full Windows system disk that backs this WSL image.
   Action: real adapters call those documented interfaces when configured. Otherwise status is `NOT_CONFIGURED`. They never invent scores. Laya is a real adapter around `Router.predict` / `predict_batch` and does not load weights during health checks. Jev is a real `POST /v1/systemone` client and is not called without a key.

6. **Licence.** Apache-2.0 is the established licence on the public Python siblings (Keziah, Hoglah, Deborah, and most of the rest). Serah follows that pattern rather than omitting a licence or choosing a different one.

7. **Candidate growth and locked definitions.** The curator may propose. Code enforces distinct-day thresholds, a per-day proposal cap, and no automatic merge. Locked definitions change only through an explicit versioned human revision. Curator suggestions about locked copy are stored and not applied.

8. **One causal taxonomy in v0.1.** Events carry `causal_mode`. The pipeline writes `causal` only. Retrospective backfill is a later, explicitly marked path.

9. **Comparison without credentials.** Two deterministic engines, `mock` and `mock_conservative`, share evidence, taxonomy, questions, and decay, and differ only by a documented scoring bias. They are instruments for tests and the demo, not claims about a person.

## Iteration 2 — architecture after those corrections

| | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Q13 | Q14 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q | 94 | 95 | 92 | 93 | 94 | 95 | 94 | 93 | 93 | 96 | 91 | 93 | 92 | 93 |
| C | 0.86 | 0.88 | 0.84 | 0.88 | 0.90 | 0.90 | 0.86 | 0.84 | 0.82 | 0.90 | 0.86 | 0.84 | 0.82 | 0.88 |

No dimension is below 88. Deltas from iteration 1 are large, which is the point of the revision, so this is not yet stable.

## Iteration 3 — small tightenings

Additional decisions, none of which reopen the layer split:

- Renormalise a distribution only when every mass is non-negative and the sum is within 0.02 of 1. Otherwise reject it. Exact sums are kept as provided.
- Linear decay, when selected, is half the level at one half-life and zero at two. It is an experimental option beside exponential decay and no decay.
- Human merge, split, exclusion, and flags append audit or taxonomy events. Rows of model output are not deleted.
- Extraction and scoring record stage marks so a rerun skips completed work instead of repeating model calls.
- A curator run that was requested as `llm` and fails does not silently switch to the mock curator.

| | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Q13 | Q14 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q | 94 | 95 | 93 | 93 | 95 | 95 | 95 | 94 | 93 | 96 | 91 | 93 | 92 | 93 |
| C | 0.86 | 0.88 | 0.85 | 0.88 | 0.91 | 0.90 | 0.88 | 0.86 | 0.83 | 0.90 | 0.86 | 0.85 | 0.83 | 0.88 |

Maximum absolute Q change from iteration 2: 1. Maximum absolute C change: 0.02.

## Iteration 4 — confirmation

The same architecture was re-scored. No further design change was required. Remaining uncertainty is operational (whether a future provider build returns probabilities under a different key), and it is already handled by rejecting malformed distributions rather than by guessing.

| | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Q13 | Q14 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q | 94 | 95 | 93 | 93 | 95 | 95 | 95 | 94 | 93 | 96 | 91 | 93 | 92 | 93 |
| C | 0.86 | 0.88 | 0.85 | 0.88 | 0.91 | 0.90 | 0.88 | 0.86 | 0.83 | 0.90 | 0.86 | 0.85 | 0.83 | 0.88 |

Maximum absolute Q change from iteration 3: 0. Maximum absolute C change: 0.

Stabilised on iterations 3 and 4. No critical dimension is below 88. No architectural contradiction left open.

## Locked v0.1 decisions

- Layers stay separate: evidence, taxonomy, measurement, reservoir, visualisation.
- User text is evidence. Assistant text is context. Endorsement has to be in the user's words.
- Shared causal taxonomy across engines. Scoring differences are the comparison.
- Observations are immutable. Decay settings replay locally.
- No observation is not a zero observation.
- Reservoirs use one shared temporal configuration per experiment.
- Mock engines make the whole application runnable with no credentials and no weight download.
- Real adapters: Laya (local library), Jev (TypeSafe HTTP), Kai (System One HTTP), Decider (HTTP or the documented Python package), optional OpenAI-compatible LLM baseline.
- Personal exports, databases, caches, and secrets stay out of git.
- Apache-2.0, matching the public sibling convention.

## Unresolved, accepted for v0.1

- Retrospective backfill is represented in the schema and not implemented as a pipeline.
- Per-concept half-lives are a later configuration, not a v0.1 default.
- Kai and Decider are not scored in the default demo, because no local weights or endpoints are configured.
- The 10-bin rubric is an instrument choice forced by today's System-1 score limit. It is versioned, so a later provider that natively emits another scale can be stored without rewriting history.
