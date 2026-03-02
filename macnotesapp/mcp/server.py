"""MCP server exposing cache-backed Apple Notes tools."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .service import AsyncNotesService


bootstrap = os.environ.get("MACNOTESAPP_MCP_BOOTSTRAP_SYNC", "1") not in {"0", "false", "False"}
service = AsyncNotesService(bootstrap_sync=bootstrap)
mcp = FastMCP("macnotesapp")


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


def run() -> None:
    """Run MCP server on stdio transport."""
    mcp.run()
