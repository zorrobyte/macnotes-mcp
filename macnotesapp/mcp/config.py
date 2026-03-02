"""Configuration for macnotesapp MCP daemon/server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import toml
from xdg_base_dirs import xdg_config_home


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class MCPSettings:
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    mount_path: str = "/"
    bootstrap_sync: bool = True
    poll_interval_seconds: int = 120
    cache_db_path: str | None = None
    log_level: str = "INFO"
    log_dir: str | None = None
    lock_path: str | None = None


def default_config_path() -> Path:
    return xdg_config_home() / "macnotes-mcp" / "service.toml"


def load_settings() -> MCPSettings:
    cfg = _load_file_config(default_config_path())
    transport = os.getenv("MACNOTES_MCP_TRANSPORT", cfg.get("transport", "stdio"))
    host = os.getenv("MACNOTES_MCP_HOST", cfg.get("host", "127.0.0.1"))
    port = _int(os.getenv("MACNOTES_MCP_PORT", cfg.get("port", 8000)), 8000)
    mount_path = os.getenv("MACNOTES_MCP_MOUNT_PATH", cfg.get("mount_path", "/"))
    bootstrap_sync = _bool(
        os.getenv("MACNOTES_MCP_BOOTSTRAP_SYNC", cfg.get("bootstrap_sync", True)), True
    )
    poll_interval_seconds = _int(
        os.getenv(
            "MACNOTES_MCP_POLL_INTERVAL_SECONDS",
            cfg.get("poll_interval_seconds", 120),
        ),
        120,
    )
    cache_db_path = os.getenv("MACNOTES_MCP_CACHE_DB_PATH", cfg.get("cache_db_path"))
    log_level = str(os.getenv("MACNOTES_MCP_LOG_LEVEL", cfg.get("log_level", "INFO"))).upper()
    log_dir = os.getenv("MACNOTES_MCP_LOG_DIR", cfg.get("log_dir"))
    lock_path = os.getenv("MACNOTES_MCP_LOCK_PATH", cfg.get("lock_path"))
    return MCPSettings(
        transport=transport,
        host=host,
        port=port,
        mount_path=mount_path,
        bootstrap_sync=bootstrap_sync,
        poll_interval_seconds=poll_interval_seconds,
        cache_db_path=cache_db_path,
        log_level=log_level,
        log_dir=log_dir,
        lock_path=lock_path,
    )


def _load_file_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = toml.load(path)
    except Exception:
        return {}
    service = data.get("service", {})
    return service if isinstance(service, dict) else {}
