"""Async service layer for notes cache + background Apple Events worker."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from macnotesapp import NotesApp

from .cache import AsyncCacheStore


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class JobState:
    """Tracks queued write operation state."""

    id: str
    op: str
    payload: dict[str, Any]
    status: str = "queued"
    error: str | None = None
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    result: dict[str, Any] | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


class AsyncNotesService:
    """Cache-first async service with a single background Apple Events worker."""

    def __init__(
        self,
        bootstrap_sync: bool = True,
        poll_interval_seconds: int = 120,
        db_path: Path | None = None,
    ):
        self.cache = AsyncCacheStore(db_path=db_path)
        self.bootstrap_sync = bootstrap_sync
        self.poll_interval_seconds = poll_interval_seconds
        self._queue: asyncio.Queue[JobState] = asyncio.Queue()
        self._jobs: dict[str, JobState] = {}
        self._started = False
        self._starting_lock = asyncio.Lock()
        self._worker_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._sync_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._starting_lock:
            if self._started:
                return
            await self.cache.setup()
            self._worker_task = asyncio.create_task(self._worker_loop())
            self._poll_task = asyncio.create_task(self._poll_loop())
            self._started = True
        if self.bootstrap_sync and await self.cache.count_notes() == 0:
            await self.sync_full()

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
        await self.cache.close()
        self._started = False

    async def list_notes(
        self, account: str | None = None, text: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        await self.start()
        return await self.cache.list_notes(account=account, text=text, limit=limit)

    async def read_note(
        self,
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        live: bool = False,
    ) -> dict[str, Any] | None:
        await self.start()
        if not live:
            cached = await self.cache.get_note(note_id=note_id, name=name, account=account)
            if cached is not None:
                return cached
        note = await self._run_blocking(self._read_note_sync, note_id, name, account)
        if note:
            await self.cache.upsert_note(note)
        return note

    async def create_note(
        self,
        name: str,
        body: str,
        account: str | None = None,
        folder: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        job = await self._enqueue("create", {
            "name": name,
            "body": body,
            "account": account,
            "folder": folder,
        })
        if wait:
            await self.wait_for_job(job["job_id"])
        return job

    async def update_note(
        self,
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        new_name: str | None = None,
        new_body: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        job = await self._enqueue("update", {
            "note_id": note_id,
            "name": name,
            "account": account,
            "new_name": new_name,
            "new_body": new_body,
        })
        if wait:
            await self.wait_for_job(job["job_id"])
        return job

    async def delete_note(
        self,
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        job = await self._enqueue("delete", {
            "note_id": note_id,
            "name": name,
            "account": account,
        })
        if wait:
            await self.wait_for_job(job["job_id"])
        return job

    async def move_note(
        self,
        folder: str,
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        job = await self._enqueue("move", {
            "folder": folder,
            "note_id": note_id,
            "name": name,
            "account": account,
        })
        if wait:
            await self.wait_for_job(job["job_id"])
        return job

    async def wait_for_job(self, job_id: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        await self.start()
        job = self._jobs.get(job_id)
        if not job:
            return {"error": f"job not found: {job_id}"}
        try:
            await asyncio.wait_for(job.done.wait(), timeout=timeout_seconds)
        except TimeoutError:
            return self.get_job_status(job_id)
        return self.get_job_status(job_id)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            return {"error": f"job not found: {job_id}"}
        return self._job_to_dict(job)

    def queue_status(self) -> dict[str, Any]:
        queued = sum(1 for j in self._jobs.values() if j.status == "queued")
        running = sum(1 for j in self._jobs.values() if j.status == "running")
        failed = sum(1 for j in self._jobs.values() if j.status == "failed")
        succeeded = sum(1 for j in self._jobs.values() if j.status == "succeeded")
        return {
            "queued": queued,
            "running": running,
            "failed": failed,
            "succeeded": succeeded,
            "queue_depth": self._queue.qsize(),
            "jobs_total": len(self._jobs),
        }

    async def sync_full(self) -> dict[str, Any]:
        await self.start()
        async with self._sync_lock:
            notes = await self._run_blocking(self._fetch_all_notes_sync)
            await self.cache.bulk_upsert_notes(notes)
            now = _utcnow_iso()
            await self.cache.set_meta("last_full_sync_at", now)
            await self.cache.set_meta("last_sync_at", now)
            return {"notes_synced": len(notes), "last_sync_at": now}

    async def sync_incremental(self) -> dict[str, Any]:
        # Notes scripting does not provide an efficient changed-notes cursor.
        return await self.sync_full()

    async def sync_status(self) -> dict[str, Any]:
        await self.start()
        return {
            "cache_path": str(self.cache.db_path),
            "notes_count": await self.cache.count_notes(),
            "last_sync_at": await self.cache.get_meta("last_sync_at"),
            "last_full_sync_at": await self.cache.get_meta("last_full_sync_at"),
            "queue": self.queue_status(),
        }

    async def accounts(self) -> list[str]:
        return await self._run_blocking(lambda: NotesApp().accounts)

    async def _enqueue(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        await self.start()
        job = JobState(id=str(uuid.uuid4()), op=op, payload=payload)
        self._jobs[job.id] = job
        await self._queue.put(job)
        return {"job_id": job.id, "status": job.status, "op": op}

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            job.status = "running"
            job.updated_at = _utcnow_iso()
            try:
                result = await self._run_blocking(self._apply_job_sync, job.op, job.payload)
                cache_updates = result.pop("_cache_updates", [])
                for update in cache_updates:
                    if update["op"] == "upsert":
                        await self.cache.upsert_note(update["note"])
                    elif update["op"] == "remove":
                        await self.cache.remove_note(update["note_id"])
                job.result = result
                job.status = "succeeded"
                job.error = None
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
            finally:
                job.updated_at = _utcnow_iso()
                job.done.set()
                self._queue.task_done()

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval_seconds)
            try:
                await self.sync_incremental()
            except Exception:
                # Poll sync should not crash server.
                continue

    async def _run_blocking(self, func, *args):
        return await asyncio.to_thread(func, *args)

    def _fetch_all_notes_sync(self) -> list[dict[str, Any]]:
        notesapp = NotesApp()
        out: list[dict[str, Any]] = []
        for account in notesapp.accounts:
            noteslist = notesapp.noteslist(accounts=[account])
            for note in noteslist.asdict():
                note["account"] = account
                out.append(note)
        return out

    def _read_note_sync(
        self, note_id: str | None, name: str | None, account: str | None
    ) -> dict[str, Any] | None:
        notesapp = NotesApp()
        notes = notesapp.notes(
            id=[note_id] if note_id else None,
            name=[name] if name else None,
            accounts=[account] if account else None,
        )
        if not notes:
            return None
        return notes[0].asdict()

    def _find_note_sync(self, payload: dict[str, Any]):
        notesapp = NotesApp()
        note_id = payload.get("note_id")
        name = payload.get("name")
        account = payload.get("account")
        notes = notesapp.notes(
            id=[note_id] if note_id else None,
            name=[name] if name else None,
            accounts=[account] if account else None,
        )
        if not notes:
            raise ValueError("note not found")
        return notes[0]

    def _apply_job_sync(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        notesapp = NotesApp()
        if op == "create":
            account_name = payload.get("account")
            account = notesapp.account(account_name) if account_name else notesapp.account()
            note = account.make_note(
                payload["name"],
                payload["body"],
                payload.get("folder"),
            )
            data = note.asdict()
            return {
                "note_id": data["id"],
                "name": data["name"],
                "_cache_updates": [{"op": "upsert", "note": data}],
            }

        if op == "update":
            note = self._find_note_sync(payload)
            if payload.get("new_name"):
                note.name = payload["new_name"]
            if payload.get("new_body") is not None:
                note.body = payload["new_body"]
            data = note.asdict()
            return {
                "note_id": data["id"],
                "name": data["name"],
                "_cache_updates": [{"op": "upsert", "note": data}],
            }

        if op == "delete":
            note = self._find_note_sync(payload)
            note_id = note.id
            note.delete()
            return {
                "note_id": note_id,
                "deleted": True,
                "_cache_updates": [{"op": "remove", "note_id": note_id}],
            }

        if op == "move":
            note = self._find_note_sync(payload)
            note.move(payload["folder"])
            data = note.asdict()
            return {
                "note_id": data["id"],
                "folder": data["folder"],
                "_cache_updates": [{"op": "upsert", "note": data}],
            }

        raise ValueError(f"unsupported op: {op}")

    def _job_to_dict(self, job: JobState) -> dict[str, Any]:
        return {
            "job_id": job.id,
            "op": job.op,
            "status": job.status,
            "error": job.error,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "result": job.result,
        }
