from __future__ import annotations

import argparse
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import r2pipe
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("r2-thinmcp")


@dataclass
class PipeSession:
    session_id: str
    target: str
    flags: list[str]
    opened_at: float
    pipe: Any = field(repr=False)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


class SessionStore:
    def __init__(self, readonly: bool = False):
        self._readonly = readonly
        self._sessions: dict[str, PipeSession] = {}
        self._lock = threading.RLock()

    @property
    def readonly(self) -> bool:
        return self._readonly

    def open(self, target: str, flags: list[str] | None = None) -> PipeSession:
        clean_flags = [f.strip() for f in (flags or []) if f and f.strip()]
        if self._readonly and "-r" not in clean_flags:
            clean_flags.append("-r")

        pipe = r2pipe.open(target, flags=clean_flags)
        session = PipeSession(
            session_id=str(uuid.uuid4()),
            target=target,
            flags=clean_flags,
            opened_at=time.time(),
            pipe=pipe,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> PipeSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Unknown session_id: {session_id}")
        return session

    def close(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if not session:
            raise ValueError(f"Unknown session_id: {session_id}")
        with session.lock:
            try:
                session.pipe.quit()
            except Exception:
                pass

    def list(self) -> list[PipeSession]:
        with self._lock:
            return list(self._sessions.values())


STORE = SessionStore(readonly=False)
DEFAULT_MAX_OUTPUT_CHARS = 200_000
ANSI_COLOR_RE = re.compile(r"\x1b\[[0-9;]*m")


def _is_dangerous_command(command: str) -> bool:
    cmd = command.strip()
    if not cmd:
        return False

    blocked_prefixes = (
        "!",     # shell escape
        "#!",    # shebang script
        "w",     # write commands family
        "wt",    # write to file
        "wp",    # patch
        "wf",    # write file
        "o+",    # reopen write mode
        "oo+",   # reopen rw
        "rm ",   # shell-like removal via wrappers
    )
    return any(cmd.startswith(prefix) for prefix in blocked_prefixes)


def _trim_output(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return text, False
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _normalize_cursor(cursor: int) -> int:
    return cursor if cursor >= 0 else 0


def _extract_command_token(help_line: str) -> str | None:
    cleaned = ANSI_COLOR_RE.sub("", help_line).strip()
    if cleaned.startswith("|"):
        cleaned = cleaned[1:].strip()
    if not cleaned:
        return None
    if cleaned.startswith(("Usage", "Append", "Prefix", "Environment:", "Examples:")):
        return None

    token = cleaned.split()[0]
    if token in {"|", ":", "-"}:
        return None

    for sep in ("[", "(", "<"):
        token = token.split(sep, 1)[0]

    if "=" in token and not token.startswith(("==", "!=", ">=", "<=")):
        token = token.split("=", 1)[0]

    token = token.rstrip(":;,")
    if token.startswith("%"):
        token = "%"

    return token or None


@mcp.tool()
def pipe_open(
    target: str,
    flags: list[str] | None = None,
    analyze: bool = False,
    analyze_command: str = "aaa",
) -> dict[str, Any]:
    """Open a persistent r2pipe session and return its session id."""
    session = STORE.open(target=target, flags=flags)

    if analyze:
        with session.lock:
            session.pipe.cmd(analyze_command)

    return {
        "session_id": session.session_id,
        "target": session.target,
        "flags": session.flags,
        "readonly": STORE.readonly,
        "opened_at": session.opened_at,
    }


@mcp.tool()
def pipe_close(session_id: str) -> dict[str, bool]:
    """Close an existing r2pipe session."""
    STORE.close(session_id)
    return {"ok": True}


@mcp.tool()
def pipe_list() -> list[dict[str, Any]]:
    """List all active r2pipe sessions."""
    items = []
    now = time.time()
    for session in STORE.list():
        items.append(
            {
                "session_id": session.session_id,
                "target": session.target,
                "flags": session.flags,
                "age_sec": round(now - session.opened_at, 3),
            }
        )
    return items


@mcp.tool()
def pipe_cmd(session_id: str, command: str, max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> dict[str, Any]:
    """Run pipe.cmd(command) on an existing session."""
    if STORE.readonly and _is_dangerous_command(command):
        raise ValueError("Command blocked in readonly mode")

    session = STORE.get(session_id)
    with session.lock:
        output = session.pipe.cmd(command)

    trimmed, truncated = _trim_output(output, max_output_chars)
    return {
        "output": trimmed,
        "truncated": truncated,
        "output_chars": len(trimmed),
    }


@mcp.tool()
def pipe_cmdj(session_id: str, command: str) -> dict[str, Any]:
    """Run pipe.cmdj(command) on an existing session."""
    if STORE.readonly and _is_dangerous_command(command):
        raise ValueError("Command blocked in readonly mode")

    session = STORE.get(session_id)
    with session.lock:
        result = session.pipe.cmdj(command)
    return {"result": result}


@mcp.tool()
def pipe_list_commands(
    session_id: str,
    prefix: str = "",
    cursor: int = 0,
    page_size: int = 200,
    source_command: str | None = None,
) -> dict[str, Any]:
    """Return command names discovered from r2 help output with pagination."""
    if page_size <= 0:
        page_size = 200
    if page_size > 5_000:
        page_size = 5_000

    selected_source_command = source_command or (f"{prefix[0]}?" if prefix else "?")

    session = STORE.get(session_id)
    with session.lock:
        raw = session.pipe.cmd(selected_source_command)

        if not raw.strip() and selected_source_command != "?":
            selected_source_command = "?"
            raw = session.pipe.cmd(selected_source_command)

    commands: set[str] = set()
    for line in raw.splitlines():
        cmd = _extract_command_token(line)
        if cmd:
            commands.add(cmd)

    ordered = sorted(commands)
    if prefix:
        ordered = [c for c in ordered if c.startswith(prefix)]

    start = _normalize_cursor(cursor)
    end = start + page_size
    items = ordered[start:end]
    next_cursor = end if end < len(ordered) else None

    return {
        "items": items,
        "total": len(ordered),
        "cursor": start,
        "next_cursor": next_cursor,
        "page_size": page_size,
        "source_command": selected_source_command,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Thin MCP wrapper around persistent r2pipe sessions")
    parser.add_argument(
        "--readonly",
        action="store_true",
        help="Open sessions in readonly mode and block dangerous write/shell commands",
    )
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=200_000,
        help="Default max output length for pipe_cmd",
    )
    return parser


def main() -> None:
    global STORE
    global DEFAULT_MAX_OUTPUT_CHARS

    args = _build_arg_parser().parse_args()
    STORE = SessionStore(readonly=args.readonly)
    DEFAULT_MAX_OUTPUT_CHARS = args.max_output_chars
    mcp.run()


if __name__ == "__main__":
    main()
