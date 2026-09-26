# Model adapters

Every engine implements `evaluate` and `evaluate_batch`. Callers see `DecisionResult` only.

## The shared score instrument

Laya 0.3, Jev's documented score primitive, Kai's System One interface, and the Decider family's score primitive accept 2–10 ordered levels. Serah therefore asks a 10-level score question. Level index `i` is the intensity bin:

`0, 11, 22, 33, 44, 56, 67, 78, 89, 100`

The stored distribution is the provider's probabilities on those bins. Expected intensity is the probability-weighted sum. A generic expected-value function also accepts other bin sets. The worked example in the brief, with mass on 20 through 70, has expected intensity 47, and that case is tested. It is not what these providers are asked, because they would reject an 11-level rubric.

If a provider returns a scalar level and no probabilities, Serah stores `native_output_type=scalar_score` and interpolates the level onto the bins. It does not invent a distribution.

Distributions with a negative mass, or a sum more than 0.02 away from 1, are rejected. Sums within 0.02 are renormalised and the method string records that.

## Confidence

`distribution_concentration` is Serah's `1 - H / log(k)` over the stored distribution. `provider_confidence` is left null for System-1 score answers. Laya's field named `confidence` is normalised entropy (`agent.py`). Copying it into `provider_confidence` would give one quantity two names. The provider's field is kept under `provider_reported`.

## Mock

`mock` and `mock_conservative` are deterministic. They read the user evidence only, take the strongest lexicon anchor for the concept, and place a fixed peaked distribution on the ten bins. The conservative engine multiplies the anchor by 0.82 before peaking. Obligation pressure uses a high anchor when three or more of its markers are in the user text, and a low anchor otherwise. These engines exist so tests, CI, and the demo need no credentials. They are not a model of a person.

## Laya

`LayaDecisionEngine` imports `laya` and calls `Router.predict_batch`. Status checks the import only. Weights load on the first score, which also downloads a checkpoint on a cold machine. Serah's tests do not do that. Optional install: `pip install -e ".[laya]"`. `LAYA_DEVICE` and `LAYA_CHECKPOINT` are forwarded when set. This matches Laya 0.3.20 and the adapter shape already used by Keziah.

System-1 engines receive the user evidence as a plain string. Assistant context and the measurement instructions stay out of that state. The question text still carries the evidence rule. The LLM baseline is the exception: it is a language model, so it receives the user text and the context separately.

## Keziah

`keziah` sends the measurement to a running Keziah server. Set `SERAH_KEZIAH_BASE_URL` (for example `http://127.0.0.1:8766`) and optionally `SERAH_KEZIAH_MODEL` (default `mock`) and `SERAH_KEZIAH_API_KEY`. Serah posts `{model, state, questions, timeout_s, client_id}` to `/v1/systemone`. `state` is the user text only. Answers are read from the job result's `response.answers` and translated like any other System-1 score. If the `keziah` package imports, Serah uses `keziah.Client`. Otherwise it uses the same JSON over HTTP. An unset URL leaves the engine `NOT_CONFIGURED` and does not stop the rest of Serah.

## Jev

`SystemOneHttpEngine` posts `{"model", "state", "questions"}` to `{JEV_BASE_URL}/v1/systemone`, default host `https://api.typesafe.ai`, model `jev-latest`. The bearer token is read from `TYPESAFE_API_KEY`, then `JEV_API_KEY`. No key means `NOT_CONFIGURED`. Status does not call the network. A score run without a key raises and writes no observations.

## Kai

The Decision-1.0-Kai card says to call a System One endpoint you host. Serah uses that HTTP shape when `KAI_BASE_URL` is set, with `KAI_MODEL` defaulting to `Decision-1.0-Kai-0.6B`. A key is sent only if `KAI_API_KEY` is set. Serah does not download the weights.

## Decider

The Mapika Decider cards document `POST /v1/systemone` and `decider.infer.Decider(model).system_one(state, questions)`. If `DECIDER_BASE_URL` is set, Serah uses HTTP. Otherwise, if `DECIDER_MODEL` is set and the `decider` package imports, it uses the local class. If the response has no score probabilities, the call fails rather than inventing them. Weights are not downloaded by Serah.

## LLM baseline and the semantic layer

`SERAH_LLM_BASE_URL` plus `SERAH_LLM_MODEL` enable an OpenAI-compatible chat client. The measurement prompt asks for the ten bins, or a single intensity if the model will not give a distribution. Replies are parsed as JSON and validated. Malformed replies are retried and then failed.

The same client is used for episode extraction and taxonomy review when `SERAH_EXTRACTOR` or `SERAH_CURATOR` is `llm`. Those prompts tell the model that assistant text is context. The extractor may only return concept ids from the supplied taxonomy.

## Failure

One unavailable engine does not prevent startup, `serah doctor`, or scoring a different engine. Batch calls keep episode and concept ids attached to each result.
