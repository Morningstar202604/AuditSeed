import json
import subprocess
import sys
import os

from conftest import SERVER_DIR


def _server(repo, storage_root):
    """Spawn the MCP server with an isolated storage root."""
    env = os.environ.copy()
    env["USERPROFILE"] = str(storage_root)
    env["HOME"] = str(storage_root)
    return subprocess.Popen(
        [sys.executable, "mcp_server.py"],
        cwd=SERVER_DIR,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _send(proc, *msgs):
    proc.stdin.write("\n".join(json.dumps(m) for m in msgs) + "\n")
    proc.stdin.flush()


def _recv(proc):
    line = proc.stdout.readline()
    assert line.strip(), "server closed unexpectedly: " + proc.stderr.read()
    return json.loads(line)


def _req(id_, method, params=None):
    m = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        m["params"] = params
    return m


def test_protocol_matrix(repo, root):
    proc = _server(repo, root)
    try:
        # initialize
        _send(proc, _req(1, "initialize", {}))
        init = _recv(proc)
        assert init["result"]["serverInfo"]["name"] == "auditseed"
        assert "tools" in init["result"]["capabilities"]

        # notification: must NOT produce a response
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, _req(2, "tools/list"))
        only = _recv(proc)
        assert only["id"] == 2
        assert len(only["result"]["tools"]) >= 6

        # unknown method
        _send(proc, _req(3, "no/such/method"))
        resp = _recv(proc)
        assert resp["error"]["code"] == -32601

        # unknown tool
        _send(proc, _req(4, "tools/call", {"name": "nope", "arguments": {}}))
        resp = _recv(proc)
        assert resp["error"]["code"] == -32602

        # malformed json line → parse error with id null
        proc.stdin.write("this is not json\n")
        proc.stdin.flush()
        resp = _recv(proc)
        assert resp["error"]["code"] == -32700 and resp["id"] is None
    finally:
        proc.kill()


def test_full_audit_flow_via_tools(repo, root):
    proc = _server(repo, root)
    try:
        _send(proc, _req(1, "initialize", {}))
        _recv(proc)
        _send(
            proc,
            _req(
                2,
                "tools/call",
                {
                    "name": "audit_begin",
                    "arguments": {
                        "repo": str(repo),
                        "task": "flow-1",
                        "reason": "exercise the full flow over MCP",
                    },
                },
            ),
        )
        begin = _recv(proc)
        assert "ok" in json.loads(begin["result"]["content"][0]["text"])

        (repo / "app.py").write_text("print('v2')\n", encoding="utf-8")
        _send(
            proc,
            _req(
                3,
                "tools/call",
                {"name": "audit_note", "arguments": {"repo": str(repo), "text": "halfway"}},
            ),
        )
        _recv(proc)

        _send(
            proc,
            _req(
                4,
                "tools/call",
                {
                    "name": "audit_finish",
                    "arguments": {"repo": str(repo), "task": "flow-1", "outcome": "merged"},
                },
            ),
        )
        _recv(proc)

        _send(
            proc,
            _req(
                5,
                "tools/call",
                {"name": "audit_verify", "arguments": {"repo": str(repo)}},
            ),
        )
        ver = json.loads(_recv(proc)["result"]["content"][0]["text"])
        assert ver["ok"] is True and ver["entries"] >= 3

        _send(
            proc,
            _req(
                6,
                "tools/call",
                {
                    "name": "audit_export",
                    "arguments": {"repo": str(repo), "task": "flow-1", "format": "json"},
                },
            ),
        )
        report = json.loads(_recv(proc)["result"]["content"][0]["text"])
        assert report["task"] == "flow-1" and report["outcome"] == "merged"
    finally:
        proc.kill()
