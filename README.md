<div align="center">

# AuditSeed

**The tamper-evident audit trail for AI coding agents.**

AgentSeed makes agents tell the truth. **AuditSeed makes their changes
provable** — every file edit and command is captured by the *client hook*
(not claimed by the model), the *why* is declared before work starts, and
the whole history lives in a SHA-256 hash chain you can verify and export
as a changeset report.

[![License](https://img.shields.io/badge/license-PolyForm_NC_1.0.0-purple)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.0.1-blue)](CHANGELOG.md)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

English · 中文 docs inside ([DESIGN.md](docs/DESIGN.md))

</div>

---

## Why

Ask any team using AI coding agents: *"Which agent changed this file, when,
and why?"* The answer today is: the conversation is gone, the model's
self-report is untrusted, and git shows *what* but never *why*.

- The **context window is ephemeral** — compaction, session end, another
  machine. Two weeks later nobody can answer the question above.
- **The model cannot audit itself.** A log written by the same party being
  audited is testimony, not evidence. Capture must be a deterministic
  process the agent cannot bypass or rewrite.
- **Compliance is catching up**: SOC2 change management, ISO 27001
  A.8.15/A.8.16, EU AI Act Art. 12 (automated logging) all demand exactly
  this layer for AI-assisted changes.

## What it is — in 30 seconds

A drop-in [Agent Plugins](https://agent-plugins.org) 1.0.0 plugin
(Skill + client hook + MCP server) with a three-layer closed loop:

| Layer | Role | Why it alone is not enough |
| --- | --- | --- |
| **Skill** (`audit`) | the agent *declares* task + reason before acting | soft instruction; model could skip it |
| **Client hook** | *hard-captures* every Write/Edit/MultiEdit/Bash | captures events but no "why", no storage semantics |
| **MCP server** | hash-chain store, tamper verification, git reconciliation, report export, CI gate | dead code unless called |

Any single layer is deficient; the bundle is the product. That bundling is
exactly what the new plugin spec makes possible.

## Quick start

```bash
# inside any repository, declare the work (the skill does this for you)
python bin/auditseed.py begin  --repo . --task fix-login-race \
    --reason "login race: check-then-set in session.py:88 is not atomic; single conditional UPDATE"

# ... work normally — hooks capture everything ...

python bin/auditseed.py finish --repo . --task fix-login-race --outcome merged

# verify, inspect, export
python bin/auditseed.py verify --repo .
python bin/auditseed.py status --repo .
python bin/auditseed.py export --repo . --task fix-login-race --format md

# CI gate: integrity + closure + 100% capture coverage, else the pipeline fails
python bin/auditseed.py gate --repo . --task fix-login-race --min-coverage 100
```

MCP tools: `audit_begin`, `audit_finish`, `audit_status`, `audit_verify`,
`audit_export`, `audit_note`. Deliberately absent: anything that lets the
model edit evidence.

## The honesty features

- **Coverage reconciliation** — the working tree (git) is ground truth; the
  report lists every change *without* a chain event and every event *without*
  a working-tree change. Gaps are visible, never hidden.
- **Debris vs tampering** — a crash mid-append leaves a torn line; `verify`
  classifies it as debris (linkage resumes around it) instead of failing.
- **Append-only by construction** — the chain file is written strictly with
  `O_APPEND`; no rewrite code path exists.
- **Local-first** — storage stays in `~/.auditseed`; nothing is uploaded.
- **Zero dependencies** — pure standard-library Python 3.9+; git only for
  reconciliation.

## Honest limitations (v0.0.1)

- Clients without hook support fall back to git reconciliation; the coverage
  report states the real gap.
- A local attacker with full disk access can delete the chain (external
  anchoring of the chain head ships in 0.1).
- The model's *reasoning* is not captured — only declarations, events, and
  receipts. See [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md).

## Family

- **AgentSeed** — the anti-hallucination gate (verify before "done")
- **AuditSeed** — this plugin: tamper-evident process audit & compliance export
- Together: the agent doesn't lie, and you can prove what it did.
