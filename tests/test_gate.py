import os
import subprocess
import sys

from conftest import PROJECT_ROOT, make_hook_env

CLI = os.path.join(PROJECT_ROOT, "bin", "auditseed.py")


def _cli(repo, storage_root, *args):
    env = make_hook_env(repo, storage_root)
    return subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True,
        text=True,
        cwd=str(repo),
        env=env,
        timeout=60,
    )


def _storage(root):
    return os.path.join(root, "gate-storage")


def _full_task(repo, storage_root):
    """begin → change → record → finish, via the library (hook equivalent).

    root matches what the CLI derives from the HOME override:
    expanduser("~") == storage_root → base == storage_root/.auditseed
    """
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "server"))
    from engine.chainstore import ChainStore

    store = ChainStore(str(repo), root=os.path.join(str(storage_root), ".auditseed"))
    store.begin_task("task-a", "gate happy path exercise")
    (repo / "app.py").write_text("print('v2')\n", encoding="utf-8")
    store.record_event("file_change", {"path": "app.py", "op": "modify"})
    store.finish_task("task-a", "merged", "done")


def test_gate_passes_on_clean_verified_task(repo, root):
    storage = _storage(root)
    os.makedirs(storage, exist_ok=True)
    _full_task(repo, storage)
    proc = _cli(repo, storage, "gate", "--repo", str(repo), "--task", "task-a")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_gate_fails_when_chain_verify_reports_failure(repo, root, monkeypatch):
    """The gate's integrity branch: verify() failure → exit 1 (the byte-level
    tamper drill lives in CI; here we exercise the gate's decision logic
    in-process, with verify() injected to report a broken chain)."""
    storage = _storage(root)
    os.makedirs(storage, exist_ok=True)
    _full_task(repo, storage)
    monkeypatch.setenv("USERPROFILE", str(storage))
    monkeypatch.setenv("HOME", str(storage))

    sys.path.insert(0, os.path.join(PROJECT_ROOT, "server"))
    import argparse
    import importlib.util

    import engine.chainstore as cs

    spec = importlib.util.spec_from_file_location("auditseed_cli", CLI)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    def fake_verify(self):
        return {
            "ok": False,
            "entries": 3,
            "head": None,
            "debris": [],
            "problems": [(2, "hash mismatch (content tampered)")],
        }

    monkeypatch.setattr(cs.ChainStore, "verify", fake_verify)
    args = argparse.Namespace(repo=str(repo), task="task-a", min_coverage=100.0)
    rc = cli.cmd_gate(args)
    assert rc == 1


def test_gate_fails_on_unlogged_changes(repo, root):
    storage = _storage(root)
    os.makedirs(storage, exist_ok=True)
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "server"))
    from engine.chainstore import ChainStore

    store = ChainStore(str(repo), root=os.path.join(str(storage), ".auditseed"))
    store.begin_task("task-b", "changed a file but hid it from the chain")
    (repo / "app.py").write_text("print('sneaky')\n", encoding="utf-8")
    store.finish_task("task-b", "merged")
    proc = _cli(
        repo, storage, "gate", "--repo", str(repo), "--task", "task-b", "--min-coverage", "100"
    )
    assert proc.returncode == 1
    assert "coverage" in proc.stdout


def test_gate_fails_on_unclosed_task(repo, root):
    storage = _storage(root)
    os.makedirs(storage, exist_ok=True)
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "server"))
    from engine.chainstore import ChainStore

    store = ChainStore(str(repo), root=os.path.join(str(storage), ".auditseed"))
    store.begin_task("task-c", "never finished")
    proc = _cli(repo, storage, "gate", "--repo", str(repo), "--task", "task-c")
    assert proc.returncode == 1
    assert "not closed" in proc.stdout


def test_gate_fails_on_unknown_task(repo, root):
    storage = _storage(root)
    os.makedirs(storage, exist_ok=True)
    proc = _cli(repo, storage, "gate", "--repo", str(repo), "--task", "ghost")
    assert proc.returncode == 1
    assert "no audit entries" in proc.stdout
