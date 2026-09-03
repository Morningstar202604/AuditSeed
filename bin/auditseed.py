#!/usr/bin/env python3
"""AuditSeed CLI — the deterministic side of the audit plugin.

    auditseed begin  --repo PATH --task ID --reason "..."
    auditseed finish --repo PATH --task ID --outcome merged
    auditseed status --repo PATH
    auditseed verify --repo PATH
    auditseed export --repo PATH --task ID [--format md|json]
    auditseed gate   --repo PATH --task ID --min-coverage 100

Exit codes for `gate`: 0 pass, 1 fail, 2 usage/config error.
Everything prints to stdout; nothing writes outside the chain.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

from engine.chainstore import ChainError, ChainLocked, ChainStore  # noqa: E402
from engine.reconcile import reconcile  # noqa: E402
from engine.report import export_json, export_markdown  # noqa: E402


def _store(args) -> ChainStore:
    return ChainStore(args.repo)


def cmd_begin(args) -> int:
    store = _store(args)
    entry = store.begin_task(args.task, args.reason)
    print(f"audit task '{args.task}' opened (seq {entry['seq']}, head {entry['hash'][:12]}…)")
    print("reason recorded on-chain; captured edits now attribute to this task")
    return 0


def cmd_finish(args) -> int:
    store = _store(args)
    entry = store.finish_task(args.task, args.outcome, args.summary or "")
    print(f"audit task '{args.task}' closed as {args.outcome} (seq {entry['seq']})")
    return 0


def cmd_status(args) -> int:
    store = _store(args)
    entries, _ = store.read_all()
    rec = reconcile(args.repo, entries)
    active = (store.get_active_task() or {}).get("task")
    print(f"repo:        {args.repo}")
    print(f"repo_id:     {store.repo_id}")
    print(f"chain:       {len(entries)} entries, active task: {active or 'none'}")
    print(f"git:         {rec['git']}")
    if rec["git"] == "available":
        print(f"coverage:    {rec['coverage']}% ({len(rec['covered'])}/{len(rec['changed'])} changed paths on-chain)")
        if rec["unlogged"]:
            print("unlogged changes:")
            for p, op in rec["unlogged"].items():
                print(f"  - {op:7s} {p}")
        if rec["phantom"]:
            print(f"phantom events (no working-tree change): {rec['phantom']}")
    return 0


def cmd_verify(args) -> int:
    store = _store(args)
    result = store.verify()
    print(f"entries: {result['entries']}  head: {result['head']}")
    if result["debris"]:
        print(f"debris (torn writes, linkage intact): {result['debris']}")
    if result["ok"]:
        print("chain OK: every entry hashes and links")
        return 0
    print("chain BROKEN:")
    for line, msg in result["problems"]:
        print(f"  - entry #{line}: {msg}")
    return 1


def cmd_export(args) -> int:
    store = _store(args)
    if args.format == "json":
        print(export_json(store, args.task))
    else:
        print(export_markdown(store, args.task))
    return 0


def cmd_gate(args) -> int:
    store = _store(args)
    entries = store.entries_for_task(args.task)
    if not entries:
        print(f"gate: no audit entries for task '{args.task}'")
        return 1
    verification = store.verify()
    if not verification["ok"]:
        print(f"gate: chain integrity FAILED ({len(verification['problems'])} problems)")
        for line, msg in verification["problems"][:5]:
            print(f"  - entry #{line}: {msg}")
        return 1
    closes = [e for e in entries if e.get("type") == "task_close"]
    if not closes:
        print(f"gate: task '{args.task}' is not closed (no task_close event)")
        return 1
    rec = reconcile(args.repo, entries)
    if rec["git"] == "available" and rec["coverage"] < args.min_coverage:
        print(
            f"gate: coverage {rec['coverage']}% < required {args.min_coverage}% "
            f"(unlogged: {json.dumps(rec['unlogged'], ensure_ascii=False)})"
        )
        return 1
    print(
        f"gate: PASS — task '{args.task}' closed as "
        f"{closes[-1]['payload'].get('outcome')}, chain verified, coverage {rec['coverage']}%"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="auditseed", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("begin", help="open an audit task (declaration ceremony)")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--task", required=True)
    sp.add_argument("--reason", required=True, help="why this change is made")

    sp = sub.add_parser("finish", help="close an audit task")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--task", required=True)
    sp.add_argument("--outcome", required=True, choices=["merged", "reverted", "partial", "abandoned"])
    sp.add_argument("--summary", default="")

    sp = sub.add_parser("status", help="coverage / unlogged changes / active task")
    sp.add_argument("--repo", required=True)

    sp = sub.add_parser("verify", help="re-hash the whole chain")
    sp.add_argument("--repo", required=True)

    sp = sub.add_parser("export", help="export a task changeset report")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--task", required=True)
    sp.add_argument("--format", default="md", choices=["md", "json"])

    sp = sub.add_parser("gate", help="CI gate: integrity + closure + coverage")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--task", required=True)
    sp.add_argument("--min-coverage", type=float, default=100.0)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return {
            "begin": cmd_begin,
            "finish": cmd_finish,
            "status": cmd_status,
            "verify": cmd_verify,
            "export": cmd_export,
            "gate": cmd_gate,
        }[args.cmd](args)
    except ChainLocked as exc:
        print(f"error: {exc}")
        return 2
    except ChainError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
