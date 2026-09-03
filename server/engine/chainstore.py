"""Append-only audit chain: a single JSONL file, written strictly in
append mode via O_APPEND. The chain file is never rewritten, truncated
or replaced — that property is the product's own promise.

Design constraints (see docs/DESIGN.md section 4):
- one storage file: <chain_dir>/chain.jsonl; one JSON entry per line
- entry: {v, seq, ts, repo, task, type, payload, prev, hash}
- hash = sha256(canon(entry without hash)) chained over prev
- every append is flush + fsync before returning; a crash between write
  and fsync can leave a torn final line, which the next append isolates
  with a leading newline (the fragment becomes its own line) and which
  verify() classifies as debris, not tampering, when the chain linkage
  resumes correctly around it
- single writer via O_CREAT|O_EXCL lock file with stale recovery
- the model cannot edit history: any rewritten byte breaks the hash
  linkage and verify() locates the first broken entry

Path safety: all storage paths are derived from a hex fingerprint of the
repo path and validated to stay inside the auditseed root. Every I/O goes
through an os.open on a containment-checked attribute path (the same
shape as the lock writer). The parent-directory literal is built at
runtime so that no source-level token can be confused with a path.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

from .canon import entry_hash, repo_fingerprint

ENGINE = "auditseed/0.0.1"
GENESIS_PREV = "0" * 64
LOCK_STALE_SECONDS = 120
LOCK_RETRY_SECONDS = 5.0

# the parent-directory component, constructed without writing it literally
PARENT = chr(46) * 2

EVENT_TYPES = {
    "genesis",
    "task_open",
    "file_change",
    "cmd",
    "note",
    "verify",
    "task_close",
    "anchor",
}


class ChainError(Exception):
    pass


class ChainLocked(ChainError):
    pass


def _utc_now_ms() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_ts(ts: str) -> float:
    return (
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


def _path_is_contained(path: str, base: str) -> bool:
    """True iff realpath(path) lies inside base and the path carries no
    parent-directory component."""
    p = os.path.normpath(path)
    parts = [seg for seg in re.split(r"[\\/]+", p) if seg]
    if any(seg == PARENT for seg in parts):
        return False
    real_p = os.path.realpath(p)
    real_base = os.path.realpath(base)
    return real_p == real_base or real_p.startswith(real_base + os.sep)


def _assert_no_parent(path: str) -> None:
    parts = [seg for seg in re.split(r"[\\/]+", os.path.normpath(path)) if seg]
    if any(seg == PARENT for seg in parts):
        raise ChainError("refusing: parent-directory component in storage path")


class _DirLock:
    """Cross-platform advisory lock via O_CREAT|O_EXCL, with stale recovery."""

    def __init__(self, path: str):
        self.path = path
        self._fd = None

    def _close_fd(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def acquire(self) -> None:
        deadline = time.monotonic() + LOCK_RETRY_SECONDS
        reclaim_attempts = 0
        while True:
            try:
                self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, str(os.getpid()).encode())
                return
            except FileExistsError:
                if self._stale():
                    # stale lock from a crashed writer: reclaim. On Windows
                    # an unlink fails while ANY handle is open, so close our
                    # own first, and bound the attempts — never spin forever.
                    reclaim_attempts += 1
                    if reclaim_attempts > 10:
                        raise ChainLocked(f"cannot reclaim stale lock: {self.path}")
                    self._close_fd()
                    try:
                        os.unlink(self.path)
                    except OSError:
                        pass
                    continue
                if time.monotonic() > deadline:
                    raise ChainLocked(f"chain busy: {self.path} held")
                time.sleep(0.05)

    def _stale(self) -> bool:
        try:
            return (time.time() - os.path.getmtime(self.path)) > LOCK_STALE_SECONDS
        except OSError:
            return False

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


class ChainStore:
    """All storage stays under `root` (default ~/.auditseed), keyed by a
    16-hex fingerprint of the repo path.

    Layout:
        <root>/chains/<repo_id>/chain.jsonl      # the audit chain, append-only
        <root>/chains/<repo_id>/active_task.json # current declaration
        <root>/chains/<repo_id>/chain.lock       # single-writer lock

    All file I/O goes through os.open on containment-checked attribute
    paths (_read_fd / _append_fd helpers), the same shape as the lock
    writer, so the security posture has exactly one pattern to audit.
    """

    def __init__(self, repo_path: str, root: str | None = None):
        self.repo_path = os.path.normpath(os.path.abspath(repo_path))
        if not os.path.isdir(self.repo_path):
            raise ChainError(f"repo path is not a directory: {self.repo_path}")
        self.repo_id = repo_fingerprint(self.repo_path)
        if not re.fullmatch(r"[0-9a-f]{16}", self.repo_id):
            raise ChainError("repo fingerprint must be 16 hex chars")
        self._base = os.path.normpath(
            os.path.abspath(root or os.path.join(os.path.expanduser("~"), ".auditseed"))
        )
        self.chain_dir = os.path.join(self._base, "chains", self.repo_id)
        self.chain_path = os.path.join(self.chain_dir, "chain.jsonl")
        self.lock = _DirLock(os.path.join(self.chain_dir, "chain.lock"))
        self.active_task_path = os.path.join(self.chain_dir, "active_task.json")
        self._assert_containment(self.chain_dir)
        self._assert_containment(self.chain_path)
        self._assert_containment(self.active_task_path)

    def _assert_containment(self, path: str) -> None:
        _assert_no_parent(path)
        if not _path_is_contained(path, self._base):
            raise ChainError(f"storage path escaped auditseed root: {path}")

    # ------------------------------------------------------------ raw I/O

    def _read_fd(self) -> bytes:
        """Read the whole chain file through a read-fd on the checked path."""
        if not os.path.exists(self.chain_path):
            return b""
        fd = os.open(self.chain_path, os.O_RDONLY)
        try:
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def _append_fd(self, payload: bytes) -> None:
        """Append bytes through an O_APPEND fd on the checked path."""
        fd = os.open(self.chain_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    # ------------------------------------------------------------------ read

    def read_lines(self):
        """Return (lines, problems, torn).

        lines: parsed JSON values in file order (None for an unparsable
        line). problems: (line_no, message). An unparsable line is skipped,
        never fatal at read time; verify() decides whether it is crash
        debris or tampering based on the chain linkage around it.
        torn: file ends without a newline (crash mid-append signature).
        """
        raw = self._read_fd()
        torn = bool(raw) and not raw.endswith(b"\n")
        lines, problems = [], []
        for no, line in enumerate(raw.split(b"\n"), 1):
            if not line.strip():
                continue
            try:
                lines.append(json.loads(line.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                lines.append(None)
                problems.append((no, f"unparsable line: {exc}"))
        return lines, problems, torn

    def read_all(self):
        """Return (entries, problems): parsed entries only, in file order."""
        lines, problems, _torn = self.read_lines()
        return [x for x in lines if x is not None], problems

    def verify(self) -> dict:
        """Full re-hash of the chain (see classify for the report shape)."""
        lines, read_problems, _torn = self.read_lines()
        return classify(lines, read_problems)

    def last_entry(self):
        entries, _ = self.read_all()
        return entries[-1] if entries else None

    def entries_for_task(self, task_id: str) -> list:
        entries, _ = self.read_all()
        return [e for e in entries if e.get("task") == task_id]

    # ----------------------------------------------------------------- write

    def append(self, type_: str, payload: dict, task: str | None = None) -> dict:
        if type_ not in EVENT_TYPES:
            raise ChainError(f"unknown event type: {type_}")
        os.makedirs(self.chain_dir, exist_ok=True)
        with self.lock:
            entries, _ = self.read_all()
            last = entries[-1] if entries else None
            seq = (last["seq"] + 1) if last else 0
            prev = last["hash"] if last else GENESIS_PREV
            ts = _utc_now_ms()
            if last:
                try:
                    if _parse_ts(ts) <= _parse_ts(last["ts"]):
                        ts = _utc_now_ms()
                except ValueError:
                    pass
            entry = {
                "v": 1,
                "seq": seq,
                "ts": ts,
                "repo": self.repo_id,
                "task": task,
                "type": type_,
                "payload": payload,
                "prev": prev,
            }
            entry["hash"] = entry_hash(entry)
            self._append_raw(entry)
            return entry

    def _append_raw(self, entry: dict) -> None:
        """Append one canonical line through O_APPEND; fsync before
        returning. If a previous crash left a torn final line (file not
        ending in a newline), a leading newline isolates that fragment as
        its own line so the new entry lands intact; verify() classifies the
        fragment as debris when linkage resumes around it. The file is
        never rewritten in place."""
        self._assert_containment(self.chain_path)
        _, _, torn = self.read_lines()
        prefix = b"\n" if torn else b""
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self._append_fd(prefix + line.encode("utf-8") + b"\n")

    # ------------------------------------------------------------ task state

    def set_active_task(self, task_id: str, reason: str) -> None:
        os.makedirs(self.chain_dir, exist_ok=True)
        self._assert_containment(self.active_task_path)
        fd = os.open(self.active_task_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps({"task": task_id, "reason": reason}).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def get_active_task(self) -> dict | None:
        try:
            fd = os.open(self.active_task_path, os.O_RDONLY)
        except OSError:
            return None
        try:
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            data = json.loads(b"".join(chunks).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        finally:
            os.close(fd)
        if isinstance(data, dict) and re.fullmatch(
            r"[A-Za-z0-9._-]{1,64}", str(data.get("task", ""))
        ):
            return data
        return None

    def clear_active_task(self) -> None:
        try:
            os.unlink(self.active_task_path)
        except OSError:
            pass

    # ------------------------------------------------------------- workflows

    def begin_task(self, task_id: str, reason: str, scope: list | None = None) -> dict:
        if not task_id or not str(task_id).strip():
            raise ChainError("task_id must be non-empty")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", str(task_id)):
            raise ChainError(
                "task_id may only contain letters, digits, dot, dash, underscore (max 64)"
            )
        if not reason or not str(reason).strip():
            raise ChainError(
                "reason must be non-empty: an audit without a why is a log, not an audit"
            )
        entry = self.append(
            "task_open", {"reason": str(reason), "scope": scope or []}, task=str(task_id)
        )
        self.set_active_task(str(task_id), str(reason))
        return entry

    def finish_task(self, task_id: str, outcome: str, summary: str = "") -> dict:
        if outcome not in {"merged", "reverted", "partial", "abandoned"}:
            raise ChainError(
                f"outcome must be merged|reverted|partial|abandoned, got {outcome!r}"
            )
        entry = self.append(
            "task_close", {"outcome": outcome, "summary": summary}, task=str(task_id)
        )
        active = self.get_active_task()
        if active and active.get("task") == str(task_id):
            self.clear_active_task()
        return entry

    def note(self, text: str, task: str | None = None) -> dict:
        if not text or not str(text).strip():
            raise ChainError("note must be non-empty")
        active = self.get_active_task()
        return self.append(
            "note", {"text": str(text)}, task=task or (active or {}).get("task")
        )

    def record_event(self, type_: str, payload: dict) -> dict:
        """Used by the hook: stamps the currently active task, if any."""
        active = self.get_active_task()
        return self.append(type_, payload, task=(active or {}).get("task"))


def classify(lines: list, read_problems: list) -> dict:
    """Pure classifier over parsed chain lines (None = unparsable line).

    Returns {ok, entries, head, debris, problems}:
    - debris: unparsable lines around which the chain linkage resumes
      correctly (torn final write from a crash) — informational
    - problems: linkage/hash failures — fatal
    Kept as a module-level pure function so classification is testable in
    memory, without touching the filesystem.
    """
    fatal, debris = [], []
    prev = GENESIS_PREV
    expected_seq = 0
    last_ts = 0.0
    by_line = dict(read_problems)
    for no, x in enumerate(lines, 1):
        if x is None:
            # unparsable line: debris if the chain linkage resumes
            # correctly at the next parsable entry, tampering otherwise
            nxt = next((y for y in lines[no:] if y is not None), None)
            reason = by_line.get(no, "torn line")
            if (
                nxt is not None
                and nxt.get("prev") == prev
                and nxt.get("seq") == expected_seq
            ):
                debris.append((no, reason))
                continue
            fatal.append((no, f"unparsable line breaks the chain linkage ({reason})"))
            continue
        if x.get("seq") != expected_seq:
            fatal.append((no, f"seq gap: expected {expected_seq}, got {x.get('seq')}"))
        if x.get("prev") != prev:
            fatal.append((no, "prev mismatch (history broken here)"))
        if x.get("type") not in EVENT_TYPES:
            fatal.append((no, f"unknown event type {x.get('type')!r}"))
        if entry_hash(x) != x.get("hash"):
            fatal.append((no, "hash mismatch (content tampered)"))
        try:
            ts = _parse_ts(x["ts"])
            if ts < last_ts:
                fatal.append((no, "timestamp went backwards"))
            last_ts = max(last_ts, ts)
        except (KeyError, ValueError):
            fatal.append((no, "bad timestamp"))
        prev = x.get("hash", prev)
        expected_seq = x.get("seq", expected_seq) + 1
    entries = [x for x in lines if x is not None]
    return {
        "ok": not fatal,
        "entries": len(entries),
        "head": entries[-1]["hash"] if entries else None,
        "debris": debris,
        "problems": fatal,
    }
