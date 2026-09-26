"""Keep tests off the operator's real database and any local .env."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERAH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("SERAH_DB_PATH", str(tmp_path / "serah.sqlite"))
    monkeypatch.setenv("SERAH_CURATOR", "mock")
    monkeypatch.setenv("SERAH_EXTRACTOR", "mock")
    for name in (
        "JEV_API_KEY",
        "TYPESAFE_API_KEY",
        "SERAH_LLM_API_KEY",
        "SERAH_LLM_BASE_URL",
        "SERAH_LLM_MODEL",
        "KAI_BASE_URL",
        "KAI_API_KEY",
        "DECIDER_BASE_URL",
        "DECIDER_API_KEY",
        "DECIDER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
