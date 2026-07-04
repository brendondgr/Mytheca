# Velora — Claude Code Entry Point

Velora is an AI-driven, multi-character roleplay chat engine (Next.js frontend + FastAPI multi-agent backend). This file exists to **route you directly to the right file** — check the tables below before grepping or globbing the repo.

## Read First (always)

1. `docs/skills/global-project-rules/SKILL.md` — stack, environment rules, validation gate, git workflow, docs-maintenance duties. **Read this before any change.**
2. `docs/checklist.md` — active work, open follow-ups.
3. The one canonical skill under `docs/skills/` matching your task (table below).

`docs/` is the single source of truth. `.claude/skills/` only points back to it — don't duplicate instructions there.

## Which skill for which task

| Task | Skill |
| --- | --- |
| Repo layout, where a new file should live | `docs/skills/repository-structure/SKILL.md` |
| Routes, API contract, data flow, design-quality gate | `docs/skills/website-architecture/SKILL.md` |
| Frontend UI/component/motion work | `docs/skills/ui-frontend/SKILL.md` |
| Accessibility / mobile pass | `docs/skills/accessibility-mobile/SKILL.md` |
| ADA compliance | `docs/skills/ada-compliance/SKILL.md` |
| Writing/refining an implementation plan | `docs/skills/planner/SKILL.md` |

## Docs — go straight to the file, don't search

| Need | File |
| --- | --- |
| Project purpose, domain model, tech stack | `docs/documentation.md` |
| Full repo tree + path ownership table | `docs/structure.md` |
| Commands, env vars, ports, validation gate | `docs/workflow.md` |
| Active work / open items | `docs/checklist.md` |
| Modes, auth, boundaries, architecture decisions | `docs/architecture.md` |
| Frontend route map | `docs/routes.md` |
| Component ownership map | `docs/component-map.md` |
| Data origins + streaming/event path | `docs/data-flow.md` |
| Build/run/deploy targets | `docs/deployment.md` |
| Visual tokens, themes, UI states | `docs/design-system.md` |
| API + NDJSON event contract | `docs/api-contract.md` |
| Hybrid RAG pipeline (Qdrant/fastembed) | `docs/rag.md` |
| Story Graph (Neo4j) substrate | `docs/story-graph-neo4j.md` |
| ComfyUI image generation | `docs/comfyui-image-generation.md` |
| Original product briefing (domain objects, event types) | `docs/briefings/storyline-chat-briefing.md` |
| Visual design reference (locked-in HTML mockups) | `docs/CharacterFrontpage/` |
| Feature plans / handoffs | `docs/plans/<feature-name>.md` — `ls docs/plans/` to find one by name |

## Backend — `web/backend/app/`

One file per concern; go straight to it instead of grepping the whole `app/` tree.

| Layer | Path | Files |
| --- | --- | --- |
| API routes | `routes/` | `characters.py` `storylines.py` `scenarios.py` `settings.py` `stats.py` `play.py` (turn streaming) `context_documents.py` `rag.py` `graph.py` `options.py` |
| Turn loop / orchestration | `services/` | `turn_engine.py` (POV loop+delta stream) `assembler.py` (context) `retrieval_gate.py` `emission.py` `validator.py` (stat clamp + presence) `presence.py` (scene-presence fold) `events_store.py` `turn_writer.py` `crud.py` `consistency.py` `reflection.py` `relationships.py` `type_registry.py` `stat_guidance.py` `stat_render.py` (current-band + {Character} substitution) `settings_store.py` `llm.py`/`llm_backend.py` `media.py`/`media_cleanup.py`/`portraits.py`/`scene_art.py`/`comfyui.py` `graph_reader.py`/`graph_writer.py` `concurrency.py` |
| LLM agents | `agents/` | `character_turn_agent.py` (think→speak) `director_agent.py` (who's-up+branches) `narrator_agent.py` (interstitials) — authoring: `storyline_agent.py` `character_agent.py` `setting_agent.py` `scenario_agent.py` `build_agent.py` `triage_agent.py` `extract_agent.py` `planner_agent.py` `intent_agent.py` `reflection_agent.py` `relationship_agent.py` `_common.py` (shared) |
| Story-Graph content | `content/` | `graph_registry.py` (type catalogue) + `stats/*.md` (per-stat guidance: `health.md` `patience.md` `suspicion.md` `trust.md`) |
| Hybrid RAG | `rag/` | `schema.py` (LoreEntry) `serializer.py` `tokens.py` `entries.py` `embedder.py` `store.py` `indexer.py` `retriever.py` `const.py` |
| Live turn state | `memory/` | `buffer.py` (Redis recent-turn buffer) `interior.py` |
| Event stream | `events/` | `envelope.py` `stream.py` (build_event/to_ndjson_line) |
| DB models | `models/` | `storyline.py` `character.py` `setting.py` `scenario.py` `event.py` `stat.py` `session.py` `context_document.py` `graph_type.py` `app_setting.py` |
| Pydantic schemas | `schemas/` | mirrors `models/` + `build.py` `play.py` `rag.py` `reasoning.py` `settings.py` |
| Config/clients | `core/` | `config.py` `db.py` `redis.py` `neo4j.py` `qdrant.py` `bootstrap.py` (preflight) `seed.py` `errors.py` `ids.py` |
| Migrations | `web/backend/alembic/` | `env.py` + `versions/` (non-additive schema changes only) |
| Docker | `web/backend/docker-compose.yml`, `web/backend/docker/neo4j/` | Postgres/Redis/Neo4j/Qdrant, started by root `app.py` |

## Frontend — `web/frontend/`

| Layer | Path | Notes |
| --- | --- | --- |
| Routes | `app/` | `page.tsx` (home/library) · `storylines/new/`, `storylines/[id]/edit/` · `[storylineId]/`, `[storylineId]/[scenarioId]/` (story player) · `play/[scenarioId]/` · `options/` |
| Feature modules (route logic + state) | `features/` | `story-player/` (`StoryPlayerRoute.tsx`, `StoryPlayerView.tsx`, `useScenePlay.ts`, `turn-stream.ts`, `scene-data.ts`) · `library/` (`LibraryView.tsx`, `LibraryColumns.tsx`, `useLibraryState.ts`, `storylineCreator.ts`, `entityDocs.ts`) · `options/` (`OptionsView.tsx`, `useOptionsSettings.ts`, `tabs/*`) |
| Domain UI components | `components/feature/` | Columns: `CharacterColumn.tsx` `SettingColumn.tsx` `ScenarioColumn.tsx` · Cards: `CharacterCard.tsx` `SettingCard.tsx` `ScenarioCard.tsx` · Modals: `CharacterModal.tsx` `SettingModal.tsx` `EntityModal.tsx` `SealModal.tsx` `PortraitModal.tsx` `SceneArtModal.tsx` `CharacterProfileModal.tsx` `BeginSceneModal.tsx` `StorylineDeleteModal.tsx` · Story player: `TranscriptBeat.tsx` `SceneIntro.tsx` `SceneLoader.tsx` `Composer.tsx` `CastRail.tsx` `DirectorRail.tsx` `CharacterDossier.tsx` · Editing: `StatsEditor.tsx` `VoiceSamplesEditor.tsx` `ScenarioForm.tsx` · Panels: `TriagePanel.tsx` `WorldBuildPanel.tsx` `TurnInspectorPanel.tsx` `ContextFilesPanel.tsx` `ContextBudgetMeter.tsx` · Misc: `LibraryTabs.tsx` `CreateMenu.tsx` `StorylineMenu.tsx` `ColumnChrome.tsx` `ProcessProgress.tsx` `OptionsMenu.tsx` `ScenarioCarousel.tsx` |
| Reusable primitives | `components/ui/` | `Button.tsx` `Modal.tsx` `TextField.tsx` `TextArea.tsx` `Chip.tsx` `ToggleChip.tsx` `Tag.tsx` `MultiSelect.tsx` `IconButton.tsx` `CloseButton.tsx` `FieldLabel.tsx` `SectionHeader.tsx` `Eyebrow.tsx` `Monogram.tsx` `Toast.tsx` |
| App chrome | `components/layout/` | `AppShell.tsx` `AppHeader.tsx` `SceneHeader.tsx` `MotionProvider.tsx` `ThemeSwitcher.tsx` `ToastProvider.tsx` |
| Shared hooks | `hooks/` | `use-event-stream.ts` (NDJSON consumer) `use-field-reveal.ts` `use-font-size.ts` `use-theme.tsx` |
| Helpers / API client | `lib/` | `api.ts` `types.ts` `events.ts` `theme.ts` `fonts.ts` `font-size.ts` `contextBudget.ts` `cardArt.ts` `monogram.ts` `readDocs.ts` `seals.ts` `cn.ts` `seed-data.ts` |
| Global styles | `styles/`, `app/globals.css` | Tailwind v4 `@theme` tokens |
| Shared FE↔BE contracts | `web/shared/contracts/` | currently empty (`.gitkeep`) |

**Frontend tests are co-located** next to what they test (`Foo.tsx` → `Foo.test.tsx`), *not* under `utils/tests/frontend/` (that dir is effectively empty — ignore it despite what older docs imply).

## Backend tests — `utils/tests/backend/`

Grouped by area: `api/` `agents/` `services/` `rag/` `data/`, plus shared `conftest.py`. Add new tests under the matching subfolder as `test_<behavior>.py`.

## Root-level essentials

| File | Purpose |
| --- | --- |
| `app.py` | Launches backend+frontend together (`python app.py`), or one side (`... frontend`\|`backend`), or stops both (`... stop`). Owns Docker (Postgres/Redis/Neo4j/Qdrant). |
| `pyproject.toml` / `.python-version` | uv-managed backend project, Python 3.13 |
| `.env.example` | Documented env vars — copy to `.env` |

## Fast command reference

Full detail: `docs/workflow.md`.

```bash
uv run python app.py backend      # backend dev server (preflight + uvicorn, port 3345)
uv run pytest                     # backend tests (in-memory SQLite, no Docker needed)
cd web/frontend && npm run dev    # frontend dev server (port 3346)
cd web/frontend && npm test       # frontend tests (Vitest)
cd web/frontend && npm run typecheck && npm run lint
```

## Non-negotiable rules (full detail in `docs/skills/global-project-rules/SKILL.md`)

- `uv` only for Python (never pip/poetry/conda); npm for frontend.
- Update the relevant `docs/*.md` in the **same change** that alters behavior (see table above for which file owns what).
- Branch off `main`; commit per completed plan phase; no push/PR unless asked.
- Validation gate before calling anything done: `uv run pytest` + frontend tests, plus an accessibility/responsive pass for UI changes.
