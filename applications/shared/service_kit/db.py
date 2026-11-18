"""Async SQLAlchemy database helper with startup retry (container/DB race)."""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .logging import get_logger

logger = get_logger("service.db")


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 5) -> None:
        if not url:
            raise ValueError("DATABASE_URL is required")
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        self.url = url
        self.engine = create_async_engine(
            url,
            echo=echo,
            pool_pre_ping=True,
            connect_args=connect_args,
            **({} if url.startswith("sqlite") else {"pool_size": pool_size, "max_overflow": 5}),
        )
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_models(self, retries: int = 1, delay: float = 2.0) -> None:
        last_error: Exception | None = None
        for attempt in range(1, max(retries, 1) + 1):
            try:
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                logger.info("database_schema_ready", extra={"attempt": attempt})
                return
            except Exception as exc:  # pragma: no cover - exercised in integration
                last_error = exc
                logger.warning(
                    "database_not_ready",
                    extra={"attempt": attempt, "error": str(exc)[:300]},
                )
                if attempt < retries:
                    await asyncio.sleep(delay)
        raise RuntimeError(f"database initialization failed: {last_error}") from last_error

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # pragma: no cover - depends on runtime
            logger.warning("database_ping_failed", extra={"error": str(exc)[:300]})
            return False

    def session(self) -> AsyncSession:
        return self.session_factory()

    async def dispose(self) -> None:
        await self.engine.dispose()
