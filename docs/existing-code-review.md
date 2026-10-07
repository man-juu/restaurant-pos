# Existing code review (Q-001, Step 0)

Reviewed 2026-10-07 at commit `564b870` ("Initial FastAPI setup"). Read-only: no code changed.

## 1. What exists

| Item | Finding |
| --- | --- |
| Structure | `app/main.py`, `requirements.txt`, `.gitignore`. One commit. |
| Language and framework | Python, FastAPI 0.134, Pydantic 2.12, SQLAlchemy 2.0.47 (installed, not used). |
| Database, models, migrations | None. No database driver (`asyncpg` is missing), no Alembic. |
| Tests, lint, CI, Docker | None. |
| How it runs | Presumably `uvicorn app.main:app`, which serves `GET /` → `{"message": "Restaurant POS Running 🚀"}`. |

## 2. Quality assessment

- `app/main.py` is a hello-world: a sync handler, no settings, no app factory, and no `/health`.
- `requirements.txt` is `pip freeze` output saved as **UTF-16 LE with CRLF line endings** (from Windows PowerShell `>` redirection). Many tools and Linux Docker builds can't read it. It also pins `colorama`, which is Windows-only, and mixes direct and transitive dependencies.
- `.gitignore` is reasonable but incomplete for the planned monorepo.

## 3. Comparison with docs/04 and docs/05

Nothing overlaps yet. The planned `backend/`, `frontend/`, `infra/` layout, the module structure, RLS tenancy, ledgers and audit log don't exist. Because there is no data model, there is no float-money or tenant-isolation debt to undo.

## 4. Keep or rewrite

| File | Recommendation |
| --- | --- |
| `app/main.py` | **Rewrite** as `backend/app/main.py` in slice 0.2. |
| `requirements.txt` | **Replace** with `backend/pyproject.toml` (UTF-8, direct deps only, with a lock file) in slice 0.1. |
| `.gitignore` | **Keep and extend** in slice 0.1 (`.env.*` with `!.env.example`, `node_modules/`, `dist/`, tool caches, coverage). |

In short, treat it as a throwaway prototype and start clean (this matches the Q-001 default).

## 5. Risks

- Secrets in history: none. Both commits contain only the files above, and `.env` was never tracked.
- Encoding: the UTF-16 file would break a Linux build. Removing it fixes that.
- No other risks found.

## 6. Questions for the owner

See the summary in chat. Recorded answers go into the `docs/09` changelog.
