"""Environment-driven configuration shared by every service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class BaseSettings:
    """Common settings. Concrete services extend this with their own fields."""

    service_name: str
    version: str = "1.0.0"
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    internal_token: str = field(
        default_factory=lambda: os.getenv("INTERNAL_API_TOKEN", "dev-internal-token")
    )
    request_timeout_seconds: float = field(
        default_factory=lambda: env_float("REQUEST_TIMEOUT_SECONDS", 2.5)
    )
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    db_max_retries: int = field(default_factory=lambda: env_int("DB_MAX_RETRIES", 30))
    metrics_enabled: bool = field(default_factory=lambda: env_bool("METRICS_ENABLED", True))

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}
