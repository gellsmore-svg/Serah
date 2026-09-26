"""Deterministic lexicon shared by the mock extractor, curator, and mock engines.

Real System-1 engines do not use this file. It exists so the offline instrument
is inspectable and repeatable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LexiconHit:
    concept_id: str
    intensity: float
    pattern: str


# Word-boundary patterns. Intensities are mock-instrument anchors, not findings.
_PATTERN_ROWS: tuple[tuple[str, str, float], ...] = (
    ("emotion.anger", r"\bfurious\b", 90),
    ("emotion.anger", r"\brage\b", 88),
    ("emotion.anger", r"\blivid\b", 86),
    ("emotion.anger", r"\banger\b", 72),
    ("emotion.anger", r"\bangry\b", 70),
    ("emotion.fear", r"\bafraid\b", 64),
    ("emotion.fear", r"\bscared\b", 66),
    ("emotion.fear", r"\bfrightened\b", 70),
    ("emotion.fear", r"\bfear\b", 60),
    ("emotion.anxiety", r"\banxious\b", 48),
    ("emotion.anxiety", r"\banxiety\b", 50),
    ("emotion.anxiety", r"\bon edge\b", 36),
    ("emotion.anxiety", r"\buneasy\b", 34),
    ("emotion.anxiety", r"\bworried\b", 40),
    ("emotion.sadness", r"\bsadness\b", 60),
    ("emotion.sadness", r"\bsad\b", 55),
    ("emotion.sadness", r"\bgrief\b", 75),
    ("emotion.sadness", r"\bheartbroken\b", 80),
    ("emotion.joy", r"\bjoy\b", 70),
    ("emotion.joy", r"\bjoyful\b", 74),
    ("emotion.joy", r"\bdelighted\b", 72),
    ("emotion.love", r"\blove\b", 74),
    ("emotion.love", r"\baffection\b", 64),
    ("emotion.gratitude", r"\bgrateful\b", 68),
    ("emotion.gratitude", r"\bgratitude\b", 70),
    ("emotion.gratitude", r"\bthankful\b", 64),
    ("emotion.hope", r"\bhopeful\b", 66),
    ("emotion.shame", r"\bashamed\b", 70),
    ("emotion.shame", r"\bshame\b", 68),
    ("emotion.guilt", r"\bguilty\b", 66),
    ("emotion.guilt", r"\bguilt\b", 64),
    ("emotion.frustration", r"\bfrustrat\w*", 62),
    ("emotion.frustration", r"\bfed up\b", 58),
    ("emotion.loneliness", r"\blonely\b", 64),
    ("emotion.loneliness", r"\bloneliness\b", 68),
    ("emotion.contentment", r"\bcontentment\b", 60),
    ("emotion.calm", r"\bcalm\b", 40),
    ("emotion.calm", r"\bat ease\b", 42),
    ("emotion.calm", r"\bpeaceful\b", 48),
)

_COMPILED = tuple((concept_id, re.compile(pattern, re.IGNORECASE), intensity) for concept_id, pattern, intensity in _PATTERN_ROWS)

BODY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("stomach tightness", re.compile(r"\bstomach\b", re.IGNORECASE)),
    ("tightness", re.compile(r"\btight\b", re.IGNORECASE)),
    ("chest sensation", re.compile(r"\bchest\b", re.IGNORECASE)),
)

OBLIGATION_MARKERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bhave to\b",
        r"\bduty\b",
        r"\bstomach\b",
        r"\btight\b",
        r"\burgent\b",
        r"\bcannot leave it\b",
        r"\brelief\b",
    )
)


def concept_hits(text: str) -> dict[str, float]:
    """Strongest mock intensity per concept. Assistant text must not be passed in."""
    found: dict[str, float] = {}
    for concept_id, pattern, intensity in _COMPILED:
        if pattern.search(text):
            found[concept_id] = max(found.get(concept_id, 0.0), intensity)
    return found


def body_signals(text: str) -> list[str]:
    return [label for label, pattern in BODY_PATTERNS if pattern.search(text)]


def obligation_marker_count(text: str) -> int:
    return sum(1 for pattern in OBLIGATION_MARKERS if pattern.search(text))
