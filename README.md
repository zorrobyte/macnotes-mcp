# macnotes-mcp

`macnotes-mcp` is a fork of [RhetTbull/macnotesapp](https://github.com/RhetTbull/macnotesapp) focused on running Apple Notes as a production-ready MCP server.

It provides:
- Async, cache-backed reads
- Background queued writes to Apple Notes
- macOS LaunchAgent service support
- Easy integration with `mcporter` and OpenClaw

## Fork Attribution

This project is forked from:
- Upstream: `RhetTbull/macnotesapp`
- Upstream repo: <https://github.com/RhetTbull/macnotesapp>

The original Python/CLI Notes automation remains available, and this fork adds MCP-first architecture and service tooling.

## Requirements

- macOS (Apple Notes automation is macOS-only)
- Python 3.10-3.13
- `uv` (recommended) for env/dependency management
- Apple Notes.app installed and accessible

Optional:
- `mcporter` for MCP client setup and testing
- OpenClaw if you want agent integration

## Quick Start

Clone and install:

```bash
git clone https://github.com/zorrobyte/macnotes-mcp.git
cd macnotes-mcp
uv sync
```

Run MCP over stdio:

```bash
uv run notes-mcp
```

Run MCP over local HTTP (streamable-http):

```bash
MACNOTES_MCP_TRANSPORT=streamable-http MACNOTES_MCP_HOST=127.0.0.1 MACNOTES_MCP_PORT=8765 uv run notes-mcp-daemon
```

## Run as a macOS Background Service

Install as LaunchAgent:

```bash
./scripts/install_service.sh
```

Uninstall:

```bash
./scripts/uninstall_service.sh
```

Service details:
- Label: `com.zorrobyte.macnotes-mcp`
- Default endpoint: `http://127.0.0.1:8765/mcp`
- Logs: `~/Library/Logs/macnotes-mcp/`

Check service:

```bash
launchctl print "gui/${UID}/com.zorrobyte.macnotes-mcp"
```

Tail logs:

```bash
tail -f ~/Library/Logs/macnotes-mcp/launchd.stderr.log
tail -f ~/Library/Logs/macnotes-mcp/service.log
```

## MCP Client Setup

### mcporter + OpenClaw helper

Use the helper script:

```bash
./scripts/setup_mcporter.sh
```

This does two things:
- Registers MCP server `macnotes-mcp` in `~/.mcporter/mcporter.json`
- Disables OpenClaw bundled `apple-notes` skill to avoid overlap

Custom server name/url:

```bash
./scripts/setup_mcporter.sh my-notes http://127.0.0.1:8765/mcp
```

### Manual mcporter setup

```bash
mcporter config add macnotes-mcp --url http://127.0.0.1:8765/mcp --transport http --scope home
mcporter call macnotes-mcp.notes_health --json
```

## MCP Tools

The server exposes:

- `notes_health`
- `notes_accounts`
- `notes_sync_full`
- `notes_sync_incremental`
- `notes_sync_status`
- `notes_queue_status`
- `notes_job_status`
- `notes_job_wait`
- `notes_list`
- `notes_read`
- `notes_create`
- `notes_update`
- `notes_delete`
- `notes_move`

## Configuration

Config source priority:
1. Environment variables
2. `~/.config/macnotes-mcp/service.toml`
3. Built-in defaults

Example config template:
- `deploy/config/service.example.toml`

Main environment variables:
- `MACNOTES_MCP_TRANSPORT` = `stdio` | `sse` | `streamable-http`
- `MACNOTES_MCP_HOST` (default `127.0.0.1`)
- `MACNOTES_MCP_PORT` (default `8000`)
- `MACNOTES_MCP_MOUNT_PATH` (default `/`)
- `MACNOTES_MCP_BOOTSTRAP_SYNC` (default `true`)
- `MACNOTES_MCP_POLL_INTERVAL_SECONDS` (default `120`)
- `MACNOTES_MCP_CACHE_DB_PATH` (optional override)
- `MACNOTES_MCP_LOG_LEVEL` (default `INFO`)
- `MACNOTES_MCP_LOG_DIR` (optional override)
- `MACNOTES_MCP_LOCK_PATH` (optional override)

## Architecture Summary

- Source of truth: Apple Notes via ScriptingBridge/Apple Events
- Cache: local SQLite for fast reads and search
- Writes: queued background jobs for non-blocking behavior
- Sync: bootstrap full sync + periodic refresh loop

Important:
- Direct writes to Apple Notes private SQLite (`NoteStore.sqlite`) are not used.
- This avoids corruption/sync issues from private schema assumptions.

## Permissions and macOS Notes Automation

On first run, macOS may prompt for Automation permissions (Terminal/Python controlling Notes).

If calls fail:
- Open System Settings -> Privacy & Security -> Automation
- Ensure your invoking app/runtime is allowed to control Notes
- Re-run service or command

## Troubleshooting

Health check:

```bash
mcporter call macnotes-mcp.notes_health --json
```

If endpoint is unreachable:
- Verify service is running with `launchctl print ...`
- Confirm listener port `8765` is open
- Check `launchd.stderr.log` and `service.log`

If sync is slow on first run:
- Large Apple Notes libraries can take time for initial bootstrap
- Use `notes_sync_status` to track cache size and sync state

If OpenClaw still uses old notes skill:

```bash
openclaw config set skills.entries.apple-notes.enabled false
```

## Legacy CLI (from upstream)

This fork still includes upstream CLI entrypoints:
- `notes`
- `macnotesapp` Python API modules

The main focus of this fork is MCP service usage.

## Development

Install dev environment:

```bash
uv sync
```

Run tests:

```bash
uv run pytest -v -s tests/
```

Run daemon locally:

```bash
uv run notes-mcp-daemon --transport streamable-http --host 127.0.0.1 --port 8765
```

## License

MIT (same as upstream).
