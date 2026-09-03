import os
import time

import pytest

from engine.chainstore import GENESIS_PREV, ChainError, ChainLocked, classify
from engine.canon import entry_hash

GENESIS_PREV = GENESIS_PREV  # re-exported for readability below


def test_first_append_creates_genesis(store):
    e = store.append("note", {"text": "hello"})
    assert e["seq"] == 0 and e["prev"] == GENESIS_PREV and e["type"] == "note"
    v = store.verify()
    assert v["ok"] and v["entries"] == 1 and v["head"] == e["hash"]


def test_chain_links_and_orders(store):
    a = store.append("note", {"text": "a"})
    b = store.append("note", {"text": "b"})
    c = store.begin_task("t1", "because the login race must die")
    assert b["prev"] == a["hash"] and c["prev"] == b["hash"]
    assert [x["seq"] for x in (a, b, c)] == [0, 1, 2]
    v = store.verify()
    assert v["ok"] and v["entries"] == 3


def test_task_attribution_and_finish_clears_active(store):
    store.begin_task("feat-x", "to fix the race")
    e = store.record_event("file_change", {"path": "src/a.py", "op": "modify"})
    assert e["task"] == "feat-x"
    store.note("chose approach B")
    store.finish_task("feat-x", "merged", "done")
    assert store.get_active_task() is None
    entries = store.entries_for_task("feat-x")
    assert [x["type"] for x in entries] == [
        "task_open",
        "file_change",
        "note",
        "task_close",
    ]


# --------------------------------------------------------------------------
# classification tests — in-memory, covering every fatal/debris branch
# --------------------------------------------------------------------------


def _entry(seq, prev, text="x", repo="a" * 16, ts="2026-09-03T00:00:00.000Z"):
    e = {
        "v": 1,
        "seq": seq,
        "ts": ts,
        "repo": repo,
        "task": None,
        "type": "note",
        "payload": {"text": text},
        "prev": prev,
    }
    e["hash"] = entry_hash(e)
    return e


def _chain(n=3):
    lines, prev = [], GENESIS_PREV
    for i in range(n):
        e = _entry(i, prev, text=f"e{i}")
        prev = e["hash"]
        lines.append(e)
    return lines


def test_classify_ok_chain():
    r = classify(_chain(3), [])
    assert r["ok"] and r["entries"] == 3 and r["debris"] == []


def test_classify_hash_mismatch_is_fatal():
    lines = _chain(3)
    lines[1]["payload"]["text"] = "TAMPERED"  # keep stale hash
    r = classify(lines, [])
    assert not r["ok"]
    assert any("hash mismatch" in msg for _, msg in r["problems"])


def test_classify_seq_gap_is_fatal():
    lines = _chain(3)
    del lines[1]
    r = classify(lines, [])
    assert not r["ok"]
    assert any("seq gap" in msg for _, msg in r["problems"])


def test_classify_prev_mismatch_is_fatal():
    lines = _chain(3)
    lines[2]["prev"] = "f" * 64
    r = classify(lines, [])
    assert not r["ok"]
    assert any("prev mismatch" in msg for _, msg in r["problems"])


def test_classify_unknown_type_is_fatal():
    lines = _chain(2)
    lines[1]["type"] = "self_rewrite"
    lines[1]["hash"] = entry_hash(lines[1])
    r = classify(lines, [])
    assert not r["ok"]
    assert any("unknown event type" in msg for _, msg in r["problems"])


def test_classify_debris_when_linkage_resumes():
    lines = _chain(2)
    # a torn (unparsable) line between entry 0 and 1, linkage intact
    broken = lines[0:1] + [None] + lines[1:]
    r = classify(broken, [(2, "unparsable line")])
    assert r["ok"]
    assert r["debris"] and r["debris"][0][0] == 2
    assert r["entries"] == 2


def test_classify_broken_linkage_around_unparsable_is_fatal():
    lines = _chain(2)
    # fragment in the middle, but the following entry does NOT resume linkage
    lines[1]["prev"] = "f" * 64
    broken = lines[0:1] + [None] + lines[1:]
    r = classify(broken, [(2, "unparsable line")])
    assert not r["ok"]
    assert any("breaks the chain linkage" in msg for _, msg in r["problems"])


def test_classify_tail_fragment_without_resume_is_fatal():
    lines = _chain(1) + [None]
    r = classify(lines, [(2, "unparsable line")])
    # nothing resumes after the fragment: conservative fatal
    assert not r["ok"]


# --------------------------------------------------------------------------
# store-level behaviors
# --------------------------------------------------------------------------


def test_lock_blocks_concurrent_writer(store):
    store.append("note", {"text": "a"})
    with store.lock:
        with pytest.raises(ChainLocked):
            store.append("note", {"text": "b"})


def test_stale_lock_is_reclaimed(store):
    store.append("note", {"text": "a"})
    # create a lock via the store's own writer, then backdate it
    store.lock.acquire()
    stale = time.time() - 999
    os.utime(store.lock.path, (stale, stale))
    e = store.append("note", {"text": "b"})  # must reclaim, not raise
    assert e["seq"] == 1
    store.lock.release()


def test_begin_validation(store):
    with pytest.raises(ChainError):
        store.begin_task("", "reason")
    with pytest.raises(ChainError):
        store.begin_task("bad task id!", "reason")
    with pytest.raises(ChainError):
        store.begin_task("ok-task", "  ")
    with pytest.raises(ChainError):
        store.finish_task("t", "nonsense-outcome")


def test_refuses_unknown_event_type(store):
    # in the append-only single-file design there is no overwrite code path
    # at all (O_APPEND cannot rewrite history); the guarded entry point is
    # the event-type whitelist
    with pytest.raises(ChainError):
        store.append("self_rewrite", {"text": "rewrite history"})
