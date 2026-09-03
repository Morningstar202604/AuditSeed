"""Git ground-truth reconciliation.

The chain records what the agent *declared* and what hooks *observed*.
The working tree is the ground truth. This module answers the only
question that matters for honest coverage reporting:

    which files changed, and do we have chain events for them?

Works on any repo; when git is unavailable or the directory is not a
repository, it says so instead of pretending.
"""
from __future__ import annotations

import os
import subprocess

from .canon import canon_bytes, sha256_hex


def _git(repo_path: str, *args: str) -> tuple[int, str, str]:
    """Run git in the repo; returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def is_git_repo(repo_path: str) -> bool:
    code, out, _ = _git(repo_path, "rev-parse", "--is-inside-work-tree")
    return code == 0 and out.strip() == "true"


def _changed_paths(repo_path: str) -> dict[str, str]:
    """Working-tree changes as {relative_path: op}, ops: add|modify|delete.

    Uses porcelain v1 status; only tracked-and-changed plus untracked files
    are relevant for coverage (staged-but-identical changes are included
    because staged rows also appear in porcelain output).
    """
    code, out, err = _git(repo_path, "status", "--porcelain=v1", "-z")
    if code != 0:
        raise RuntimeError(err.strip() or "git status failed")
    changes: dict[str, str] = {}
    tokens = out.split("\0")
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if len(tok) < 3:
            i += 1
            continue
        xy, path = tok[:2], tok[3:]
        if path:
            if xy.startswith("??"):
                op = "add"
            elif "D" in xy:
                op = "delete"
            else:
                op = "modify"
            changes[path.replace("\\", "/")] = op
        i += 1
    return changes


def _recorded_paths(entries: list) -> set[str]:
    """Chain-observed paths from file_change events."""
    seen = set()
    for e in entries:
        if e.get("type") == "file_change":
            p = (e.get("payload") or {}).get("path")
            if p:
                seen.add(str(p).replace("\\", "/"))
    return seen


def reconcile(repo_path: str, entries: list) -> dict:
    """Compare working tree against chain events.

    Returns {
      git: available|unavailable|not_a_repo,
      changed: {path: op},
      covered: [path],
      unlogged: {path: op},      # changed but no chain event
      phantom: [path],           # chain event for a file that did not change
      coverage: float,           # 0..100, 100 when nothing changed
      repo_id: str,
    }
    """
    from .canon import repo_fingerprint

    result = {
        "git": "available",
        "changed": {},
        "covered": [],
        "unlogged": {},
        "phantom": [],
        "coverage": 100.0,
        "repo_id": repo_fingerprint(repo_path),
    }
    if not is_git_repo(repo_path):
        result["git"] = "not_a_repo"
        return result
    try:
        changed = _changed_paths(repo_path)
    except RuntimeError as exc:
        result["git"] = "unavailable"
        result["error"] = str(exc)
        return result
    recorded = _recorded_paths(entries)
    for path, op in changed.items():
        if path in recorded:
            result["covered"].append(path)
        else:
            result["unlogged"][path] = op
    for path in sorted(recorded):
        if path not in changed:
            result["phantom"].append(path)
    total = len(changed)
    covered = len(result["covered"])
    result["coverage"] = round(100.0 * covered / total, 2) if total else 100.0
    result["changed"] = changed
    return result


def repo_id_for(repo_path: str) -> str:
    return sha256_hex(canon_bytes({"path": os.path.normpath(os.path.abspath(repo_path))}))[:16]
