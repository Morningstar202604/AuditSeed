import json
import os
import subprocess
import sys

from conftest import PROJECT_ROOT, make_hook_env

HOOK = os.path.join(PROJECT_ROOT, "hooks", "posttooluse.py")


def _run_hook(repo, storage_root, event):
    env = make_hook_env(repo, storage_root)
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=str(repo),
        env=env,
        timeout=30,
    )
    return proc


def _store_for(repo, storage_root):
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "server"))
    from engine.chainstore import ChainStore

    return ChainStore(str(repo), root=os.path.join(str(storage_root), ".auditseed"))


def test_edit_event_attributed_to_open_task(repo, root):
    storage = os.path.join(root, "hook-storage")
    os.makedirs(storage, exist_ok=True)
    store = _store_for(repo, storage)
    store.begin_task("hook-1", "hook attribution test")

    proc = _run_hook(
        repo,
        storage,
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(repo / "app.py")},
            "cwd": str(repo),
        },
    )
    assert proc.returncode == 0 and proc.stdout == ""
    entries = store.read_all()[0]
    fc = [e for e in entries if e.get("type") == "file_change"]
    assert len(fc) == 1
    assert fc[0]["task"] == "hook-1"
    assert fc[0]["payload"]["path"] == "app.py"  # relative to repo root
    assert fc[0]["payload"]["op"] == "modify"


def test_bash_event_recorded_as_cmd(repo, root):
    storage = os.path.join(root, "hook-storage")
    os.makedirs(storage, exist_ok=True)
    store = _store_for(repo, storage)
    store.begin_task("hook-cmd", "command capture")

    _run_hook(
        repo,
        storage,
        {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "cwd": str(repo)},
    )
    entries = store.read_all()[0]
    cmds = [e for e in entries if e.get("type") == "cmd"]
    assert len(cmds) == 1 and cmds[0]["payload"]["command"] == "pytest -q"


def test_uninteresting_tool_ignored(repo, root):
    storage = os.path.join(root, "hook-storage")
    os.makedirs(storage, exist_ok=True)
    store = _store_for(repo, storage)
    store.begin_task("hook-skip", "no events expected")
    _run_hook(repo, storage, {"tool_name": "Grep", "tool_input": {"pattern": "x"}, "cwd": str(repo)})
    entries = store.read_all()[0]
    assert [e["type"] for e in entries] == ["task_open"]


def test_event_without_open_task_is_unassigned(repo, root):
    storage = os.path.join(root, "hook-storage")
    os.makedirs(storage, exist_ok=True)
    store = _store_for(repo, storage)
    _run_hook(
        repo,
        storage,
        {"tool_name": "Edit", "tool_input": {"file_path": str(repo / "app.py")}, "cwd": str(repo)},
    )
    entries = store.read_all()[0]
    fc = [e for e in entries if e.get("type") == "file_change"]
    assert len(fc) == 1 and fc[0]["task"] is None  # unassigned → visible in coverage


def test_garbage_stdin_never_crashes(repo, root):
    storage = os.path.join(root, "hook-storage")
    os.makedirs(storage, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, HOOK],
        input="not json at all",
        capture_output=True,
        text=True,
        cwd=str(repo),
        env=make_hook_env(repo, storage),
        timeout=30,
    )
    assert proc.returncode == 0  # the hook never breaks the client
