"""MCP server exposing cache-backed Apple Notes tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import MCPSettings, load_settings
from .service import AsyncNotesService


def create_server(settings: MCPSettings | None = None) -> tuple[FastMCP, AsyncNotesService]:
    """Create configured MCP instance and bound service."""
    settings = settings or load_settings()
    service = AsyncNotesService(
        bootstrap_sync=settings.bootstrap_sync,
        poll_interval_seconds=settings.poll_interval_seconds,
        db_path=Path(settings.cache_db_path) if settings.cache_db_path else None,
    )
    mcp = FastMCP(
        "macnotes-mcp",
        host=settings.host,
        port=settings.port,
        mount_path=settings.mount_path,
        log_level=settings.log_level,
    )

    @mcp.tool()
    async def notes_health() -> dict[str, Any]:
        """Check server health and Notes connectivity."""
        status = await service.sync_status()
        accounts = await service.accounts()
        return {
            "ok": True,
            "accounts_count": len(accounts),
            "cache_notes_count": status["notes_count"],
            "queue": status["queue"],
        }

    @mcp.tool()
    async def notes_accounts() -> dict[str, Any]:
        """List Notes.app account names."""
        return {"accounts": await service.accounts()}

    @mcp.tool()
    async def notes_sync_full() -> dict[str, Any]:
        """Run a full sync from Notes.app into the local cache."""
        return await service.sync_full()

    @mcp.tool()
    async def notes_sync_incremental() -> dict[str, Any]:
        """Run incremental sync (currently same behavior as full sync)."""
        return await service.sync_incremental()

    @mcp.tool()
    async def notes_sync_status() -> dict[str, Any]:
        """Show cache and queue status."""
        return await service.sync_status()

    @mcp.tool()
    async def notes_queue_status() -> dict[str, Any]:
        """Show write queue status."""
        await service.start()
        return service.queue_status()

    @mcp.tool()
    async def notes_job_status(job_id: str) -> dict[str, Any]:
        """Get status for a queued write job."""
        await service.start()
        return service.get_job_status(job_id)

    @mcp.tool()
    async def notes_job_wait(job_id: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        """Wait for a queued write job to complete."""
        return await service.wait_for_job(job_id, timeout_seconds=timeout_seconds)

    @mcp.tool()
    async def notes_list(
        account: str | None = None,
        text: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """List notes from the local cache."""
        notes = await service.list_notes(account=account, text=text, limit=limit)
        return {"count": len(notes), "notes": notes}

    @mcp.tool()
    async def notes_read(
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        live: bool = False,
    ) -> dict[str, Any]:
        """Read one note by id or title."""
        note = await service.read_note(note_id=note_id, name=name, account=account, live=live)
        if not note:
            return {"found": False}
        return {"found": True, "note": note}

    @mcp.tool()
    async def notes_create(
        name: str,
        body: str,
        account: str | None = None,
        folder: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Create a note (queued background write by default)."""
        return await service.create_note(
            name=name,
            body=body,
            account=account,
            folder=folder,
            wait=wait,
        )

    @mcp.tool()
    async def notes_update(
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        new_name: str | None = None,
        new_body: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Update note title/body (queued background write by default)."""
        return await service.update_note(
            note_id=note_id,
            name=name,
            account=account,
            new_name=new_name,
            new_body=new_body,
            wait=wait,
        )

    @mcp.tool()
    async def notes_delete(
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Delete a note (queued background write by default)."""
        return await service.delete_note(
            note_id=note_id,
            name=name,
            account=account,
            wait=wait,
        )

    @mcp.tool()
    async def notes_move(
        folder: str,
        note_id: str | None = None,
        name: str | None = None,
        account: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Move a note to a different folder (queued background write by default)."""
        return await service.move_note(
            folder=folder,
            note_id=note_id,
            name=name,
            account=account,
            wait=wait,
        )

    return mcp, service


def run() -> None:
    """Run MCP server with configured transport."""
    settings = load_settings()
    mcp, _ = create_server(settings)
    mcp.run(transport=settings.transport, mount_path=settings.mount_path)
