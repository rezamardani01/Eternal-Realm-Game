"""SQLite access: one connection, one lock, explicit transactions.

Every piece of game logic runs inside ``async with db.transaction() as tx``. The lock makes
transactions strictly sequential, so two requests can never interleave a read-modify-write on
the same wallet; ``BEGIN IMMEDIATE`` additionally protects against other processes.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from .migrations import apply_migrations

Row = sqlite3.Row


class Tx:
    """Thin wrapper around the connection handed to repositories."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self.rowcount = 0

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        cursor = await self._conn.execute(sql, params)
        self.rowcount = cursor.rowcount
        last = cursor.lastrowid
        await cursor.close()
        return last or 0

    async def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        await self._conn.executemany(sql, rows)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Row | None:
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        cursor = await self._conn.execute(sql, params)
        rows = list(await cursor.fetchall())
        await cursor.close()
        return rows

    async def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        row = await self.fetchone(sql, params)
        return default if row is None or row[0] is None else row[0]


LOCK_TIMEOUT = 30.0


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
        self._conn = conn
        await apply_migrations(conn)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def _acquire(self) -> None:
        """Take the database lock, but never wait forever: a stuck holder becomes a logged error."""
        try:
            await asyncio.wait_for(self._lock.acquire(), LOCK_TIMEOUT)
        except TimeoutError as exc:
            raise RuntimeError("database lock timeout: another task held the database for too long") from exc

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Tx]:
        """Serialised write transaction: commits on success, rolls back on any exception."""
        await self._acquire()
        try:
            conn = self.conn
            await conn.execute("BEGIN IMMEDIATE")
            try:
                yield Tx(conn)
            except BaseException:
                await conn.execute("ROLLBACK")
                raise
            else:
                await conn.execute("COMMIT")
        finally:
            self._lock.release()

    @asynccontextmanager
    async def read(self) -> AsyncIterator[Tx]:
        """Read-only access that still waits for any running write transaction."""
        await self._acquire()
        try:
            yield Tx(self.conn)
        finally:
            self._lock.release()

    async def backup(self, destination: str | Path) -> Path:
        """Consistent online copy of the database (safe while the bot is running)."""
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            await self.conn.execute("VACUUM INTO ?", (str(target),))
        return target
