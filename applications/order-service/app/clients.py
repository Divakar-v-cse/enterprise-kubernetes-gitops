"""Downstream service clients used by the order workflow."""

from __future__ import annotations

import os

from service_kit import ServiceClient


def _client(target: str, env_url: str, default: str, timeout: float, token: str) -> ServiceClient:
    return ServiceClient(
        target,
        os.getenv(env_url, default),
        timeout=timeout,
        retries=2,
        breaker_threshold=5,
        breaker_reset_seconds=15.0,
        token=token,
    )


def build_clients(timeout: float, token: str) -> dict[str, ServiceClient]:
    return {
        "users": _client("user-service", "USER_SERVICE_URL", "http://localhost:8001", timeout, token),
        "products": _client(
            "product-service", "PRODUCT_SERVICE_URL", "http://localhost:8002", timeout, token
        ),
        "notifications": _client(
            "notification-service",
            "NOTIFICATION_SERVICE_URL",
            "http://localhost:8004",
            timeout,
            token,
        ),
    }
