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
  - `source_command` 未指定時は `prefix` 先頭に応じて自動選択（例: `af` -> `a?` / prefixなし -> `?`）

## Install

```bash
git clone https://github.com/n01e0/r2-thinmcp.git
cd r2-thinmcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Requirements:

- Python 3.10+
- `radare2` installed and available in `PATH`

## Run (stdio)

```bash
r2-thinmcp
```

Readonly mode (recommended when using untrusted prompts):

```bash
r2-thinmcp --readonly
```

## MCP client config example

### Claude Desktop

```json
{
  "mcpServers": {
    "r2-thinmcp": {
      "command": "r2-thinmcp",
      "args": ["--readonly"]
    }
  }
}
```

### VS Code (Copilot MCP)

```json
{
  "servers": {
    "r2-thinmcp": {
      "type": "stdio",
      "command": "r2-thinmcp",
      "args": []
    }
  },
  "inputs": []
}
```

## Notes

- Session lifecycle is explicit: open -> command(s) -> close.
- `pipe_list_commands` is best-effort; it parses output from `source_command` (default: `??`).
- In readonly mode, obvious write/shell commands are blocked by prefix checks.

## License

MIT
