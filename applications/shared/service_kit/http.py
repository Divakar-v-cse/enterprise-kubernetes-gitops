"""Resilient HTTP client for service-to-service calls.

Adds per-attempt timeouts, bounded retries on transient failures, a per-host
circuit breaker and Prometheus counters so upstream flakiness is observable.
"""

from __future__ import annotations

import asyncio
import random
import time

import httpx
from prometheus_client import Counter, Histogram

from .logging import get_logger

logger = get_logger("service.http")

UPSTREAM_REQUESTS = Counter(
    "upstream_requests_total", "Calls to upstream services", ["target", "outcome"]
)
UPSTREAM_LATENCY = Histogram(
    "upstream_request_duration_seconds",
    "Latency of upstream calls",
    ["target"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class UpstreamError(RuntimeError):
    def __init__(self, target: str, message: str, status_code: int | None = None):
        super().__init__(f"{target}: {message}")
        self.target = target
        self.status_code = status_code


class CircuitOpenError(UpstreamError):
    def __init__(self, target: str) -> None:
        super().__init__(target, "circuit breaker open")


class ServiceClient:
    """Small wrapper around httpx.AsyncClient with retries + circuit breaker."""

    def __init__(
        self,
        target: str,
        base_url: str,
        *,
        timeout: float = 2.5,
        retries: int = 2,
        breaker_threshold: int = 5,
        breaker_reset_seconds: float = 15.0,
        token: str | None = None,
    ) -> None:
        self.target = target
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(retries, 0)
        self.breaker_threshold = breaker_threshold
        self.breaker_reset_seconds = breaker_reset_seconds
        self._failures = 0
        self._opened_at = 0.0
        self._client: httpx.AsyncClient | None = None
        self._token = token

    async def start(self) -> None:
        headers = {"user-agent": f"{self.target}-client/1.0"}
        if self._token:
            headers["x-internal-token"] = self._token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers=headers,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _breaker_open(self) -> bool:
        if self._failures < self.breaker_threshold:
            return False
        if time.monotonic() - self._opened_at > self.breaker_reset_seconds:
            logger.info("circuit_half_open", extra={"target": self.target})
            self._failures = self.breaker_threshold - 1
            return False
        return True

    def _record(self, ok: bool) -> None:
        if ok:
            self._failures = 0
        else:
            self._failures += 1
            if self._failures == self.breaker_threshold:
                self._opened_at = time.monotonic()
                logger.warning("circuit_opened", extra={"target": self.target})

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._client is None:
            await self.start()
        assert self._client is not None
        if self._breaker_open():
            UPSTREAM_REQUESTS.labels(self.target, "circuit_open").inc()
            raise CircuitOpenError(self.target)

        attempts = self.retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                response = await self._client.request(method, path, **kwargs)
                UPSTREAM_LATENCY.labels(self.target).observe(time.perf_counter() - started)
                if response.status_code in RETRYABLE_STATUS and attempt < attempts:
                    UPSTREAM_REQUESTS.labels(self.target, "retry").inc()
                    await asyncio.sleep(min(0.15 * 2 ** (attempt - 1) + random.random() * 0.05, 1.0))
                    continue
                ok = response.status_code < 500
                self._record(ok)
                UPSTREAM_REQUESTS.labels(
                    self.target, "success" if response.status_code < 400 else f"http_{response.status_code}"
                ).inc()
                return response
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                UPSTREAM_LATENCY.labels(self.target).observe(time.perf_counter() - started)
                UPSTREAM_REQUESTS.labels(self.target, "transport_error").inc()
                if attempt < attempts:
                    await asyncio.sleep(min(0.15 * 2 ** (attempt - 1) + random.random() * 0.05, 1.0))
                    continue
        self._record(False)
        raise UpstreamError(self.target, f"request failed: {last_error}")

    async def get_json(self, path: str, **kwargs) -> dict:
        response = await self.request("GET", path, **kwargs)
        if response.status_code >= 400:
            raise UpstreamError(self.target, response.text[:200], response.status_code)
        return response.json()

    async def post_json(self, path: str, payload: dict, **kwargs) -> dict:
        response = await self.request("POST", path, json=payload, **kwargs)
        if response.status_code >= 400:
            raise UpstreamError(self.target, response.text[:200], response.status_code)
        return response.json()
