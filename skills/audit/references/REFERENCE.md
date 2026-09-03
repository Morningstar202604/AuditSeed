# Audit skill — field reference

## Event taxonomy (what lands on the chain)

| type | who produces it | when |
| --- | --- | --- |
| `task_open` | you, via `audit_begin` | before the first edit of a piece of work |
| `file_change` | client hook (automatic) | every Write/Edit/MultiEdit |
| `cmd` | client hook (automatic) | every Bash call |
| `note` | you, via `audit_note` | decision breadcrumbs worth keeping |
| `verify` | verification tools | receipts (e.g. AgentSeed verify results) |
| `task_close` | you, via `audit_finish` | work complete, honestly labeled |
| `anchor` | user / CI | chain-head hash exported for external proof |

## Reason quality rubric

A good `reason` answers: what is changing, why now, and what was wrong before.

- Bad: "fix bug"
- Bad: "update code"
- Good: "login race: two concurrent requests could both consume the reset
  token because the check-then-set in session.py:88 is not atomic; making it
  a single conditional UPDATE"
- Good: "bump fastjson per security rule java-dep-fastjson-vuln; 1.x has
  known deserialization RCE history, team standard is jackson"

## Outcome vocabulary

- `merged` — the change is kept as-is
- `partial` — some of it kept; say what remains in `summary`
- `reverted` — tried and rolled back (this is a *good* chain entry: it keeps
  the lesson and the diff evidence)
- `abandoned` — the task was dropped before any real change

## Anti-patterns

- Declaring one giant task for a whole session — split per coherent change.
- Declaring AFTER editing "to be safe" — the coverage report timestamps
  make late declarations visible. Declare first; if you forget, say so.
- Copy-pasting the same reason across tasks — reviewers see this as noise.
- Treating `reverted` as failure — in an audited workflow, honest reverts
  are exactly what the chain is for.
