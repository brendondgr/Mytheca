# Plan: Storyline Data Layer — Postgres persistence + Library CRUD wiring

> Status: in progress (feature branch `feat/storyline-data-layer`). This is the
> planner-skill copy of the approved plan; the working copy lives at
> `~/.claude/plans/cryptic-roaming-bachman.md`.

## Context

Mytheca's frontend Library is fully built but runs entirely on **in-memory seed data** (`web/frontend/lib/seed-data.ts` via `web/frontend/features/library/useLibraryState.ts`): create/edit/delete mutate React state and reset on reload. The backend is a stub — `web/backend/app/main.py` has only a `/health` route and every `app/*` package is an empty `__init__.py`.

This plan stands up the **FastAPI + Postgres data layer** so storylines, characters, settings, and scenarios can be created/edited/deleted and **persist**, then **wires the existing Library UI to that backend** so frontend and backend work together. It also lays a per-storyline **stat schema seam** (definitions on the storyline, clamped values on characters — surfaced on scene pages later, not in the Library yet) and **chat scaffolding as data structures only** (event + play-session tables and the NDJSON event envelope types — no streaming, agents, or turn logic).

Three scoping decisions are locked by the user:
1. **Postgres from the start**, with `python app.py backend` bringing services up and running preflight checks before serving.
2. **Stats = per-storyline schema seam**, fully functional at the data layer (no UI this pass).
3. **Chat = data structures only.**

## Key assumptions

- **Tests run on SQLite, app runs on Postgres** — dialect-neutral `JSON` + Python-side defaults so one metadata creates on both; pytest uses in-memory SQLite + dependency override (no Postgres/Docker for tests).
- **Sync SQLAlchemy + sync `def` route handlers** (psycopg3, no async driver).
- **camelCase wire format** via a `CamelModel` Pydantic base (`alias_generator=to_camel`, `populate_by_name=True`, `from_attributes=True`).
- **String PKs, client-id optional on create** (409 on collision); seed slugs survive.
- **`BranchTag` ≠ `EventType`** — modeled as two separate `Literal`s (the Embergate seed uses `check_request`).
- **Branches = JSON column; stats = normalized `stat_definitions` + `character_stats` tables**; stats exposed as **sibling resources**, not embedded in Character/Storyline.
- **`GET /storylines` returns summaries**; children fetched per-storyline and hydrated lazily on the frontend.
- **Frontend = await-then-apply + hand-rolled fetch**; backend down → honest error UI + Retry (no seed fallback).
- **Alembic deferred** (idempotent `create_all` for now); **no new dependencies**.

## Phases (commit per phase — `[Storyline Data Layer] (n/8) Complete: …`)

1. **Backend foundation** — `web/backend/app/core/{config,db,redis}.py` + tests (`utils/tests/backend/data/test_config.py`, `test_db.py`).
2. **Models + camelCase schemas** — `app/models/{storyline,character,setting,scenario,stat}.py`, `app/schemas/{base,storyline,character,setting,scenario,stat}.py` + `test_models.py`, `test_schemas.py`.
3. **CRUD routes** — `app/services/crud.py`, `app/routes/{storylines,characters,settings,scenarios}.py`, `main.py` (routers + CORS + `/api`) + `utils/tests/backend/api/test_*`. Docs: `api-contract.md`.
4. **Stat endpoints + clamping** — `app/routes/stats.py` (defs + character values; range locked, clamp, unknown-key reject) + `test_stats.py`. Docs: `api-contract.md`.
5. **Seed + preflight bootstrap** — `app/core/{seed,bootstrap}.py`, `web/backend/docker-compose.yml`, `app.py` wiring + minimal lifespan + `test_seed.py`, `test_bootstrap.py`. Docs: `deployment.md`, `workflow.md`.
6. **Chat scaffold (data only)** — `app/models/{event,session}.py`, `app/events/envelope.py` + `test_events.py`. Docs: `api-contract.md`, `data-flow.md`.
7. **Frontend API client** — `web/frontend/lib/api.ts`, `NEXT_PUBLIC_API_URL` in `.env.example` + `web/frontend/.env.local.example`. Docs: `deployment.md`.
8. **Wire the Library** — async `useLibraryState.ts` (load + await-then-apply + loading/error/pending), `EntityModal.tsx` (pending/error), `LibraryView.tsx` (error banner), updated library tests (`vi.mock("@/lib/api")` + `getBy`→`findBy`), a11y/responsive pass. Docs: `data-flow.md`, `routes.md`, `architecture.md`, `checklist.md`.

## Verification (end-to-end, after Phase 8)

1. `uv run pytest` green on SQLite (no Postgres needed).
2. `python app.py backend` → preflight brings up Postgres+Redis, creates schema, seeds Embergate, prints a pass report, serves `:8000`; spot-check `GET /api/storylines`.
3. `python app.py` (`:3000`) → preview tools confirm the Library loads from the API; create a character, reload, confirm it **persists**; with backend stopped, confirm the error banner instead of silent data loss.
4. `npm test && npm run typecheck` green; a11y/responsive pass recorded.
