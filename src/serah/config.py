"""Environment configuration. Secrets are read from the environment and never logged."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    data_dir: Path = Field(
        default=Path.home() / ".local" / "share" / "serah",
        validation_alias="SERAH_DATA_DIR",
    )
    db_path: Path | None = Field(default=None, validation_alias="SERAH_DB_PATH")
    curator: str = Field(default="mock", validation_alias="SERAH_CURATOR")
    extractor: str = Field(default="mock", validation_alias="SERAH_EXTRACTOR")
    llm_base_url: str | None = Field(default=None, validation_alias="SERAH_LLM_BASE_URL")
    llm_model: str | None = Field(default=None, validation_alias="SERAH_LLM_MODEL")
    llm_api_key: str | None = Field(default=None, validation_alias="SERAH_LLM_API_KEY")
    llm_api_key_env: str = Field(default="SERAH_LLM_API_KEY", validation_alias="SERAH_LLM_API_KEY_ENV")
    jev_base_url: str = Field(default="https://api.typesafe.ai", validation_alias="JEV_BASE_URL")
    jev_model: str = Field(default="jev-latest", validation_alias="JEV_MODEL")
    laya_device: str | None = Field(default=None, validation_alias="LAYA_DEVICE")
    laya_checkpoint: str | None = Field(default=None, validation_alias="LAYA_CHECKPOINT")
    kai_base_url: str | None = Field(default=None, validation_alias="KAI_BASE_URL")
    kai_api_key: str | None = Field(default=None, validation_alias="KAI_API_KEY")
    kai_model: str = Field(default="Decision-1.0-Kai-0.6B", validation_alias="KAI_MODEL")
    decider_base_url: str | None = Field(default=None, validation_alias="DECIDER_BASE_URL")
    decider_api_key: str | None = Field(default=None, validation_alias="DECIDER_API_KEY")
    decider_model: str | None = Field(default=None, validation_alias="DECIDER_MODEL")
    decay: str = Field(default="exponential", validation_alias="SERAH_DECAY")
    half_life_hours: float = Field(default=72.0, validation_alias="SERAH_HALF_LIFE_HOURS")
    activation_gain: float = Field(default=0.35, validation_alias="SERAH_ACTIVATION_GAIN")
    reservoir_update: str = Field(default="bounded_saturating", validation_alias="SERAH_RESERVOIR_UPDATE")
    scoring_mode: str = Field(default="relevant", validation_alias="SERAH_SCORING_MODE")
    candidate_days: int = Field(default=2, validation_alias="SERAH_CANDIDATE_DAYS")
    active_days: int = Field(default=3, validation_alias="SERAH_ACTIVE_DAYS")
    max_proposals_per_day: int = Field(default=2, validation_alias="SERAH_MAX_PROPOSALS_PER_DAY")

    def resolved_db_path(self) -> Path:
        if self.db_path is not None:
            return Path(self.db_path)
        return Path(self.data_dir) / "serah.sqlite"

    def resolved_llm_key(self) -> str | None:
        if self.llm_api_key:
            return self.llm_api_key
        value = os.environ.get(self.llm_api_key_env, "").strip()
        return value or None


def get_settings() -> Settings:
    """Read settings now. Tests opt out of a local .env via SERAH_IGNORE_DOTENV=1."""
    if os.environ.get("SERAH_IGNORE_DOTENV") == "1":
        return Settings(_env_file=None)
    return Settings(_env_file=".env")
