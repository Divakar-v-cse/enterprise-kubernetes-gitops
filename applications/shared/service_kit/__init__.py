"""Shared runtime kit for all FastAPI microservices.

Deliberately small and dependency-light so every service image stays slim:
configuration, structured JSON logging, Prometheus metrics, error handling,
health probes and a resilient service-to-service HTTP client.
"""

from .app_factory import build_app
from .config import BaseSettings, env_bool, env_int
from .errors import ApiError, install_error_handlers
from .http import CircuitOpenError, ServiceClient, UpstreamError
from .logging import configure_logging, get_logger
from .metrics import REQUEST_COUNT, REQUEST_LATENCY, install_metrics


def __getattr__(name: str):
    """Keep SQLAlchemy optional: the gateway ships without database drivers."""
    if name == "Database":
        from .db import Database

        return Database
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BaseSettings",
    "env_bool",
    "env_int",
    "configure_logging",
    "get_logger",
    "install_metrics",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "ApiError",
    "install_error_handlers",
    "Database",
    "ServiceClient",
    "CircuitOpenError",
    "UpstreamError",
    "build_app",
]
