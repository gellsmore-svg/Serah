"""Stable and random identifiers."""

from __future__ import annotations

import uuid

SERAH_NS = uuid.UUID("8c1a0c4e-5b2a-5d3e-9f10-0a0b0c0d0e0f")


def new_id() -> str:
    return str(uuid.uuid4())


def stable_id(*parts: str) -> str:
    return str(uuid.uuid5(SERAH_NS, "|".join(parts)))
