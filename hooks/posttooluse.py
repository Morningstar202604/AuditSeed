"""Client hook entry: PostToolUse event capture.

The client fires this after every matched tool call (Write/Edit/MultiEdit/
Bash) and feeds a JSON event on stdin. We normalize it into a chain event
and append. Hard rules:

- this script NEVER blocks the client: it always exits 0, and any error is
  swallowed (a missed capture shows up as an unlogged change in the
  coverage report — the gap is visible, not hidden)
- it never prints to stdout (hook protocol)
- the repo root is discovered from the changed file path / cwd by walking
  up to the nearest .git
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.normpath(os.path.join(HERE, "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from engine.chainstore import ChainStore  # noqa: E402

FILE_TOOLS = {"Write": "write", "Edit": "modify", "MultiEdit": "modify"}
INTERESTING = set(FILE_TOOLS) | {"Bash"}


def find_repo_root(start: str) -> str | None:
    """Walk up from start to the nearest directory containing .git."""
    p = os.path.normpath(os.path.abspath(start))
    while True:
        if os.path.isdir(os.path.join(p, ".git")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def normalize(event: dict) -> dict | None:
    """Turn a client hook event into a chain event payload, or None when
    the event is not interesting."""
    tool = event.get("tool_name", "")
    if tool not in INTERESTING:
        return None
    tool_input = event.get("tool_input") or {}
    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))[:500]
        if not cmd.strip():
            return None
        return {"type": "cmd", "payload": {"command": cmd, "tool": tool}}
    path = str(tool_input.get("file_path", "") or tool_input.get("notebook_path", ""))
    if not path:
        return None
    return {
        "type": "file_change",
        "payload": {"path": path, "op": FILE_TOOLS.get(tool, "modify"), "tool": tool},
    }


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    try:
        payload = normalize(event)
        if payload is None:
            return 0
        if payload["type"] == "file_change":
            cwd = event.get("cwd") or os.getcwd()
            base = find_repo_root(cwd) or find_repo_root(payload["payload"]["path"])
            if base:
                payload["payload"]["path"] = (
                    os.path.relpath(payload["payload"]["path"], base).replace("\\", "/")
                )
        else:
            base = find_repo_root(event.get("cwd") or os.getcwd())
        if not base:
            return 0
        store = ChainStore(base)
        store.record_event(payload["type"], payload["payload"])
    except Exception:
        # never break the client's tool flow because auditing hiccuped
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
