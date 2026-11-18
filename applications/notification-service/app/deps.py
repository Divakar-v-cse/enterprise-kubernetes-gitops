from __future__ import annotations

from fastapi import Header, Request

from service_kit import ApiError


async def require_internal_token(
    request: Request, x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")
) -> None:
    settings = request.app.state.settings
    if x_internal_token != settings.internal_token:
        raise ApiError(401, "unauthorized", "Missing or invalid internal service token")
