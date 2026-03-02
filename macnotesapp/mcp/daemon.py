"""Long-running daemon entrypoint for macnotesapp MCP server."""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
from pathlib import Path

from xdg_base_dirs import xdg_data_home

from macnotesapp import NotesApp

from .config import load_settings
from .server import create_server


def _configure_logging(log_dir: str | None, log_level: str) -> None:
    base_dir = Path(log_dir) if log_dir else (Path.home() / "Library" / "Logs" / "macnotes-mcp")
    base_dir.mkdir(parents=True, exist_ok=True)
    log_file = base_dir / "service.log"
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ]
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
    )


def _acquire_lock(lock_path: str | None):
    path = Path(lock_path) if lock_path else (xdg_data_home() / "macnotes-mcp" / "service.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode("utf-8"))
    return fd


def _validate_notes_access() -> None:
    # Force an automation call so startup fails fast with a clear error if TCC blocks access.
    app = NotesApp()
    _ = app.version
    _ = app.accounts


def main() -> None:
    parser = argparse.ArgumentParser(description="Run macnotes-mcp as a long-running daemon.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        help="Override configured transport.",
    )
    parser.add_argument("--host", help="Override configured host.")
    parser.add_argument("--port", type=int, help="Override configured port.")
    args = parser.parse_args()

    settings = load_settings()
    if args.transport:
        settings.transport = args.transport
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port

    _configure_logging(settings.log_dir, settings.log_level)
    log = logging.getLogger("macnotes_mcp.daemon")
    log.info("starting service transport=%s host=%s port=%s", settings.transport, settings.host, settings.port)

    try:
        lock_fd = _acquire_lock(settings.lock_path)
    except BlockingIOError as exc:
        raise SystemExit("another macnotes-mcp service instance is already running") from exc

    try:
        _validate_notes_access()
    except Exception as exc:
        raise SystemExit(
            "failed to access Apple Notes. Grant automation permission and retry."
        ) from exc

    mcp, _ = create_server(settings)
    try:
        mcp.run(transport=settings.transport, mount_path=settings.mount_path)
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    main()
