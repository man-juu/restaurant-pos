# Existing code review (Q-001)

Reviewed: commit `564b870` "Initial FastAPI setup". Status: waiting on an owner decision. Nothing has been changed.

## What exists

| File | Contents | Recommendation |
| --- | --- | --- |
| `app/main.py` | 6-line FastAPI hello-world (`GET /`) | **Rewrite**: replace with `backend/app/main.py` (app factory, health route) in Phase 0. Nothing in it is worth keeping. |
| `requirements.txt` | `pip freeze` output, **UTF-16 LE with CRLF**, includes `colorama` (Windows-only) | **Rewrite**: many tools can't read UTF-16. Use `backend/pyproject.toml` with pinned deps (async SQLAlchemy needs `asyncpg`, plus `alembic`, `pydantic-settings`); dev tools go in a separate group. |
| `.gitignore` | venv, pycache, `*.db`, `.env` | **Keep and extend**: add `.env.*` with `!.env.example`, `node_modules/`, `dist/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`. |

## Gaps against CLAUDE.md

- `docs/` is missing: no specs, no ADRs, no `README.md` approval table, no `docs/tasks/phase-0.md`. Because of the status gate, no application code can be written until these exist and are approved.
- The layout doesn't match yet (`app/` at the root instead of `backend/app/`, no `frontend/` or `infra/`).
- No tests, lint config, Docker Compose or CI.

## Decision needed from the owner

1. Add the `docs/` specs to the repo and mark them Approved in `docs/README.md`.
2. Confirm that the prototype can be deleted and replaced as described above.
