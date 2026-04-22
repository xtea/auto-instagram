"""Global settings and per-account config loading."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Viewport(BaseModel):
    width: int = 1440
    height: int = 900


class ProxySettings(BaseModel):
    server: str
    bypass: str | None = None
    username: str | None = None
    password: str | None = None


class PacingSettings(BaseModel):
    max_posts_per_day: int = 3
    min_step_delay_seconds: float = 30
    max_step_delay_seconds: float = 180
    pre_run_idle_seconds_min: float = 60
    pre_run_idle_seconds_max: float = 180

    @field_validator("max_step_delay_seconds")
    @classmethod
    def _max_gte_min(cls, v: float, info: object) -> float:
        values = getattr(info, "data", {})
        if v < values.get("min_step_delay_seconds", 0):
            raise ValueError("max_step_delay_seconds must be >= min_step_delay_seconds")
        return v


class AccountConfig(BaseModel):
    handle: str
    browser: Literal["patchright", "camoufox"] = "patchright"
    user_agent: str
    viewport: Viewport = Field(default_factory=Viewport)
    locale: str = "en-US"
    timezone: str = "America/Los_Angeles"
    proxy: ProxySettings | None = None
    pacing: PacingSettings = Field(default_factory=PacingSettings)
    headless: bool = False


class Settings(BaseSettings):
    """Process-wide settings, overridable via env or .env."""

    model_config = SettingsConfigDict(
        env_prefix="AUTO_IG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    account: str = "demo"
    sessions_dir: Path = Path("./sessions")
    content_dir: Path = Path("./content")
    config_dir: Path = Path("./config")
    queue_db: Path = Path("./sessions/queue.db")
    log_level: str = "INFO"

    def session_file(self, account: str) -> Path:
        return self.sessions_dir / f"{account}.json"

    def account_config_file(self, account: str) -> Path:
        return self.config_dir / f"{account}.yaml"


def load_account_config(path: Path) -> AccountConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Account config not found: {path}. "
            f"Copy config/account.example.yaml to {path.name} and edit it."
        )
    raw = yaml.safe_load(path.read_text())
    return AccountConfig.model_validate(raw)
