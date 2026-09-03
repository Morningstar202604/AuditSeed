---
name: audit
description: Declare what you are about to change and why BEFORE editing, then close the task with an honest outcome. Use at the start of any change in a repository with AuditSeed installed — the hook records every file edit and command automatically, but the *why* only you can declare. Refusing to declare makes your edits show up as unlogged changes in the coverage report.
---

# Audit — declare, act, close

You are working in a repository audited by AuditSeed. A tamper-evident chain
records every file change and command you make (via client hooks) — that part
happens to you, not by you. What only YOU can provide is the *why*. The chain
is designed around that division of labor.

## The ceremony (mandatory)

1. **Before your first edit or command**, open a task:

   `audit_begin(repo: <repo root>, task: <short-id>, reason: <why>, scope: <expected paths>)`

   - `task`: short, stable id for this piece of work (e.g. `fix-login-race`)
   - `reason`: one or two sentences a reviewer can audit later. Not "fix bug" —
     say which bug, from where, and what changes because of it.
   - `scope` (optional): the paths you expect to touch. Divergence from scope
     becomes visible in the report — use it honestly.

2. **Work normally.** Every Write/Edit/Bash is captured and attributed to the
   open task automatically.

3. **When adding a non-obvious decision mid-work**, leave a breadcrumb:

   `audit_note(repo: <root>, text: "chose approach B because X; alternative A rejected because Y")`

4. **When done**, close the task honestly:

   `audit_finish(repo: <root>, task: <id>, outcome: merged|reverted|partial|abandoned, summary: <what actually happened>)`

## Rules

- One task = one coherent piece of work. Do not batch unrelated changes into
  one declaration.
- Never re-open a task to "restate" history — the chain is append-only and
  the coverage report will show the truth anyway.
- If you edit files WITHOUT an open task, they are recorded as unlogged
  changes; `auditseed gate` will fail on them. If you notice this happened,
  open a task and note the miss honestly (`audit_note`), rather than hoping.
- Verify results from other tools (e.g. AgentSeed) may be appended as
  receipts; ask before claiming a receipt you have not run.

## What this is not

The chain is not a chat log and not a substitute for code review. It is the
bridge between "the model claims" and "the tree shows" — keep your
declarations accurate and short.
