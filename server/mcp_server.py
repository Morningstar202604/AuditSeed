"""AuditSeed MCP server — zero-dependency stdio JSON-RPC 2.0.

Protocol: newline-delimited JSON-RPC over stdin/stdout (Model Context
Protocol stdio transport). Methods:

- initialize                 → capabilities + serverInfo
- notifications/initialized  → (notification, no response)
- tools/list                 → the audit tool family
- tools/call                 → audit_begin / audit_finish / audit_status /
                               audit_verify / audit_export / audit_note

Deliberately NOT exposed as MCP tools: anything that mutates or judges the
chain's trustworthiness on the model's request (no chain editing, no gate
bypass). The model can declare and ask; it cannot alter evidence.
"""
from __future__ import annotations

import json
import sys

from engine.chainstore import ChainError, ChainStore
from engine.report import export_json, export_markdown

SERVER_INFO = {"name": "auditseed", "version": "0.0.1"}
PROTOCOL_VERSION = "2024-11-05"


def _tool_specs() -> list:
    return [
        {
            "name": "audit_begin",
            "description": (
                "Open an audit task BEFORE making changes. Declare the task id "
                "and, most importantly, the reason (the why). Every captured "
                "file change is attributed to this task until audit_finish."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "repository root path"},
                    "task": {"type": "string", "description": "short task id (letters/digits/dot/dash/underscore)"},
                    "reason": {"type": "string", "description": "why this change is being made"},
                    "scope": {"type": "array", "items": {"type": "string"}, "description": "expected paths/dirs (optional)"},
                },
                "required": ["repo", "task", "reason"],
            },
        },
        {
            "name": "audit_finish",
            "description": "Close an audit task with an outcome (merged|reverted|partial|abandoned) and a summary.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "task": {"type": "string"},
                    "outcome": {"type": "string", "enum": ["merged", "reverted", "partial", "abandoned"]},
                    "summary": {"type": "string"},
                },
                "required": ["repo", "task", "outcome"],
            },
        },
        {
            "name": "audit_status",
            "description": "Coverage report: what changed in the working tree, what is on the chain, what was missed.",
            "inputSchema": {
                "type": "object",
                "properties": {"repo": {"type": "string"}},
                "required": ["repo"],
            },
        },
        {
            "name": "audit_verify",
            "description": "Re-hash the whole chain and report integrity (tamper detection).",
            "inputSchema": {
                "type": "object",
                "properties": {"repo": {"type": "string"}},
                "required": ["repo"],
            },
        },
        {
            "name": "audit_export",
            "description": "Export the changeset report for a task (markdown or json). Read-only.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "task": {"type": "string"},
                    "format": {"type": "string", "enum": ["md", "json"]},
                },
                "required": ["repo", "task"],
            },
        },
        {
            "name": "audit_note",
            "description": "Append a structured note to the current task's audit trail.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["repo", "text"],
            },
        },
    ]


def _dispatch(name: str, args: dict) -> str:
    if name == "audit_begin":
        store = ChainStore(args["repo"])
        entry = store.begin_task(args["task"], args["reason"], args.get("scope"))
        return json.dumps(
            {"ok": True, "task": args["task"], "seq": entry["seq"], "hash": entry["hash"]},
            ensure_ascii=False,
        )
    if name == "audit_finish":
        store = ChainStore(args["repo"])
        entry = store.finish_task(args["task"], args["outcome"], args.get("summary", ""))
        return json.dumps(
            {"ok": True, "task": args["task"], "seq": entry["seq"], "hash": entry["hash"]},
            ensure_ascii=False,
        )
    if name == "audit_status":
        store = ChainStore(args["repo"])
        entries, _ = store.read_all()
        from engine.reconcile import reconcile

        rec = reconcile(store.repo_path, entries)
        rec["active_task"] = (store.get_active_task() or {}).get("task")
        rec["chain_entries"] = len(entries)
        return json.dumps(rec, ensure_ascii=False, indent=2)
    if name == "audit_verify":
        store = ChainStore(args["repo"])
        return json.dumps(store.verify(), ensure_ascii=False, indent=2)
    if name == "audit_export":
        store = ChainStore(args["repo"])
        fmt = args.get("format", "md")
        if fmt == "json":
            return export_json(store, args["task"])
        return export_markdown(store, args["task"])
    if name == "audit_note":
        store = ChainStore(args["repo"])
        entry = store.note(args["text"])
        return json.dumps({"ok": True, "seq": entry["seq"]}, ensure_ascii=False)
    raise KeyError(name)


def handle(req: dict) -> dict | None:
    """Handle one JSON-RPC request; returns a response dict or None for
    notifications."""
    method = req.get("method", "")
    msg_id = req.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method.startswith("notifications/"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _tool_specs()}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            text = _dispatch(name, args)
        except KeyError:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        except ChainError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"audit error: {exc}"}],
                    "isError": True,
                },
            }
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"invalid params: {exc}"},
            }
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": text}]}}
    if msg_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {exc}"},
            }
        else:
            resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
