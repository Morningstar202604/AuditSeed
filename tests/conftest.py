import json
import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(PROJECT_ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


@pytest.fixture()
def repo(tmp_path):
    """A real git repository with one committed file."""
    r = tmp_path / "repo"
    r.mkdir()
    def git(*args):
        subprocess.run(
            ["git", "-C", str(r), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (r / "app.py").write_text("print('v1')\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    return r


@pytest.fixture()
def root(tmp_path):
    """Isolated auditseed storage root (never touches ~/.auditseed)."""
    root = tmp_path / "auditseed-root"
    root.mkdir()
    return str(root)


@pytest.fixture()
def store(repo, root):
    sys.path.insert(0, SERVER_DIR)
    from engine.chainstore import ChainStore

    return ChainStore(str(repo), root=root)


def make_hook_env(repo_path, storage_root):
    env = os.environ.copy()
    # point expanduser("~") at the isolated root for both platforms
    env["USERPROFILE"] = str(storage_root)
    env["HOME"] = str(storage_root)
    env["AUDITSEED_TEST_REPO"] = str(repo_path)
    return env
