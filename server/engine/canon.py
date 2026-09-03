"""Canonical JSON serialization and SHA-256 helpers.

Every entry in the audit chain is hashed over its canonical form:
UTF-8, sorted keys, compact separators, non-ASCII preserved.
Two implementations serializing the same entry must agree byte-for-byte,
otherwise the chain breaks — so this module is the single source of truth.
"""
from __future__ import annotations

import hashlib
import json


def canon_bytes(obj) -> bytes:
    """Serialize to the canonical byte form used for hashing."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entry_hash(entry: dict) -> str:
    """Hash an entry over everything except its own `hash` field."""
    body = {k: v for k, v in entry.items() if k != "hash"}
    return sha256_hex(canon_bytes(body))


def repo_fingerprint(repo_path: str) -> str:
    """Stable, non-reversible fingerprint of the repo absolute path.

    The path itself never enters the chain (privacy); only this prefix does.
    """
    import os

    norm = os.path.normpath(os.path.abspath(repo_path))
    return sha256_hex(canon_bytes({"path": norm}))[:16]
