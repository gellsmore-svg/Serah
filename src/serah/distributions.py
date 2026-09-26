"""Ordinal intensity distributions.

Serah's display scale is 0–100. System-1 score primitives currently accept at most
ten ordered levels, so the shared instrument uses ten bins. Expected intensity is
the probability-weighted sum of bin values. This module does not invent a
distribution a provider did not return.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from serah.errors import DistributionError

# Level index i of a 10-level System-1 score maps to these intensity bins.
INSTRUMENT_BINS: tuple[float, ...] = (0, 11, 22, 33, 44, 56, 67, 78, 89, 100)

# Renormalise only inside this absolute distance from 1. Wider gaps are rejected.
RENORMALISE_TOLERANCE = 0.02

LEVEL_DESCRIPTIONS: tuple[str, ...] = (
    "Absent. The user's evidence does not express this concept.",
    "Faint trace. A weak or passing hint, easy to miss.",
    "Mild. Present but slight, and not a focus of the evidence.",
    "Noticeable. Clearly present at a low intensity.",
    "Moderate-low. A steady but limited presence.",
    "Moderate. A clear part of what the user expresses, without dominating it.",
    "Elevated. Strong enough to shape the passage.",
    "Strong. A dominant thread in the user's expression.",
    "Very strong. The passage is largely organised around this concept.",
    "Maximal. The concept saturates the user's expressed state in this evidence.",
)


@dataclass(frozen=True)
class DistributionMetrics:
    expected: float
    entropy: float
    concentration: float
    spread: float
    modal_bin: float


def expected_intensity(distribution: dict[float, float]) -> float:
    """Probability-weighted intensity. Bins may be any numeric set."""
    return sum(float(bin_value) * float(probability) for bin_value, probability in distribution.items())


def _entropy(probabilities: list[float]) -> float:
    total = 0.0
    for probability in probabilities:
        if probability > 0.0:
            total -= probability * math.log(probability)
    return total


def metrics(distribution: dict[float, float]) -> DistributionMetrics:
    probabilities = [float(value) for value in distribution.values()]
    expected = expected_intensity(distribution)
    variance = sum(
        float(probability) * (float(bin_value) - expected) ** 2
        for bin_value, probability in distribution.items()
    )
    entropy = _entropy(probabilities)
    count = len(probabilities)
    if count > 1:
        concentration = 1.0 - entropy / math.log(count)
    else:
        concentration = 1.0
    modal = max(distribution, key=lambda bin_value: (distribution[bin_value], -float(bin_value)))
    return DistributionMetrics(
        expected=expected,
        entropy=entropy,
        concentration=max(0.0, min(1.0, concentration)),
        spread=math.sqrt(max(0.0, variance)),
        modal_bin=float(modal),
    )


def validate_distribution(raw: dict) -> tuple[dict[float, float], str]:
    """Return a canonical distribution and the normalisation method applied.

    ``as_provided`` means the masses already summed to 1.
    ``renormalised_within_0.02`` means they were scaled because the gap was small.
    """
    if not isinstance(raw, dict) or not raw:
        raise DistributionError("distribution must be a non-empty object")
    parsed: dict[float, float] = {}
    for key, value in raw.items():
        try:
            bin_value = float(key)
            probability = float(value)
        except (TypeError, ValueError) as exc:
            raise DistributionError("distribution keys and values must be numeric") from exc
        if probability < 0.0 or math.isnan(probability) or math.isinf(probability):
            raise DistributionError("distribution contains a negative or non-finite mass")
        if math.isnan(bin_value) or math.isinf(bin_value):
            raise DistributionError("distribution contains a non-finite bin")
        parsed[bin_value] = parsed.get(bin_value, 0.0) + probability
    total = sum(parsed.values())
    if total <= 0.0:
        raise DistributionError("distribution has no probability mass")
    if abs(total - 1.0) <= 1e-9:
        return parsed, "as_provided"
    if abs(total - 1.0) <= RENORMALISE_TOLERANCE:
        scaled = {bin_value: probability / total for bin_value, probability in parsed.items()}
        # Keep the stored masses summing to 1 despite binary rounding.
        drift = 1.0 - sum(scaled.values())
        last = next(reversed(scaled))
        scaled[last] += drift
        return scaled, "renormalised_within_0.02"
    raise DistributionError("distribution sum is outside the 0.02 tolerance")


def level_index_distribution(probabilities: dict) -> tuple[dict[float, float], str]:
    """Map a System-1 score probability map keyed by level index onto instrument bins."""
    if len(INSTRUMENT_BINS) != len(LEVEL_DESCRIPTIONS):
        raise DistributionError("instrument bins and descriptions disagree")
    mapped: dict[float, float] = {}
    for key, value in probabilities.items():
        try:
            index = int(str(key))
        except (TypeError, ValueError) as exc:
            raise DistributionError("score probabilities must be keyed by level index") from exc
        if index < 0 or index >= len(INSTRUMENT_BINS):
            raise DistributionError("score level index is outside the 10-level instrument")
        mapped[INSTRUMENT_BINS[index]] = float(value)
    if len(mapped) != len(probabilities):
        raise DistributionError("score probabilities repeated a level index")
    return validate_distribution(mapped)


def level_to_intensity(score: float, bins: tuple[float, ...] = INSTRUMENT_BINS) -> float:
    """Interpolate a scalar level index onto bin intensities. This does not invent masses."""
    if not bins:
        raise DistributionError("no bins configured")
    if score <= 0:
        return float(bins[0])
    if score >= len(bins) - 1:
        return float(bins[-1])
    lower = int(math.floor(score))
    fraction = score - lower
    return float(bins[lower]) * (1.0 - fraction) + float(bins[lower + 1]) * fraction


def peaked_distribution(intensity: float, sigma: float = 18.0) -> dict[float, float]:
    """Deterministic distribution peaked on ``intensity``. Used only by the mock engines."""
    weights = {
        bin_value: math.exp(-0.5 * ((bin_value - intensity) / sigma) ** 2)
        for bin_value in INSTRUMENT_BINS
    }
    total = sum(weights.values())
    scaled = {bin_value: weight / total for bin_value, weight in weights.items()}
    drift = 1.0 - sum(scaled.values())
    last = INSTRUMENT_BINS[-1]
    scaled[last] += drift
    return scaled
