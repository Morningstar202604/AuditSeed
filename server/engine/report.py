"""Changeset / compliance report generation.

Pure: every function returns a string. Nothing here writes files — the CLI
prints, the user (or CI) captures. "stdout-first tooling" keeps the
write-surface of the whole plugin limited to the chain itself.
"""
from __future__ import annotations

import json

from .chainstore import ChainStore
from .reconcile import reconcile

_OUTCOMES = {
    "merged": "merged (kept)",
    "reverted": "reverted (rolled back)",
    "partial": "partially applied",
    "abandoned": "abandoned",
}


def _task_entries(store: ChainStore, task_id: str) -> list:
    entries = store.entries_for_task(task_id)
    if not entries:
        raise ValueError(f"no chain entries for task {task_id!r}")
    return entries


def export_json(store: ChainStore, task_id: str) -> str:
    """Machine-readable report (satisfies CI gate consumers)."""
    entries = _task_entries(store, task_id)
    verification = store.verify()
    events = []
    for e in entries:
        events.append(
            {
                "seq": e.get("seq"),
                "ts": e.get("ts"),
                "type": e.get("type"),
                "payload": e.get("payload"),
            }
        )
    files = [
        {"path": p.get("path"), "op": p.get("op"), "tool": p.get("tool")}
        for p in (e.get("payload") for e in entries if e.get("type") == "file_change")
    ]
    closes = [e for e in entries if e.get("type") == "task_close"]
    report = {
        "schema": "auditseed.report/1",
        "task": task_id,
        "repo_fingerprint": store.repo_id,
        "engine": "auditseed/0.0.1",
        "declaration": next(
            (
                e.get("payload", {}).get("reason")
                for e in entries
                if e.get("type") == "task_open"
            ),
            None,
        ),
        "outcome": closes[-1].get("payload", {}).get("outcome") if closes else None,
        "summary": closes[-1].get("payload", {}).get("summary", "") if closes else "",
        "files": files,
        "events": events,
        "integrity": {
            "chain_verified": verification["ok"],
            "chain_entries": verification["entries"],
            "chain_head": verification["head"],
            "debris": verification["debris"],
        },
        "coverage": _coverage(store, entries),
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


def _coverage(store: ChainStore, entries: list) -> dict:
    try:
        rec = reconcile(store.repo_path, entries)
    except Exception as exc:  # noqa: BLE001 — report must not crash on git oddities
        return {"git": f"error: {exc}"}
    return {
        "git": rec["git"],
        "changed": len(rec["changed"]),
        "covered": len(rec["covered"]),
        "unlogged": rec["unlogged"],
        "phantom": rec["phantom"],
        "coverage_percent": rec["coverage"],
    }


def export_markdown(store: ChainStore, task_id: str) -> str:
    """Human/auditor-readable changeset report."""
    entries = _task_entries(store, task_id)
    verification = store.verify()
    opens = [e for e in entries if e.get("type") == "task_open"]
    closes = [e for e in entries if e.get("type") == "task_close"]
    files = [e for e in entries if e.get("type") == "file_change"]
    cmds = [e for e in entries if e.get("type") == "cmd"]
    notes = [e for e in entries if e.get("type") == "note"]
    verifs = [e for e in entries if e.get("type") == "verify"]

    out = []
    out.append(f"# AuditSeed changeset report — task `{task_id}`")
    out.append("")
    out.append(f"- repo fingerprint: `{store.repo_id}`")
    out.append(f"- entries in task: {len(entries)}")
    if opens:
        out.append(f"- opened at: {opens[0].get('ts')}")
        out.append(f"- reason (agent declaration): {opens[0].get('payload', {}).get('reason')}")
    out.append(
        "- outcome: "
        + (
            _OUTCOMES.get(
                closes[-1].get("payload", {}).get("outcome", ""),
                closes[-1].get("payload", {}).get("outcome", "*(open)*"),
            )
            if closes
            else "*(task not closed)*"
        )
    )
    out.append("")
    out.append("## Integrity")
    out.append("")
    out.append(
        f"- chain verified: {'YES' if verification['ok'] else 'NO'} "
        f"({verification['entries']} entries)"
    )
    out.append(f"- chain head: `{verification['head']}`")
    if verification["debris"]:
        out.append(f"- debris lines (torn writes): {len(verification['debris'])}")
    out.append("")
    out.append("## File changes")
    out.append("")
    if files:
        out.append("| time | op | path | tool |")
        out.append("| --- | --- | --- | --- |")
        for e in files:
            p = e.get("payload", {})
            out.append(
                f"| {e.get('ts')} | {p.get('op')} | `{p.get('path')}` | {p.get('tool')} |"
            )
    else:
        out.append("*(no file changes recorded)*")
    out.append("")
    if cmds:
        out.append("## Commands executed")
        out.append("")
        for e in cmds:
            p = e.get("payload", {})
            out.append(f"- `{e.get('ts')}` `{p.get('command')}` (exit {p.get('exit_code')})")
        out.append("")
    if notes:
        out.append("## Notes")
        out.append("")
        for e in notes:
            out.append(f"- `{e.get('ts')}` {e.get('payload', {}).get('text')}")
        out.append("")
    if verifs:
        out.append("## Verification receipts")
        out.append("")
        for e in verifs:
            p = e.get("payload", {})
            out.append(f"- `{e.get('ts')}` {p.get('tool')}: {p.get('result')}")
        out.append("")
    out.append("## Working-tree coverage")
    out.append("")
    cov = _coverage(store, entries)
    if cov.get("git") == "available":
        out.append(
            f"- coverage: {cov.get('coverage_percent')}% "
            f"({cov.get('covered')}/{cov.get('changed')} changed paths with chain events)"
        )
        if cov.get("unlogged"):
            out.append(f"- unlogged changes: {json.dumps(cov['unlogged'], ensure_ascii=False)}")
        if cov.get("phantom"):
            out.append(f"- events without working-tree change: {cov['phantom']}")
    else:
        out.append(f"- git reconciliation: {cov.get('git')}")
    out.append("")
    return "\n".join(out)
