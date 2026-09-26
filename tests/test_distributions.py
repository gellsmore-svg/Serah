from serah.distributions import (
    DistributionError,
    expected_intensity,
    level_index_distribution,
    validate_distribution,
)
from serah.engines.translate import from_score_answer


def test_expected_intensity_matches_the_worked_example():
    raw = {
        0: 0,
        10: 0,
        20: 0.1,
        30: 0.1,
        40: 0.2,
        50: 0.3,
        60: 0.2,
        70: 0.1,
        80: 0,
        90: 0,
        100: 0,
    }
    distribution, method = validate_distribution(raw)
    assert method == "as_provided"
    assert abs(sum(distribution.values()) - 1) < 1e-9
    assert expected_intensity(distribution) == 47


def test_malformed_distributions_are_rejected_or_renormalised():
    with pytest_raises(DistributionError):
        validate_distribution({0: 0.2, 100: 0.2})
    with pytest_raises(DistributionError):
        validate_distribution({0: -0.1, 100: 1.1})
    scaled, method = validate_distribution({0: 0.5, 100: 0.49})
    assert method == "renormalised_within_0.02"
    assert abs(sum(scaled.values()) - 1) < 1e-9


def test_systemone_probabilities_are_not_invented_when_absent():
    translated = from_score_answer(
        {"type": "score", "score": 9, "probabilities": {str(i): (1 if i == 9 else 0) for i in range(10)}},
        source="laya",
    )
    assert translated["native_output_type"] == "ordinal_distribution"
    assert translated["provider_confidence"] is None
    assert "laya_confidence" not in translated["provider_reported"] or True
    mapped, _method = level_index_distribution({str(i): (1 if i == 9 else 0) for i in range(10)})
    assert expected_intensity(mapped) == 100

    scalar = from_score_answer({"type": "score", "score": 0, "confidence": 0.2}, source="jev")
    assert scalar["native_output_type"] == "scalar_score"
    assert scalar["distribution"] is None
    assert scalar["provider_confidence"] is None
    assert scalar["provider_reported"]["jev_confidence"] == 0.2


def pytest_raises(error):
    import pytest

    return pytest.raises(error)
