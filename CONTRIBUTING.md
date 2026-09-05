# Contributing to AuditSeed

AuditSeed provides a tamper-evident audit trail for AI coding agents, capturing every file edit and command in a verifiable SHA-256 hash chain. This document explains how to contribute, the working rules every change must follow, and how to report problems.

## Working rules

* Dependency updates: search the whole repository for every occurrence of a dependency (build files, lockfiles, CI workflows, docs) before bumping. A partial bump — declaration updated but lockfile or a pinned action left behind — is the most common cause of "works locally, CI fails". Keep lockfiles in the same commit as the declaration. Move version-coupled toolchain upgrades together in one commit.
* Refactoring: pull latest main first, work on a fresh branch, keep commits atomic with messages that state the why, and always run the full check suite before pushing (for this repo: `python -m pytest`). A branch left behind main cannot be merged under the repository's branch protection.
* Merge conflicts: resolve conflicts in the working tree against the latest main; never force-push shared branches; never resolve a conflict by blindly taking either side — re-read both sides and keep both changes when they are both valid.
* Versioning: releases follow X.Y.Z starting at 0.0.0. Last digit = fixes, middle digit = feature work, first digit stays 0 until a stable release is declared. Bump the version in code, CHANGELOG.md and the tag in the same change.

## Development environment

AuditSeed's runtime is pure Python standard library (Python 3.9+) with no third-party dependencies; `pytest` is used for development only.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Common commands

- Run the full test suite: `python -m pytest`
- Run the CLI: `python bin/auditseed.py --help`
- Start the MCP server: `python server/mcp_server.py`

## Submitting changes

1. Fork this repository and clone your fork locally.
2. Create a feature branch from `main` (e.g. `feat/<short-description>` or `fix/<short-description>`).
3. Keep commits atomic, one logical change per commit, with messages that state the why (Conventional Commits).
4. Run the full test suite before pushing.
5. Open a Pull Request describing the motivation and impact; a maintainer reviews and merges it.

## Reporting issues

- For feature requests and non-security bugs, open an issue and fill out the relevant template.
- For security vulnerabilities, do not open a public issue. Use GitHub's private vulnerability reporting (Repository → Security → Report a vulnerability) and refer to [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contribution is released under the project license (PolyForm-NC-1.0.0).