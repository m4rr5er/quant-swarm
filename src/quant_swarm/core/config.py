"""Configuration — secrets from .env, everything else from configs/*.yaml.

Two layers:
- :class:`Settings`   infra/env vars (QS_* prefix, .env): nats url, db path…
- :class:`AppConfig`  yaml-driven business config: watchlist, schedule,
  risk limits, LLM named profiles and per-agent specs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "configs"


class LLMProfile(BaseModel):
    """One named LLM endpoint — any OpenAI-compatible provider or gateway."""

    base_url: str
    api_key_env: str
    model: str
    temperature: float = 0.2
    max_tokens: int | None = None
    timeout_sec: float = 60.0
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMConfig(BaseModel):
    profiles: dict[str, LLMProfile] = Field(default_factory=dict)


class ScheduleSettings(BaseModel):
    market_collect_cron: str = "*/5 9-15 * * 1-5"
    decide_cron: str = "30 14 * * 1-5"
    # Optional second-level intervals; when set they override the crons
    # (handy for dev/demo runs).
    market_collect_interval_sec: int | None = None
    decide_interval_sec: int | None = None


class AccountSettings(BaseModel):
    initial_cash: float = 1_000_000.0


class RiskSettings(BaseModel):
    max_position_weight: float = 0.20
    require_manual_confirm: bool = True


class AgentSpec(BaseModel):
    """Per-agent yaml block — extra keys pass through to ``params`` access."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    provider: str | None = None
    broker: str | None = None
    llm_profile: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    watchlist: list[str] = Field(default_factory=list)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    account: AccountSettings = Field(default_factory=AccountSettings)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agents: dict[str, AgentSpec] = Field(default_factory=dict)

    def agent(self, name: str) -> AgentSpec:
        return self.agents.get(name, AgentSpec())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QS_", env_file=".env", extra="ignore")

    bus: str = "nats"  # nats | nats_js | local
    nats_url: str = "nats://127.0.0.1:4222"
    db_path: str = "data/quantswarm.db"
    memory_dir: str = "memory"  # bounded agent memory files (runtime data)
    log_dir: str = "logs"
    log_level: str = "INFO"
    config_dir: str = str(DEFAULT_CONFIG_DIR)


def load_settings() -> Settings:
    return Settings()


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursive dict merge — ``local.yaml`` overrides leaves, keeps siblings."""
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(config_dir: str | Path | None = None) -> AppConfig:
    """Merge configs/*.yaml into AppConfig.

    ``settings.yaml`` and ``agents.yaml`` ship with the repo;
    ``local.yaml`` (gitignored) overlays them last for machine-local
    values — private endpoints, sandboxed params — and must never hold
    secrets (keys always come from env vars via ``api_key_env``).
    """
    cfg_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    merged: dict[str, Any] = {}
    for name in ("settings.yaml", "agents.yaml", "local.yaml"):
        path = cfg_dir / name
        if path.exists():
            _deep_merge(merged, yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return AppConfig.model_validate(merged)
