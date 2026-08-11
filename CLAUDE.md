# Mytheca — Claude Code Entry Point

Mytheca is an AI-driven, multi-character roleplay chat engine (Next.js frontend + FastAPI multi-agent backend). This file **routes you to the right file** — check the tables below before grepping or globbing.

## Read First (always)

1. `docs/skills/global-project-rules/SKILL.md` — stack, environment, validation gate, git workflow, docs duties. **Read this before any change.**
2. `docs/checklist.md` — genuinely-open work.
3. The one canonical skill under `docs/skills/` matching your task.

`docs/` is the single source of truth. `.claude/skills/` only points back to it — never duplicate instructions there.

## Facts that override stale assumptions

These trip people up because older prose said otherwise. All verified 2026-08-04:

- **No authentication exists.** No `User` model, no auth routes, no sessions or tokens. Nothing is gated.
- **7 story-event types**, not 5: `narration` · `character_dialogue` · `character_action` · `internal_thought` · `state_update` · `branch_choices` · `character_status_change`.
- **Streaming is NDJSON in the turn POST response.** No SSE endpoint, no WebSocket for story events, no `message_start`/`message_delta`/`message_end` frames — delta streaming re-emits the *same* event `id`+`seq` with growing `text` and `done: false → true`.
- **Alembic is in use** (12 migrations), coexisting with `create_all` + an additive reconciler.
- **`director_agent.who_is_up` and `rerank` are dead code** — tests only. `planner_agent.next_beat` makes the real per-beat decision, and its reply also carries the beat's **register** (`light`/`neutral`/`tense`/`grave`) + `stakes`, which drive the character prompt's tail, voice-sample selection, and sampler.
- **The graph reaches the prompt via `graph_reader.relationship_context()`**, not `TurnContext.subgraph` (which is diagnostics-only).
- **`web/shared/contracts/` is empty.** The FE↔BE contract is hand-mirrored in `web/frontend/lib/events.ts` + `lib/types.ts`.
- **Frontend tests are co-located** (`Foo.tsx` → `Foo.test.tsx`). `utils/tests/frontend/` is empty.
- **Framer Motion, not GSAP.** No headless UI library, no TanStack, no Zod.

## Which skill for which task

| Task | Skill |
| --- | --- |
| Where a new file should live | `docs/skills/repository-structure/SKILL.md` |
| Routes, API contract, data flow | `docs/skills/website-architecture/SKILL.md` |
| Frontend UI / component / motion work | `docs/skills/ui-frontend/SKILL.md` |
| Accessibility / mobile pass | `docs/skills/accessibility-mobile/SKILL.md` |
| ADA compliance | `docs/skills/ada-compliance/SKILL.md` |
| Writing an implementation plan | `docs/skills/planner/SKILL.md` |

## Docs — go straight to the file

| Need | File |
| --- | --- |
| Purpose, domain model, stack, status | `docs/documentation.md` |
| Full repo tree + path ownership | `docs/structure.md` |
| Commands, env, ports, validation gate | `docs/workflow.md` |
| Open work | `docs/checklist.md` |
| Boundaries, data layer, decisions | `docs/architecture.md` |
| Frontend route map (8 real routes) | `docs/routes.md` |
| Component ownership | `docs/component-map.md` |
| Data origins + the turn/streaming path | `docs/data-flow.md` |
| Build/run/deploy + every env var | `docs/deployment.md` |
| Themes, tokens, UI states | `docs/design-system.md` |
| API + NDJSON event contract | `docs/api-contract.md` |
| Hybrid RAG (Qdrant/fastembed) | `docs/rag.md` |
| Story Graph (Neo4j) | `docs/story-graph-neo4j.md` |
| ComfyUI image generation | `docs/comfyui-image-generation.md` |
| Original product briefing | `docs/briefings/storyline-chat-briefing.md` |
| Locked visual reference mockups | `docs/CharacterFrontpage/` |
| Active feature plans | `docs/plans/<feature-name>.md` — 5 files; `ls docs/plans/` to find one |
| Shipped-feature plans (historical — **do not read while routing**) | `docs/plans/archive/` |
| **Research record** — experiments, claims, figures, findings | `docs/research/` — contract: `docs/research/AGENT_INSTRUCTIONS.md` |

## Backend — `web/backend/app/`

| Layer | Path | Files |
| --- | --- | --- |
| API routes (all mounted under `/api`) | `routes/` | `characters.py` `context_documents.py` `graph.py` `options.py` `play.py` (turn streaming) `rag.py` `scenarios.py` `settings.py` `stats.py` `storylines.py` |
| Turn loop / orchestration | `services/` | `turn_engine.py` (the loop) `assembler.py` (context) `retrieval_gate.py` `emission.py` `validator.py` `consistency.py` `presence.py` `events_store.py` `turn_writer.py` `session_export.py` `reflection.py` `relationships.py` `crud.py` `stats.py` `stat_guidance.py` `stat_render.py` `type_registry.py` `storyline_apply.py` `world_populate.py` (create-time cast + settings build) `settings_store.py` `llm.py` `llm_backend.py` `graph_reader.py` `graph_writer.py` `concurrency.py` `media.py` `media_cleanup.py` `portraits.py` `scene_art.py` `comfyui.py` |
| LLM agents | `agents/` | Turn loop: `planner_agent.py` (ReAct next-beat + register) `character_turn_agent.py` (think→speak) `narrator_agent.py` `intent_agent.py` `director_agent.py` (branch/POV suggestions; `who_is_up`+`rerank` are dead) `reflection_agent.py` `relationship_agent.py`. Authoring: `storyline_agent.py` `storyline_edit/` (`scope.py` `core.py` `editor.py` `creation.py`) `character_agent.py` `setting_agent.py` `scenario_agent.py` `triage_agent.py` `roster_agent.py` (the world-population roster). Shared: `_common.py` `prompt_registry.py` (8 overridable prompt keys) |
| Authored content | `content/` | `graph_registry.py` (6 node + 16 edge built-in types) + `stats/*.md` (`health` `patience` `suspicion` `trust`) |
| Hybrid RAG | `rag/` | `schema.py` `serializer.py` `tokens.py` `entries.py` `embedder.py` `store.py` `indexer.py` `retriever.py` `const.py` |
| Live turn state | `memory/` | `buffer.py` (Redis recent-turn buffer) `interior.py` |
| Event stream | `events/` | `envelope.py` (7 story events) `stream.py` (NDJSON + trace/error frames) |
| DB models (13 tables) | `models/` | `storyline.py` `character.py` `setting.py` `scenario.py` `event.py` `stat.py` (StatDefinition + CharacterStat) `session.py` `turn_trace.py` `context_document.py` (Doc + Link) `graph_type.py` `app_setting.py` |
| Pydantic schemas | `schemas/` | `base.py` + mirrors of `models/` + `play.py` `rag.py` `reasoning.py` `settings.py` `storyline_edit.py` |
| Config/clients | `core/` | `config.py` `db.py` `redis.py` `neo4j.py` `qdrant.py` `bootstrap.py` (preflight) `seed.py` `errors.py` `ids.py` |
| Migrations | `web/backend/alembic/` | `env.py` + `versions/` (12 migrations; non-additive changes only) |
| Docker | `web/backend/docker-compose.yml`, `docker/neo4j/` | Postgres · Redis · Neo4j · Qdrant, started by root `app.py` |

## Frontend — `web/frontend/`

| Layer | Path | Notes |
| --- | --- | --- |
| Routes (8) | `app/` | `page.tsx` (`/`) · `[storylineId]/` · `[storylineId]/[scenarioId]/` (story player) · `play/[scenarioId]/` (legacy redirect) · `storylines/new/` · `storylines/[id]/edit/` · `storylines/[id]/documents/` · `options/`. One root `layout.tsx`; no route handlers. |
| Feature modules | `features/` | `story-player/` (`StoryPlayerRoute` `StoryPlayerView` `useSceneData` `useScenePlay` `turn-stream.ts` `scene-data.ts`) · `library/` (`LibraryView` `LibraryColumns` `useLibraryState` `StorylineCreatorView` `useStorylineCreator` `storylineCreator.ts` `worldBuild.ts` `useStorylineAgent` `storylineAgent.ts` `entityDocs.ts` `editor.ts`) · `options/` (`OptionsView` `useOptionsSettings` `tabs/*`) · `documents/` (`DocumentsView` `useDocuments`) |
| Domain UI (48) | `components/feature/` | Columns: `CharacterColumn` `SettingColumn` `ScenarioColumn` `ColumnChrome` `LibraryTabs` · Cards: `CharacterCard` `SettingCard` `ScenarioCard` `ScenarioCarousel` · Modals: `CharacterModal` `SettingModal` `EntityModal` `SealModal` `PortraitModal` `SceneArtModal` `CharacterProfileModal` `BeginSceneModal` `StorylineDeleteModal` `PromptOverridesModal` `BuildWorldModal` · Story player: `TranscriptBeat` `SceneIntro` `SceneLoader` `Composer` `CastRail` `DirectorRail` `CharacterDossier` `ContextUsageDial` `PovSelect` `SceneConfigMenu` `ExportMenu` · Graph: `GraphView` `GraphCanvas` `GraphInspectorPanel` · Editing: `StatsEditor` `VoiceSamplesEditor` `ScenarioForm` `PromptOverridesEditor` · Panels: `TriagePanel` `StorylineAgentPanel` `TurnInspectorPanel` `ContextFilesPanel` `ContextBudgetMeter` `DocumentsTable` `SourceDocumentsPanel` `ProcessProgress` · Menus: `CreateMenu` `StorylineMenu` `OptionsMenu` |
| Primitives (17) | `components/ui/` | `Button` `Modal` `TextField` `TextArea` `Chip` `ToggleChip` `Tag` `MultiSelect` `IconButton` `CloseButton` `FieldLabel` `SectionHeader` `Eyebrow` `Monogram` `Toast` `QuotedText` `SceneControlSelect` |
| App chrome (6) | `components/layout/` | `AppShell` `AppHeader` `SceneHeader` `MotionProvider` `ThemeSwitcher` `ToastProvider` |
| Hooks (4) | `hooks/` | `use-event-stream.ts` (NDJSON consumer) `use-field-reveal.ts` `use-font-size.ts` `use-theme.tsx` |
| Helpers (14) | `lib/` | `api.ts` `types.ts` `events.ts` `theme.ts` `fonts.ts` `font-size.ts` `contextBudget.ts` `cardArt.ts` `graphColors.ts` `monogram.ts` `readDocs.ts` `seals.ts` `seed-data.ts` `cn.ts` |
| Styles | `styles/themes.css`, `app/globals.css` | Three themes + `--fs-*` scale; Tailwind v4 `@theme inline` mapping |

**Frontend tests are co-located** (`Foo.tsx` → `Foo.test.tsx`) — 84 files. `utils/tests/frontend/` is empty; ignore it.

## Backend tests — `utils/tests/backend/`

Five area folders: `api/` `agents/` `services/` `rag/` `data/`, plus a shared `conftest.py`. Add new tests to the matching folder as `test_<behavior>.py`. 784 cases pass today.

## Root-level essentials

| File | Purpose |
| --- | --- |
| `app.py` | Launches backend + frontend (`python app.py`), one side (`… backend`\|`frontend`), or stops both (`… stop`). Frees ports 3345/3346 first and owns Docker. |
| `pyproject.toml` / `.python-version` | uv-managed backend project, Python 3.13 |
| `.env.example` | Every env var, documented — copy to `.env` |
| `Makefile` | Research-record targets only (`new-experiment` `validate-research` `research-index` `figures`). Does **not** replace `app.py`. |
| `CONTRIBUTING.md` | Validation gate + how to run an experiment |
| `line_counter.py` | Standalone LOC utility, not part of the app |

## Fast command reference

Full detail: `docs/workflow.md`.

```bash
uv run python app.py backend      # backend dev server (preflight + uvicorn, port 3345)
uv run pytest                     # backend tests (in-memory SQLite, no Docker needed)
cd web/frontend && npm run dev    # frontend dev server (port 3346)
cd web/frontend && npm test       # frontend tests (Vitest)
cd web/frontend && npm run typecheck && npm run lint
uv run python utils/scripts/check_contrast.py   # WCAG-AA theme gate
make validate-research            # enforce the research record contract
make new-experiment SLUG=x        # scaffold an experiment folder
```

## Non-negotiable rules

- `uv` only for Python (never pip/poetry/conda); npm for the frontend.
- Update the relevant `docs/*.md` in the **same change** that alters behavior.
- Branch off `main`; commit per completed plan phase; no push or PR unless asked.
- Validation gate before calling anything done: `uv run pytest` + frontend tests, plus an accessibility/responsive pass for UI changes.

## Research record (mandatory)

- Any experiment, benchmark, baseline, ablation, or evaluation run MUST be
  recorded under `docs/research/experiments/` following
  `docs/research/AGENT_INSTRUCTIONS.md`.
- Never report a metric in chat or a commit message without also writing it to
  the corresponding `manifest.yaml` and `RESULTS.md`.
- Never hand-edit a figure. Never hardcode a number in a plotting script.
- Failed and abandoned runs are recorded, not deleted.
- If asked to "just quickly check" a number, still create the experiment folder.
- **Never aggregate over the surviving runs of a partially-failed experiment.**
  Survivors are not a random subsample; report per-run rows and no aggregate.
  `EXP-2026-08-001` is the worked example of getting this wrong and catching it.
