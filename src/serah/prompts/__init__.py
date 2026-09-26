"""Versioned prompts packaged with Serah."""

from __future__ import annotations

from importlib.resources import files


def load_prompt(*parts: str) -> str:
    resource = files("serah.prompts").joinpath(*parts)
    return resource.read_text(encoding="utf-8")
