"""Application errors. Messages stay free of evidence text."""


class SerahError(Exception):
    """Base error for expected Serah failures."""


class DistributionError(SerahError):
    """A probability distribution was missing, negative, or too far from 1."""


class EngineUnavailable(SerahError):
    """The engine is not configured or its package is not installed."""


class EngineError(SerahError):
    """The engine was configured but the call failed."""


class CuratorError(SerahError):
    """The taxonomy curator did not return valid structured output."""


class ExtractorError(SerahError):
    """The episode extractor did not return valid structured output."""
