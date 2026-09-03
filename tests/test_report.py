import json

import pytest

from engine.report import export_json, export_markdown


@pytest.fixture()
def filled_store(store, repo):
    (repo / "app.py").write_text("print('v2')\n", encoding="utf-8")
    store.begin_task("feat-login", "login race: check-then-set is not atomic; making it a single conditional UPDATE")
    store.record_event("file_change", {"path": "app.py", "op": "modify", "tool": "Edit"})
    store.record_event("cmd", {"command": "pytest -q", "exit_code": 0})
    store.note("chose conditional UPDATE over a lock file")
    store.finish_task("feat-login", "merged", "single-line atomic update, tests green")
    return store


def test_json_report_is_valid_and_complete(filled_store):
    data = json.loads(export_json(filled_store, "feat-login"))
    assert data["schema"] == "auditseed.report/1"
    assert data["task"] == "feat-login"
    assert data["declaration"].startswith("login race")
    assert data["outcome"] == "merged"
    assert data["files"] == [{"path": "app.py", "op": "modify", "tool": "Edit"}]
    assert data["integrity"]["chain_verified"] is True
    assert data["integrity"]["chain_head"]
    assert data["coverage"]["git"] == "available"
    assert data["coverage"]["coverage_percent"] == 100.0


def test_markdown_report_contains_key_sections(filled_store):
    md = export_markdown(filled_store, "feat-login")
    assert "# AuditSeed changeset report" in md
    assert "feat-login" in md
    assert "login race" in md
    assert "`app.py`" in md
    assert "merged (kept)" in md
    assert "chain verified: YES" in md
    assert "chain head:" in md
    assert "coverage: 100.0%" in md
    assert "conditional UPDATE" in md  # the note is included


def test_unknown_task_raises(filled_store):
    with pytest.raises(ValueError):
        export_markdown(filled_store, "no-such-task")
