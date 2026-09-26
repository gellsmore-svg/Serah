"""Translate a System-1 score answer into Serah's intensity instrument.

The provider's own confidence field is preserved under provider_reported.
It is not copied into provider_confidence, because for these score primitives
that field is an entropy-style concentration rather than a separate certainty.
"""

from __future__ import annotations

from serah.distributions import (
    DistributionError,
    level_index_distribution,
    level_to_intensity,
    metrics,
    validate_distribution,
)
from serah.errors import EngineError


def from_score_answer(answer: dict, *, source: str) -> dict:
    if not isinstance(answer, dict):
        raise EngineError(f"{source} score answer was not an object")
    reported = {}
    if "confidence" in answer:
        reported[f"{source}_confidence"] = answer.get("confidence")
        reported[f"{source}_confidence_meaning"] = "provider_field_not_used_as_provider_confidence"
    if "score" in answer:
        reported[f"{source}_score"] = answer.get("score")
    probabilities = answer.get("probabilities")
    if isinstance(probabilities, dict) and probabilities:
        try:
            distribution, method = level_index_distribution(probabilities)
        except DistributionError as exc:
            raise EngineError(f"{source} distribution was rejected") from exc
        summary = metrics(distribution)
        normalisation = "level_index_to_intensity_bins"
        if method != "as_provided":
            normalisation = f"{normalisation}+{method}"
        return {
            "native_output_type": "ordinal_distribution",
            "normalisation_method": normalisation,
            "distribution": {str(bin_value): probability for bin_value, probability in distribution.items()},
            "expected_intensity": summary.expected,
            "provider_confidence": None,
            "distribution_concentration": summary.concentration,
            "distribution_entropy": summary.entropy,
            "modal_bin": summary.modal_bin,
            "spread": summary.spread,
            "provider_reported": reported,
        }
    if "score" in answer:
        try:
            intensity = level_to_intensity(float(answer["score"]))
        except (TypeError, ValueError, DistributionError) as exc:
            raise EngineError(f"{source} scalar score was rejected") from exc
        return {
            "native_output_type": "scalar_score",
            "normalisation_method": "linear_level_index_to_0_100",
            "distribution": None,
            "expected_intensity": intensity,
            "provider_confidence": None,
            "distribution_concentration": None,
            "distribution_entropy": None,
            "modal_bin": None,
            "spread": None,
            "provider_reported": reported,
        }
    raise EngineError(f"{source} score answer had neither probabilities nor a score")


def from_bin_distribution(bins: dict, *, method: str) -> dict:
    try:
        distribution, applied = validate_distribution(bins)
    except DistributionError as exc:
        raise EngineError("distribution was rejected") from exc
    summary = metrics(distribution)
    normalisation = method if applied == "as_provided" else f"{method}+{applied}"
    return {
        "native_output_type": "ordinal_distribution",
        "normalisation_method": normalisation,
        "distribution": {str(bin_value): probability for bin_value, probability in distribution.items()},
        "expected_intensity": summary.expected,
        "provider_confidence": None,
        "distribution_concentration": summary.concentration,
        "distribution_entropy": summary.entropy,
        "modal_bin": summary.modal_bin,
        "spread": summary.spread,
        "provider_reported": {},
    }
