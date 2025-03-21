"""
Connection manager class and get_connection function are defined here.
"""

from __future__ import annotations

from asyncio import Lock
from contextlib import asynccontextmanager
from itertools import cycle
from typing import Any, AsyncIterator

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.utils.config import DBConfig


class PostgresConnectionManager:
    """Connection manager for PostgreSQL database"""

    def __init__(
        self,
        master: DBConfig,
        logger: structlog.stdlib.BoundLogger,
        engine_options: dict[str, Any] | None = None,
        application_name: str | None = None,
    ) -> None:
        """Initialize connection manager entity."""
        self._master_engine: AsyncEngine | None = None
        self._master = master
        self._lock = Lock()
        self._logger = logger
        self._engine_options = engine_options or {}
        self._application_name = application_name

    async def update(
        self,
        master: DBConfig | None = None,
        logger: structlog.stdlib.BoundLogger | None = None,
        application_name: str | None = None,
        engine_options: dict[str, Any] | None = None,
    ) -> None:
        """Initialize connection manager entity."""
        async with self._lock:
            self._master = master or self._master
            self._logger = logger or self._logger
            self._application_name = application_name or self._application_name
            self._engine_options = engine_options or self._engine_options

            if self.initialized:
                await self.refresh()

    @property
    def initialized(self) -> bool:
        return self._master_engine is not None

    async def refresh(self) -> None:
        """(Re-)create connection engine."""
        await self.shutdown()

        await self._logger.ainfo(
            "creating postgres master connection pool",
            max_size=self._master.pool_size,
            user=self._master.user,
            host=self._master.host,
            port=self._master.port,
            database=self._master.database,
        )
        self._master_engine = create_async_engine(
            f"postgresql+asyncpg://{self._master.user}:{self._master.password}@{self._master.host}"
            f":{self._master.port}/{self._master.database}",
            future=True,
            pool_size=max(1, self._master.pool_size - 5),
            max_overflow=5,
            **self._engine_options,
        )
        try:
            async with self._master_engine.connect() as conn:
                cur = await conn.execute(select(1))
                assert cur.fetchone()[0] == 1
        except Exception as exc:
            self._master_engine = None
            raise RuntimeError("something wrong with database connection, aborting") from exc

    async def shutdown(self) -> None:
        """Dispose connection pool and deinitialize."""
        if self.initialized:
            async with self._lock:
                if self.initialized:
                    await self._master_engine.dispose()
                self._master_engine = None

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[AsyncConnection]:
        """Get an async connection to the database with read-write ability."""
        if not self.initialized:
            async with self._lock:
                if not self.initialized:
                    await self.refresh()
        async with self._master_engine.connect() as conn:
            if self._application_name is not None:
                await conn.execute(text(f'SET application_name TO "{self._application_name}"'))
                await conn.commit()
            yield conn
