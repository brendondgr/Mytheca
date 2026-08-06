# Plan: Four End-of-Day Features

## 1. Introduction

This plan completes four independent, already-scaffolded-but-unfinished seams in Mytheca. Each is self-contained and lands as its own phase set with commit-per-phase discipline (Mytheca git workflow). The four features:

1. **Stat guidance Markdown files + loader** — `StatDefinition.guidance` stores a path (`stats/health.md`) and the seed populates four of them (health, suspicion, trust, patience), but the `.md` files don't exist and no agent reads them. We author the files, add a content-resolving loader, and inject the guidance into the agents that describe the stat schema to the LLM.
2. **LLM backend detector in Options UI** — `GET /api/options/llm/backend` already returns the detected engine (`vllm`/`llamacpp`/`unknown`) + the reasoning-budget map, but there is no frontend client and nothing surfaces it. We add the API client and display it read-only in the About tab.
3. **Alembic migrations** — there is no `alembic/` directory; schema management is `create_all` + an additive-only column reconciler that cannot do non-additive changes. We introduce Alembic as the versioned-migration framework, coexisting with the existing flow (tests keep their direct `create_all`/`drop_all` SQLite path untouched).
4. **Orphaned media cleanup** — cancelled portrait/scene-art drafts and deleted entities leave unreferenced WebPs under `MEDIA_DIR`. We add a cleanup service + an Options-namespaced endpoint that cross-references on-disk `*.webp` against `Character.portrait` / `Setting.image`, with an age grace period so in-flight drafts are never deleted, plus a small Options UI control.

Work happens in the `worktree-eod-four-features` worktree (branched from local `main` @ `8b1e444`) and merges back to `main` at the end.

---

## 2. Gaps & Unanswered Questions

- **Where do guidance files live + how are paths resolved?** (Assumption) The guidance paths are relative (`stats/health.md`). Resolve them against a new `Settings.content_dir` property pointing at the `app/content` package directory, so the files live at `web/backend/app/content/stats/*.md`. The loader guards against path traversal (rejects `..`/absolute) and caches reads.
- **Which agents consume guidance?** (Assumption) The two that describe the stat schema to the model: `character_agent.propose_starting_stats` (primary consumer) and `build_agent` (world-build blueprint). The loader is injected into the schema text those build for the LLM. No new agent is created.
- **Where to surface the detected backend in the UI?** (Assumption) The **About** tab, which is already a read-only diagnostics list — the detected engine + budget ladder are diagnostics, not editable settings. Fetched on mount via the new client; failure degrades gracefully (row shows "unavailable").
- **Does Alembic replace `create_all`?** (Assumption) **No — coexist.** `create_all` + the additive reconciler stay (they keep the SQLite test path and fresh dev DBs working unchanged). Alembic is layered on as the *version-tracking + non-additive migration* path for real (non-SQLite) databases: on preflight, a real DB with no `alembic_version` table is **stamped** to the baseline (adopted without re-creating), and an already-versioned DB is **upgraded to head**. Tests do not run preflight, so their flow is untouched. This mirrors Mytheca's "graceful/best-effort" posture (like Neo4j): an Alembic failure logs into the preflight report but never blocks startup.
- **What media references must cleanup respect?** (Confirmed by exploration) Only `Character.portrait` and `Setting.image` store `/media/...` URLs; storyline seals are shape+color, not files. Cleanup scans `portraits_dir` + `scenes_dir` only.
- **How are in-flight drafts protected?** (Assumption) A draft generates a WebP *before* the entity is saved, so by the "not referenced in DB" definition it is an orphan. To avoid deleting a file a user is mid-draft on, cleanup only deletes files older than a grace period (`min_age_hours`, default 24). A dry-run report lists candidates regardless of age.
- **Frontend cleanup control placement?** (Assumption) A small maintenance control in the About tab (scan → shows count → delete with confirmation). The endpoint is the deliverable; the UI is a thin convenience.

No gaps require human intervention — all assumptions follow existing project patterns.

---

## 3. Hierarchical Step-by-Step Instructions

### Feature 1 — Stat guidance Markdown files + loader

#### Phase 1.1 — Content dir, loader, and authored Markdown files
- **Locations:**
  - `web/backend/app/core/config.py` — add a `content_dir` property (`Path(__file__).resolve().parents[1] / "content"`, i.e. `app/content`).
  - `web/backend/app/services/stat_guidance.py` (new) — `load_guidance(path: str | None) -> str | None` (resolve relative to `content_dir`, reject traversal/absolute paths, read UTF-8, LRU-cache) and `guidance_for(definition) -> str | None`.
  - `web/backend/app/content/stats/health.md`, `suspicion.md`, `trust.md`, `patience.md` (new) — human-readable guidance authored to match the seeded ranges/bands (e.g. Health 0–100 with the four bands; Suspicion 0–10; Trust −5–5; Patience 0–10).
  - `web/backend/app/content/__init__.py` — update the docstring (the "later, …per-stat Markdown guidance" note now ships).
  - `utils/tests/backend/services/test_stat_guidance.py` (new) — loads each seeded file, asserts non-empty; asserts unknown/`None` path → `None`; asserts traversal (`../config.py`, absolute path) → `None` (security).
- **Rationale:** the files and a safe resolver must exist before any agent can inject them; the loader is the single source of truth for path→text resolution.
- **Action:** Run `uv run pytest utils/tests/backend/services/test_stat_guidance.py` + full backend suite; `ruff` + `mypy`. Once green, commit: `[EOD Stat Guidance] (1/2) Complete: content_dir + stat_guidance loader + authored health/suspicion/trust/patience Markdown.`

#### Phase 1.2 — Inject guidance into agents + docs
- **Locations:**
  - `web/backend/app/agents/character_agent.py` — in `propose_starting_stats`, append each definition's loaded guidance (truncated/bounded) to the per-stat schema text it sends the LLM, via `stat_guidance.guidance_for`.
  - `web/backend/app/agents/build_agent.py` — where the blueprint prompt describes/uses the stat schema, fold in available guidance the same way (bounded so the context budget stays sane).
  - `utils/tests/backend/agents/test_character_agent.py` (+ `test_build_agent.py` if present) — assert that when a definition has guidance, the loaded text appears in the prompt sent to the mocked LLM (offline `httpx.MockTransport`).
  - `docs/documentation.md` (stat-guidance status: files + loader landed), `docs/structure.md` (`content/stats/`, `services/stat_guidance.py`), `docs/checklist.md` (mark done).
- **Rationale:** injection is the payoff — guidance only matters once it reaches the model; tests must prove it actually reaches the prompt.
- **Action:** Run `uv run pytest utils/tests/backend/agents/` + full backend suite; `ruff` + `mypy`. Once green, commit: `[EOD Stat Guidance] (2/2) Complete: inject stat guidance into character/build agents + docs.`

---

### Feature 2 — LLM backend detector in Options UI

#### Phase 2.1 — API client + About-tab surface
- **Locations:**
  - `web/frontend/lib/api.ts` — add `LlmBackendInfo` type (`{ backend: string; budgets: Record<string, number> }`) and `getLlmBackend = () => request<LlmBackendInfo>("/options/llm/backend")`.
  - `web/frontend/features/options/tabs/AboutTab.tsx` — fetch `getLlmBackend()` on mount (local `useEffect`/state; graceful "unavailable" on error), render a row for the detected engine and a compact budget-ladder list (low→max). Keep it read-only.
  - `web/frontend/test/api-mock.ts` — add a `getLlmBackend` mock.
  - `web/frontend/features/options/tabs/AboutTab.test.tsx` (new, or extend existing About test) — renders the detected engine + budget rows from the mock; asserts graceful fallback when the call rejects.
- **Rationale:** the backend already returns the data; this is purely the missing read path + display. About is the established read-only diagnostics surface.
- **Action:** Run `npm run typecheck`, `npm test` (AboutTab + api), `npm run lint`; accessibility/responsive pass (semantic `dl` rows, contrast, 320/375/768/1024). Once green, commit: `[EOD LLM Backend UI] (1/2) Complete: getLlmBackend client + About-tab detected-engine/budget display + tests.`

#### Phase 2.2 — Docs
- **Locations:** `docs/api-contract.md` (note the endpoint is now surfaced in About), `docs/component-map.md` (AboutTab shows LLM backend diagnostics), `docs/documentation.md` (status), `docs/checklist.md` (mark done).
- **Rationale:** docs track behavior in the same change (definition of done).
- **Action:** Re-run `npm run typecheck` + `npm test`. Once green, commit: `[EOD LLM Backend UI] (2/2) Complete: docs updated for surfaced LLM backend diagnostics.`

---

### Feature 3 — Alembic migrations

#### Phase 3.1 — Dependency, scaffold, env wiring, baseline migration
- **Locations:**
  - `pyproject.toml` / `uv.lock` — `uv add alembic`.
  - `web/backend/alembic.ini` (new) — minimal config; script location `web/backend/alembic`; URL is overridden at runtime from settings (no hardcoded secret).
  - `web/backend/alembic/env.py` (new) — import `app.models` so every table registers, set `target_metadata = app.core.db.Base.metadata`, pull the URL from `app.core.config.get_settings().database_url`, support online + offline modes, and use `render_as_batch=True` for SQLite compatibility.
  - `web/backend/alembic/versions/<rev>_baseline.py` (new) — autogenerated baseline capturing the **full current schema** (all 11 tables + constraints, incl. the nullable `graph_type_definitions.storyline_id` unique constraint).
  - `utils/tests/backend/data/test_alembic.py` (new) — (a) `alembic upgrade head` on a temp SQLite DB builds the schema; (b) autogenerate against the upgraded DB produces an **empty** diff (proves the baseline matches `Base.metadata` exactly — the key correctness guarantee).
- **Rationale:** the framework + a verified-complete baseline must exist before preflight can stamp/upgrade against it; the empty-diff test is what proves the baseline is trustworthy.
- **Action:** Run `uv run pytest utils/tests/backend/data/test_alembic.py` + full backend suite; `ruff` + `mypy`. Once green, commit: `[EOD Alembic] (1/3) Complete: alembic dependency + env wired to Base.metadata/settings + verified baseline migration.`

#### Phase 3.2 — Preflight integration (coexist, best-effort, SQLite-safe)
- **Locations:**
  - `web/backend/app/core/bootstrap.py` — after `create_all` + reconcile, on a **non-SQLite** DB: if no `alembic_version` table → `command.stamp(cfg, "head")` (adopt existing schema); else → `command.upgrade(cfg, "head")` (apply pending migrations). Wrap best-effort (log + add a `migrations` line to `PreflightReport`; never raise). A small helper builds the `alembic.config.Config` pointing at `web/backend/alembic.ini` with the runtime URL.
  - `utils/tests/backend/data/test_bootstrap.py` — assert SQLite preflight skips Alembic cleanly (still idempotent, report still has the existing checks + the new `migrations` line marked skipped/ok).
- **Rationale:** integrating at preflight makes migrations actually run in real deployments while the SQLite skip keeps the entire test suite and fresh dev DBs working exactly as today.
- **Action:** Run `uv run pytest utils/tests/backend/data/` + full backend suite; `ruff` + `mypy`. Once green, commit: `[EOD Alembic] (2/3) Complete: best-effort Alembic stamp/upgrade in preflight, SQLite-skipped, reported.`

#### Phase 3.3 — Docs + final validation
- **Locations:** `docs/workflow.md` (Alembic commands: `uv run alembic revision --autogenerate -m`, `uv run alembic upgrade head`, how the runtime URL is supplied), `docs/structure.md` (`web/backend/alembic/`), `docs/documentation.md` (status: Alembic is the migration path; reconciler retained for additive/dev), `docs/deployment.md` (migrations on deploy), `docs/checklist.md` (mark done).
- **Rationale:** a migration framework is only usable if the commands and the coexistence model are documented.
- **Action:** Re-run full backend suite. Once green, commit: `[EOD Alembic] (3/3) Complete: docs for Alembic workflow + coexistence with create_all/reconciler.`

---

### Feature 4 — Orphaned media cleanup

#### Phase 4.1 — Backend cleanup service + endpoint
- **Locations:**
  - `web/backend/app/services/media_cleanup.py` (new) — `scan_orphans(db, *, min_age_hours) -> report` (enumerate `*.webp` in `portraits_dir` + `scenes_dir`; collect referenced basenames from `Character.portrait` + `Setting.image` via `rsplit("/", 1)[-1]`; orphan = on disk, unreferenced; flag whether each orphan is older than the grace period) and `delete_orphans(db, *, min_age_hours) -> report` (delete only grace-period-expired orphans; return counts + freed bytes).
  - `web/backend/app/schemas/settings.py` — `MediaOrphansResponse` (counts, per-dir breakdown, total bytes, eligible-for-delete count) and `MediaCleanupResponse`.
  - `web/backend/app/routes/options.py` — `GET /options/media/orphans` (dry-run report) and `POST /options/media/cleanup` (delete eligible; accepts optional `minAgeHours`). Declared with the other options routes.
  - `utils/tests/backend/services/test_media_cleanup.py` (new) — using `tmp_path` redirected dirs + seeded Character/Setting rows: referenced files survive, unreferenced expired files are reported/deleted, unreferenced **recent** files are protected by the grace period, and the route returns the expected shape. All offline (no ComfyUI).
- **Rationale:** the service is the actual deliverable ("no endpoint or utility"); the grace period is the safety mechanism that makes deletion safe to expose.
- **Action:** Run `uv run pytest utils/tests/backend/services/test_media_cleanup.py` + full backend suite; `ruff` + `mypy`. Once green, commit: `[EOD Media Cleanup] (1/3) Complete: media_cleanup service (scan/delete with age grace) + options endpoints + tests.`

#### Phase 4.2 — Frontend client + Options control
- **Locations:**
  - `web/frontend/lib/api.ts` — `getMediaOrphans()` and `cleanupMediaOrphans(minAgeHours?)` clients + result types.
  - `web/frontend/features/options/tabs/AboutTab.tsx` (or a small `MaintenanceTab`/section) — a "Scan for orphaned media" control showing the count + freed-bytes estimate, and a "Delete" action gated behind a confirmation. Loading/disabled states; results announced (a11y live region).
  - `web/frontend/test/api-mock.ts` + `AboutTab.test.tsx` — mock both clients; test scan→count and delete→confirmation flow.
- **Rationale:** a thin, safe UI makes the maintenance task reachable without curl; confirmation + live-region keep it accessible and non-destructive-by-accident.
- **Action:** Run `npm run typecheck`, `npm test`, `npm run lint`; accessibility/responsive pass (keyboard, focus, confirmation, live region, 320/375/768/1024). Once green, commit: `[EOD Media Cleanup] (2/3) Complete: media-orphans API client + Options scan/delete control + tests.`

#### Phase 4.3 — Docs + final validation
- **Locations:** `docs/api-contract.md` (new endpoints + shapes + grace-period semantics), `docs/data-flow.md` (cleanup flow), `docs/documentation.md` (status), `docs/structure.md` (`services/media_cleanup.py`), `docs/checklist.md` (mark done).
- **Rationale:** endpoints + behavior must be documented to be the source of truth.
- **Action:** Re-run full backend + frontend suites for a clean end-to-end gate. Once green, commit: `[EOD Media Cleanup] (3/3) Complete: docs for orphaned-media cleanup endpoints + flow.`

---

### Final — Merge to main
- Re-run the full backend (`uv run pytest`) and frontend (`npm test`, `npm run typecheck`, `npm run lint`, `npm run build`) suites once more from the worktree.
- Merge `worktree-eod-four-features` into `main` (no push), resolving any conflicts, and confirm the suites stay green on `main`.

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `content_dir` | Settings property resolving the content package | `web/backend/app/core/config.py` |
| Stat-guidance loader | Path-safe, cached Markdown resolver | `web/backend/app/services/stat_guidance.py` |
| Guidance Markdown | health / suspicion / trust / patience | `web/backend/app/content/stats/*.md` |
| Agent injection | Guidance folded into stat-schema prompts | `web/backend/app/agents/character_agent.py`, `build_agent.py` |
| Guidance tests | Loader + injection (offline) | `utils/tests/backend/services/test_stat_guidance.py`, `agents/test_character_agent.py` |
| LLM-backend client | `getLlmBackend()` + type | `web/frontend/lib/api.ts` |
| Backend diagnostics UI | Detected engine + budget ladder in About | `web/frontend/features/options/tabs/AboutTab.tsx` |
| Alembic scaffold | `alembic.ini` + `env.py` wired to Base/settings | `web/backend/alembic.ini`, `web/backend/alembic/env.py` |
| Baseline migration | Full current schema, drift-verified | `web/backend/alembic/versions/*_baseline.py` |
| Preflight integration | Best-effort stamp/upgrade, SQLite-skipped | `web/backend/app/core/bootstrap.py` |
| Alembic tests | Upgrade builds schema + empty-diff drift check | `utils/tests/backend/data/test_alembic.py` |
| Media-cleanup service | Scan/delete orphans with age grace | `web/backend/app/services/media_cleanup.py` |
| Cleanup endpoints | `GET /options/media/orphans`, `POST /options/media/cleanup` | `web/backend/app/routes/options.py` |
| Cleanup UI | Scan/delete control with confirmation | `web/frontend/features/options/tabs/AboutTab.tsx` |
| Cleanup tests | Service + route (offline, grace-period) | `utils/tests/backend/services/test_media_cleanup.py` |
| Docs | api-contract, data-flow, documentation, structure, workflow, deployment, component-map, checklist | `docs/` |
