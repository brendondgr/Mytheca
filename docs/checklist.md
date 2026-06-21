# Velora — Checklist

## Initialization (Definition of Done)

### Intake
- [x] Project goal, runtime, deliverables, target users, supported tools, validation workflow known.
- [x] Web architecture decisions captured (`docs/architecture.md`, `docs/routes.md`, `docs/data-flow.md`, `docs/api-contract.md`, `docs/design-system.md`).
- [x] Product/domain model captured from `docs/briefings/storyline-chat-briefing.md` (Storyline / Character / Setting / Scenario + Story Event + Stat system; five event types) and reflected across docs.
- [x] Visual design system locked to the `docs/CharacterFrontpage/` reference (Cinzel / EB Garamond / IBM Plex Mono; Parchment / Ember / Slate themes) in `docs/design-system.md`.

### Canonical docs
- [x] `docs/` exists with documentation, structure, workflow, checklist, architecture, routes, component-map, data-flow, deployment, design-system, api-contract.
- [x] `docs/plans/` exists.
- [x] `docs/skills/` exists with `global-project-rules` + all selected skills.
- [x] `docs/skills/global-project-rules/SKILL.md` names the required reading.
- [x] Supporting skill files preserved (`structures/`, `ui/`, `SETUP.md`, `planner.md`).

### Agent pointers
- [x] Claude Code (`.claude/skills/`), OpenAI Codex (`.agents/skills/`), Cursor (`.cursor/rules/`) pointer files created.
- [x] Each pointer references `docs/skills/global-project-rules/SKILL.md` + its canonical skill.
- [x] No agent folder holds the only copy of instructions.

### Project structure
- [x] Required top-level directories exist (`web/frontend`, `web/backend`, `web/shared`, `utils` (with `utils/tests` + `utils/scripts`), `libs`, `docs`).
- [x] Web code is under `web/`; root `app.py` is the backend entrypoint.
- [x] `pyproject.toml`, `.python-version`, `.env.example` exist.
- [x] `README.md` points to canonical docs.

### Cleanup
- [x] Selected starter skill dirs migrated into `docs/skills/` and removed.
- [x] Unselected starter material removed.
- [x] Initialization helpers (`initialize.md`, `read-yaml.py`) removed after migration.
- [x] No duplicate competing sources of truth.

### Verification
- [x] Final tree inspected after cleanup.
- [x] Canonical docs and representative pointer files checked.
- [x] Pointer targets verified to exist.
- [ ] Validation commands run — **deferred**: app code not yet scaffolded, so `pytest`/frontend tests have nothing to run. Re-enable at first code phase.

## Follow-up Work (next steps)

### Scaffolding (next step after init)
- [ ] Scaffold the Next.js app in `web/frontend/` (`create-next-app`: TS, Tailwind, App Router) + add Framer Motion.
- [ ] Scaffold the FastAPI app in `web/backend/app/` and wire root `app.py` to it.
- [ ] Add backend deps via `uv add` (fastapi, uvicorn, pydantic, sqlalchemy/psycopg, redis, httpx, pytest, ruff, mypy) and run `uv sync`.
- [ ] Set up PostgreSQL + Redis connections in `app/core/`.
- [ ] Create initial DB models (users, storylines, characters, settings, scenarios, events, stat definitions, stat values) + migrations.
- [ ] Add YAML config + Markdown stat-guidance loaders in `app/core/` (`app/content/`).

### Core domain & event system (next after scaffolding)
- [ ] Lock the four core objects (Storyline / Character / Setting / Scenario) as Pydantic + shared-contract types.
- [ ] Implement the five-event NDJSON schema (`narration`, `character_dialogue`, `character_action`, `state_update`, `branch_choices`) + the validator (parse → validate → repair/retry).
- [ ] Stand up the NDJSON stream in full-event mode, then add delta streaming for visible messages.
- [ ] Build the stat system: storyline stat schema, per-character values, validator clamping, the Stats panel, and `state_update`-carried stat changes with reasons.
- [ ] Author guidance files for the first handful of stats and wire them into agent context.
- [ ] Extend stats to relationship/mood values (same machinery, relational target).

### Architecture decisions to finalize
- [ ] Auth mechanism (JWT vs. session cookie; provider) — currently "backend-owned, TBD".
- [ ] SSE vs. WebSocket for the event stream (or both) — define before building the story player.
- [ ] API base prefix and CORS origins.
- [ ] LLM provider interface shape (OpenAI + local).
- [ ] Stat lifecycle across scenarios (reset / persist / partial carry-over) and how hidden stats render.
- [ ] Deployment target (containerized vs. split hosting).

### Deferred capabilities (design seams only for now)
- [ ] Dice-based resolution (optional later layer: `check_request` → `roll_result` → `consequence` → `state_update`).
- [ ] Vector DB for semantic memory / cross-scenario character & setting memory.

### Quality gates to enforce once code exists
- [ ] pytest in `utils/tests/backend/`.
- [ ] Frontend component/route tests in `utils/tests/frontend/` (or co-located) — pick the runner (e.g. Vitest + Testing Library; Playwright for e2e).
- [ ] Accessibility + responsive pass per `accessibility-mobile` + `ada-compliance`.

## Retained / Removed Setup Files
- Removed: `initialize.md`, `read-yaml.py`, and the starter skill directories (`accessibility-mobile/`, `ada-compliance/`, `plan/`, `repo-structure/`, `ui-frontend/`, `website-architecture/`) — all migrated into `docs/skills/`.
- Retained: `.gitignore`, `.python-version` (runtime config).
