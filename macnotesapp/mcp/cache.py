"""Async SQLite cache for Notes metadata and content."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xdg_base_dirs import xdg_data_home


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


class AsyncCacheStore:
    """Async wrapper over sqlite cache."""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = xdg_data_home() / "macnotesapp" / "notes_cache.sqlite3"
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            await self._execute("PRAGMA journal_mode=WAL;")
            await self._execute("PRAGMA synchronous=NORMAL;")
            await self._execute(
                """
                CREATE TABLE IF NOT EXISTS notes_cache (
                    note_id TEXT PRIMARY KEY,
                    account TEXT,
                    folder TEXT,
                    name TEXT,
                    body TEXT,
                    plaintext TEXT,
                    creation_date TEXT,
                    modification_date TEXT,
                    password_protected INTEGER,
                    last_synced_at TEXT
                );
                """
            )
            await self._execute(
                "CREATE INDEX IF NOT EXISTS idx_notes_cache_account ON notes_cache(account);"
            )
            await self._execute(
                "CREATE INDEX IF NOT EXISTS idx_notes_cache_folder ON notes_cache(folder);"
            )
            await self._execute(
                "CREATE INDEX IF NOT EXISTS idx_notes_cache_name ON notes_cache(name);"
            )
            await self._execute(
                """
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

    async def close(self) -> None:
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                await asyncio.to_thread(conn.close)

    async def count_notes(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) FROM notes_cache;")
        return int(row[0]) if row else 0

    async def get_meta(self, key: str) -> str | None:
        row = await self._fetchone("SELECT value FROM sync_state WHERE key = ?;", (key,))
        return row[0] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await self._execute(
            """
            INSERT INTO sync_state(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """,
            (key, value),
        )

    async def upsert_note(self, note: dict[str, Any]) -> None:
        await self._execute(
            """
            INSERT INTO notes_cache (
                note_id, account, folder, name, body, plaintext,
                creation_date, modification_date, password_protected, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(note_id) DO UPDATE SET
                account = excluded.account,
                folder = excluded.folder,
                name = excluded.name,
                body = excluded.body,
                plaintext = excluded.plaintext,
                creation_date = excluded.creation_date,
                modification_date = excluded.modification_date,
                password_protected = excluded.password_protected,
                last_synced_at = excluded.last_synced_at;
            """,
            (
                note.get("id"),
                note.get("account"),
                note.get("folder"),
                note.get("name"),
                note.get("body"),
                note.get("plaintext"),
                _to_iso(note.get("creation_date")),
                _to_iso(note.get("modification_date")),
                1 if bool(note.get("password_protected")) else 0,
                _utcnow_iso(),
            ),
        )

    async def bulk_upsert_notes(self, notes: list[dict[str, Any]]) -> None:
        for note in notes:
            await self.upsert_note(note)

    async def remove_note(self, note_id: str) -> None:
        await self._execute("DELETE FROM notes_cache WHERE note_id = ?;", (note_id,))

    async def list_notes(
        self, account: str | None = None, text: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if account:
            clauses.append("account = ?")
            args.append(account)
        if text:
            clauses.append("(name LIKE ? OR plaintext LIKE ?)")
            args.extend([f"%{text}%", f"%{text}%"])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._fetchall(
            f"""
            SELECT note_id, account, folder, name, plaintext, modification_date, password_protected
            FROM notes_cache
            {where}
            ORDER BY COALESCE(modification_date, '') DESC, name ASC
            LIMIT ?;
            """,
            tuple(args + [limit]),
        )
        return [
            {
                "id": r[0],
                "account": r[1],
                "folder": r[2],
                "name": r[3],
                "plaintext": r[4],
                "modification_date": r[5],
                "password_protected": bool(r[6]),
            }
            for r in rows
        ]

    async def get_note(
        self, note_id: str | None = None, name: str | None = None, account: str | None = None
    ) -> dict[str, Any] | None:
        if note_id:
            row = await self._fetchone(
                """
                SELECT note_id, account, folder, name, body, plaintext, creation_date,
                       modification_date, password_protected, last_synced_at
                FROM notes_cache
                WHERE note_id = ?;
                """,
                (note_id,),
            )
        elif name:
            clauses = ["name = ?"]
            args: list[Any] = [name]
            if account:
                clauses.append("account = ?")
                args.append(account)
            row = await self._fetchone(
                f"""
                SELECT note_id, account, folder, name, body, plaintext, creation_date,
                       modification_date, password_protected, last_synced_at
                FROM notes_cache
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(modification_date, '') DESC
                LIMIT 1;
                """,
                tuple(args),
            )
        else:
            return None
        if not row:
            return None
        return {
            "id": row[0],
            "account": row[1],
            "folder": row[2],
            "name": row[3],
            "body": row[4],
            "plaintext": row[5],
            "creation_date": row[6],
            "modification_date": row[7],
            "password_protected": bool(row[8]),
            "last_synced_at": row[9],
        }

    async def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self._lock:
            conn = self._require_conn()

            def _op() -> None:
                cur = conn.cursor()
                try:
                    cur.execute(sql, params)
                    conn.commit()
                finally:
                    cur.close()

            await asyncio.to_thread(_op)

    async def _fetchone(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> tuple[Any, ...] | None:
        async with self._lock:
            conn = self._require_conn()

            def _op() -> tuple[Any, ...] | None:
                cur = conn.cursor()
                try:
                    cur.execute(sql, params)
                    return cur.fetchone()
                finally:
                    cur.close()

            return await asyncio.to_thread(_op)

    async def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        async with self._lock:
            conn = self._require_conn()

            def _op() -> list[tuple[Any, ...]]:
                cur = conn.cursor()
                try:
                    cur.execute(sql, params)
                    return cur.fetchall()
                finally:
                    cur.close()

            return await asyncio.to_thread(_op)

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Cache store not initialized. Call setup() first.")
        return self._conn
