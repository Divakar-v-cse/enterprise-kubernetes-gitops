"""Platform API configuration.

All values are environment driven. The token below is a local demo credential
only and must be overridden through a Kubernetes Secret in real deployments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass
class Settings:
    service_name: str = "platform-api"
    version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    api_token: str = field(default_factory=lambda: os.getenv("PLATFORM_API_TOKEN", "platform-demo-token"))
    auth_enabled: bool = field(
        default_factory=lambda: os.getenv("PLATFORM_AUTH_ENABLED", "true").lower() == "true"
    )
    kube_context: str | None = field(default_factory=lambda: os.getenv("KUBE_CONTEXT") or None)
    in_cluster: bool = field(
        default_factory=lambda: os.getenv("IN_CLUSTER", "false").lower() == "true"
    )
    demo_mode: bool = field(
        default_factory=lambda: os.getenv("PLATFORM_DEMO_MODE", "false").lower() == "true"
    )
    cluster_name: str = field(default_factory=lambda: os.getenv("CLUSTER_NAME", "gitops-platform"))
    namespace_filter: list[str] = field(
        default_factory=lambda: _csv("PLATFORM_NAMESPACES", "platform,monitoring,argocd,logging")
    )
    cors_origins: list[str] = field(
        default_factory=lambda: _csv(
            "CORS_ALLOW_ORIGINS",
            "http://localhost:5173,http://localhost:3000,http://localhost:8080,http://localhost:8081",
        )
    )
    prometheus_url: str = field(
        default_factory=lambda: os.getenv(
            "PROMETHEUS_URL", "http://prometheus-server.monitoring.svc.cluster.local:80"
        )
    )
    alertmanager_url: str = field(
        default_factory=lambda: os.getenv(
            "ALERTMANAGER_URL", "http://alertmanager.monitoring.svc.cluster.local:9093"
        )
    )
    loki_url: str = field(
        default_factory=lambda: os.getenv("LOKI_URL", "http://loki.logging.svc.cluster.local:3100")
    )
    argocd_namespace: str = field(default_factory=lambda: os.getenv("ARGOCD_NAMESPACE", "argocd"))
    security_findings_path: str = field(
        default_factory=lambda: os.getenv("SECURITY_FINDINGS_PATH", "/app/security/findings.json")
    )
    cache_ttl_seconds: float = field(
        default_factory=lambda: float(os.getenv("CACHE_TTL_SECONDS", "5"))
    )
    request_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


settings = Settings()
