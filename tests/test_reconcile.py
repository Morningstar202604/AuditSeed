import json
import os
import subprocess

import pytest

from engine.reconcile import reconcile


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_non_git_dir_reports_honestly(tmp_path, store):
    d = tmp_path / "plain"
    d.mkdir()
    rec = reconcile(str(d), store.read_all()[0])
    assert rec["git"] == "not_a_repo"


def test_unlogged_change_detected(repo, store):
    store.begin_task("t1", "test reconciliation")
    (repo / "app.py").write_text("print('v2')\n", encoding="utf-8")
    entries = store.read_all()[0]
    rec = reconcile(str(repo), entries)
    assert rec["git"] == "available"
    assert rec["changed"] == {"app.py": "modify"}
    assert rec["unlogged"] == {"app.py": "modify"}
    assert rec["coverage"] == 0.0


def test_recorded_change_is_covered(repo, store):
    store.begin_task("t1", "edit app.py properly")
    (repo / "app.py").write_text("print('v2')\n", encoding="utf-8")
    store.record_event("file_change", {"path": "app.py", "op": "modify"})
    entries = store.read_all()[0]
    rec = reconcile(str(repo), entries)
    assert rec["covered"] == ["app.py"]
    assert rec["unlogged"] == {}
    assert rec["coverage"] == 100.0


def test_untracked_new_file_is_add(repo, store):
    store.begin_task("t1", "new module")
    (repo / "newmod.py").write_text("x = 1\n", encoding="utf-8")
    entries = store.read_all()[0]
    rec = reconcile(str(repo), entries)
    assert rec["changed"] == {"newmod.py": "add"}


def test_deletion_is_delete(repo, store):
    store.begin_task("t1", "remove app.py")
    os.remove(repo / "app.py")
    entries = store.read_all()[0]
    rec = reconcile(str(repo), entries)
    assert rec["changed"] == {"app.py": "delete"}


def test_phantom_event_detected(repo, store):
    store.begin_task("t1", "claimed to touch config.py but did not")
    store.record_event("file_change", {"path": "config.py", "op": "modify"})
    entries = store.read_all()[0]
    rec = reconcile(str(repo), entries)
    assert "config.py" in rec["phantom"]
    assert rec["coverage"] == 100.0  # nothing actually changed in the tree
