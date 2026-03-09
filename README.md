# r2-thinmcp

Thin MCP server that keeps **persistent r2pipe sessions** and exposes only a small, flexible tool surface.

## Why this exists

Instead of wrapping many high-level reverse engineering operations, this server intentionally stays thin:

- keep one r2 process per session
- send arbitrary commands via `pipe.cmd` / `pipe.cmdj`
- optionally list commands from r2 help output

This avoids repeated startup/analysis overhead from stateless `r2 -e ...` invocations and keeps full r2 flexibility.

## Tools

- `pipe_open(target, flags?, analyze?, analyze_command?)`
  - opens an r2pipe session and returns `session_id`
- `pipe_close(session_id)`
- `pipe_list()`
- `pipe_cmd(session_id, command, max_output_chars?)`
- `pipe_cmdj(session_id, command)`
- `pipe_list_commands(session_id, prefix?, cursor?, page_size?, source_command?)`
  - `source_command` omitted: auto-select from prefix (`af` -> `a?`, no prefix -> `?`)

## Requirements

- Python 3.10+
- `radare2` installed and available in `PATH`
- `uv` (`uvx`) installed

## Install (uv)

### Option A: no local clone (recommended)

```bash
uv tool install --force --from git+https://github.com/n01e0/r2-thinmcp r2-thinmcp
```

Then run:

```bash
r2-thinmcp --readonly
```

### Option B: local development clone

```bash
git clone https://github.com/n01e0/r2-thinmcp.git
cd r2-thinmcp
uv sync
uv run r2-thinmcp --readonly
```

## Claude Code setup (uvx)

Add as stdio MCP server:

```bash
claude mcp add --transport stdio r2-thinmcp -- \
  uvx --from git+https://github.com/n01e0/r2-thinmcp r2-thinmcp --readonly
```

Useful follow-ups:

```bash
claude mcp list
claude mcp get r2-thinmcp
```

## Codex CLI setup (uvx)

### Option A: via CLI

```bash
codex mcp add r2-thinmcp -- \
  uvx --from git+https://github.com/n01e0/r2-thinmcp r2-thinmcp --readonly
```

Check:

```bash
codex mcp list
```

### Option B: via `~/.codex/config.toml`

```toml
[mcp_servers.r2-thinmcp]
command = "uvx"
args = [
  "--from",
  "git+https://github.com/n01e0/r2-thinmcp",
  "r2-thinmcp",
  "--readonly",
]
```

## Agent guidance (explicit)

- If you want machine-friendly output, prefer r2 `*j` commands (e.g. `ij`, `aflj`, `iSj`).
- You can call those commands in **either** way:
  - `pipe_cmd("aflj")` (returns JSON text)
  - `pipe_cmdj("aflj")` (returns parsed JSON object)
- Both are acceptable. Choose whichever is easier for your client/runtime.
- If your client handles only text well, `pipe_cmd` + `*j` is usually simplest.

## Notes

- Session lifecycle is explicit: open -> command(s) -> close.
- `pipe_list_commands` is best-effort and parses r2 help output.
- `--readonly` blocks obvious write/shell command prefixes.

## License

MIT
