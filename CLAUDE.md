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
- **9 story-event types**: `narration` · `character_dialogue` · `character_action` · `internal_thought` · `state_update` · `branch_choices` · `character_status_change` · `scene_image` (the player's in-narrative picture) · `cast_request` (the scene **asking** for an absent character — never an arrival; the AI has no way to bring anyone in, and presence moves only when the player answers).
- **Streaming is NDJSON in the turn POST response.** No SSE endpoint, no WebSocket for story events, no `message_start`/`message_delta`/`message_end` frames — delta streaming re-emits the *same* event `id`+`seq` with an **incremental** `text` chunk and `done: false`, and the final frame carries `done: true` with an **empty** `text`. Accumulate by `id`; the persisted row holds the full text. Reading the text off the `done` frame alone gets you `""` for every streamed beat.
- **Alembic is in use** (17 migrations), coexisting with `create_all` + an additive reconciler.
- **The player's non-POV mode is the *Playwright*, not the Narrator** (renamed 2026-08-24). One word named two opposite things — the AI voice writing third-person prose *inside* the scene, and the player standing outside it giving instructions — and that overload was the direct cause of a point-of-view defect: a `player` beat rendered as `You:` in both transcripts, so the cast dutifully addressed a person who is not in the room (9 of 10 beats in a live baseline; the narrator wrote *"he reaches out to grab your wrist"*). A `player` beat now renders as **`Direction:`**, unconditionally — under POV the line is stored as the character's own beat instead, so the role already carries the answer. **"Narrator" now means only the AI narrator** (`narrator_agent`, `NARRATOR_SYSTEM`, the `narration` event, `role="narrator"`, `NarratorCard`). `TurnContext.player_embodied` is the one flag every renderer and prompt reads; the second-person rule rides in the character prompt's recency **tail**, not the operator-overridable output contract, so a customised prompt cannot silently lose point of view.
- **Beat length and beats-per-message are adaptive — no number reaches the prompt.** The three-tier `beatLength` control and the `maxTurns` cap are **gone** (2026-08-24), along with the four scene presets, which were defined entirely in terms of them (`GET /options/scene-presets` returns `[]`). The tiers worked exactly as instructed, which was the defect: beats clustered at 3–5 paragraphs regardless of the moment. Never reintroduce a count — and never a **word** count, which EXP-2026-08-007 measured moving the average the *wrong* way. The only ceilings left are runaway backstops: `TURN_MAX_BEATS` (24, floored at `2 × cast + 6`) and one 2048-token prose allowance. The `Scenario` columns survive but are **unread**; old clients sending the fields are ignored, not 422'd.
- **`utils/scripts/scene_smoke.py` is how you check prose changes.** It builds a throwaway world, plays it through the real engine against the real model, prints every beat with its speaker and paragraph count, and scores each against the point-of-view rules — importing the checks from `services/emission` so the harness and the engine's guards cannot disagree. Run it after any prompt or turn-loop change. It is **not** an experiment (n=1, no arms, recorded nowhere); anything comparative belongs in `docs/research/experiments/`.
- **`director_agent.who_is_up` and `rerank` are dead code** — tests only. `planner_agent.plan_beats` makes the real decision (up to `TURN_PLANNER_LOOKAHEAD` beats per call; `next_beat` is its one-beat wrapper), and its reply also carries each beat's **register** (`light`/`neutral`/`tense`/`grave`) + `stakes`, which drive the character prompt's tail, voice-sample selection, and sampler. **It also decides when the turn ends** — that used to be `maxTurns`' job, and the first run without the cap produced 16 beats on one message because the planner had never had to. Its `end` rule is now explicit and its hand-the-floor-around rule is scoped to order rather than length; that fix is **unmeasured** (`docs/checklist.md`).
- **The graph reaches the prompt via `graph_reader.relationship_context()`**, not `TurnContext.subgraph` (which is diagnostics-only).
- **`web/shared/contracts/` is empty.** The FE↔BE contract is hand-mirrored in `web/frontend/lib/events.ts` + `lib/types.ts`.
- **Frontend tests are co-located** (`Foo.tsx` → `Foo.test.tsx`). `utils/tests/frontend/` is empty.
- **Framer Motion, not GSAP.** No headless UI library, no TanStack, no Zod.
- **The rails are no longer `lg`-only.** Below `lg`, `CastRail`/`DirectorRail`/`CharacterDossier` open as `Drawer` bottom sheets from `SceneRailBar` (above the composer), mounting the *same* `…Content` components with the *same* prop objects — so there is no reduced mobile copy to keep in sync. Below `sm` the scene header collapses into `SceneMenu`, which drills down in place for a panel-owning item rather than nesting a popover.
- **The three type families are self-hosted** (`app/fonts/`, `next/font/local`). `next build` therefore runs with no network — it could not before, which is why this repo had no production bundle and no Core Web Vitals number until `EXP-2026-08-012`.
- **Image generation is no longer watercolor-only.** Three art styles (`painted` — the default and the old look · `anime` · `photoreal`) live in `content/art_styles.py` and reach **every** image surface: character portraits, setting art, scenario art, the in-play scene image, and the "New Storyline" world build. A style sets the prompt-writing agent's wording *and* whether the workflow's LoRA node (`72`) is patched or **bypassed** — `anime`/`photoreal` ship LoRA-less because none is installed, editable per style in Options. `settings_store.resolve_art_style` is the one answer to "what look, with which LoRA?"; unknown ids fall back rather than raise.
- **`sr-only` is `position: fixed`**, overridden unlayered in `app/globals.css`. Tailwind's `absolute` default escapes `overflow: hidden` and inflates the *root* scroller (6212px, measured). Use a bare rule, never `@utility sr-only` — that merges with the core utility and the offline and Turbopack pipelines order the merge differently.

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
| Motion / loading / responsiveness contract for new UI | `docs/frontend-polish-spec.md` |
| API + NDJSON event contract | `docs/api-contract.md` |
| Hybrid RAG (Qdrant/fastembed) | `docs/rag.md` |
| Story Graph (Neo4j) | `docs/story-graph-neo4j.md` |
| ComfyUI image generation | `docs/comfyui-image-generation.md` |
| Original product briefing | `docs/briefings/storyline-chat-briefing.md` |
| Locked visual reference mockups | `docs/CharacterFrontpage/` |
| Active feature plans | `docs/plans/<feature-name>.md` — 29 files; `ls docs/plans/` to find one. The five-plan play-experience program is indexed by `docs/plans/play-experience-program.md` |
| Shipped-feature plans (historical — **do not read while routing**) | `docs/plans/archive/` |
| **Research record** — experiments, claims, figures, findings | `docs/research/` — contract: `docs/research/AGENT_INSTRUCTIONS.md` |

## Backend — `web/backend/app/`

| Layer | Path | Files |
| --- | --- | --- |
| API routes (all mounted under `/api`) | `routes/` | `characters.py` `context_documents.py` `graph.py` `options.py` `play.py` (turn streaming) `rag.py` `scenarios.py` `settings.py` `stats.py` `storylines.py` |
| Turn loop / orchestration | `services/` | **The turn loop, decomposed** — `turn_engine.py` is the **orchestrator only** (it defines exactly `validate_turn_inputs` + `run_turn`) and calls: `turn_setup.py` (`prepare_turn` — everything before the first beat) `beat_runner.py` (produce one decided beat) `beat_stream.py` (emission → delta-streamed events, the per-beat stops) `turn_effects.py` (stat / presence / relationship consequences) `turn_emit.py` (`Emitter` `LiveSegment` `Tracer`) `direction_runtime.py` (what the direction still owes mid-turn; `attempted` → `confirm`) `direction_check.py` (did the prose actually reach it — a lexical coverage check, no LLM call) `context_budget.py` (the one owner of the model's context window and the block-quantised transcript depth) `history_compaction.py` (what falls out of the window becomes a rolling per-session summary; invalidated on rewind/edit/re-roll) `turn_finalize.py` (suggestions → graph write → reflection → recency) `session_state.py` (the one owner of history mutation — truncate, copy, replay, rebuild) `session_stats.py` (session-scoped stat values) `beat_rerun.py` (re-roll a beat or a turn, keeping takes). Then `assembler.py` (context) `retrieval_gate.py` `emission.py` `validator.py` `consistency.py` `presence.py` `events_store.py` `turn_writer.py` `session_export.py` `reflection.py` `relationships.py` `crud.py` `stats.py` `stat_guidance.py` `stat_render.py` `type_registry.py` `storyline_apply.py` `world_populate.py` (create-time cast + settings build, from the author's classified docs) `world_populate_runs.py` (background runs + resumable frame log) `settings_store.py` `llm.py` `llm_backend.py` `graph_reader.py` `graph_writer.py` `concurrency.py` `media.py` `media_cleanup.py` `portraits.py` `scene_art.py` `scene_moment.py` (in-play scene images) `comfyui.py` |
| LLM agents | `agents/` | Turn loop: `planner_agent.py` (ReAct beat plan + register) `character_turn_agent.py` (think→speak) `narrator_agent.py` `intent_agent.py` `direction_agent.py` (the player's direction → outcomes the turn owes + the budget packer) `director_agent.py` (branch/POV suggestions; `who_is_up`+`rerank` are dead) `reflection_agent.py` `relationship_agent.py`. Authoring: `storyline_agent.py` `storyline_edit/` (`scope.py` `core.py` `editor.py` `creation.py`) `character_agent.py` `setting_agent.py` `scenario_agent.py` `triage_agent.py` `roster_agent.py` (invented roster) `extract_agent.py` (the author's docs → named subjects). In-play art: `moment_agent.py` (the scene → an appearance-first image prompt). Memory: `recap_agent.py` (dropped beats → the scene's rolling summary). Composer: `ghostwriter_agent.py` (the player's stated intent → their own line, drafted into the composer and never persisted). Shared: `_common.py` `prompt_registry.py` (10 overridable prompt keys) |
| Authored content | `content/` | `graph_registry.py` (6 node + 16 edge built-in types) · `art_styles.py` (3 image looks: `painted` `anime` `photoreal`) + `stats/*.md` (`health` `patience` `suspicion` `trust`) |
| Hybrid RAG | `rag/` | `schema.py` `serializer.py` `tokens.py` `entries.py` `embedder.py` `store.py` `indexer.py` `retriever.py` `const.py` |
| Live turn state | `memory/` | `buffer.py` (Redis recent-turn buffer) `interior.py` |
| Event stream | `events/` | `envelope.py` (9 story events) `stream.py` (NDJSON + trace/error frames) |
| DB models (14 tables) | `models/` | `storyline.py` `character.py` `setting.py` `scenario.py` `event.py` `stat.py` (StatDefinition + CharacterStat + SessionCharacterStat) `session.py` `turn_trace.py` `context_document.py` (Doc + Link) `graph_type.py` `app_setting.py` |
| Pydantic schemas | `schemas/` | `base.py` + mirrors of `models/` + `play.py` `rag.py` `reasoning.py` `settings.py` `storyline_edit.py` |
| Config/clients | `core/` | `config.py` `db.py` `redis.py` `neo4j.py` `qdrant.py` `bootstrap.py` (preflight) `seed.py` `errors.py` `ids.py` |
| Migrations | `web/backend/alembic/` | `env.py` + `versions/` (17 migrations; non-additive changes only) |
| Docker | `web/backend/docker-compose.yml`, `docker/neo4j/` | Postgres · Redis · Neo4j · Qdrant, started by root `app.py` |

## Frontend — `web/frontend/`

| Layer | Path | Notes |
| --- | --- | --- |
| Routes (8) | `app/` | `page.tsx` (`/`) · `[storylineId]/` · `[storylineId]/[scenarioId]/` (story player) · `play/[scenarioId]/` (legacy redirect) · `storylines/new/` · `storylines/[id]/edit/` · `storylines/[id]/documents/` · `options/`. One root `layout.tsx`; no route handlers. |
| Feature modules | `features/` | `story-player/` (`StoryPlayerRoute` `StoryPlayerView` `useSceneData` `useScenePlay` `turn-stream.ts` `scene-data.ts`) · `library/` (`LibraryView` `LibraryColumns` `useLibraryState` `StorylineCreatorView` `useStorylineCreator` `storylineCreator.ts` `worldBuild.ts` `useStorylineAgent` `storylineAgent.ts` `entityDocs.ts` `editor.ts`) · `options/` (`OptionsView` `useOptionsSettings` `tabs/*`) · `documents/` (`DocumentsView` `useDocuments`) |
| Domain UI (75) | `components/feature/` | Columns: `CharacterColumn` `SettingColumn` `ScenarioColumn` `ColumnChrome` `LibraryTabs` · Cards: `CharacterCard` `SettingCard` `ScenarioCard` `ScenarioCarousel` · Modals: `CharacterModal` `SettingModal` `EntityModal` `SealModal` `PortraitModal` `SceneArtModal` `CharacterProfileModal` `BeginSceneModal` `StorylineDeleteModal` `PromptOverridesModal` `BuildWorldModal` · Story player: `TranscriptBeat` `TurnStatusStrip` `TranscriptAnnouncer` `JumpToLatest` `SceneIntro` `SceneLoader` `Composer` `DirectionRow` `DirectionChecklist` `MentionMenu` `GhostwriteButton` `CastRail`+`CastRailContent` `DirectorRail`+`DirectorRailContent` `CharacterDossier`+`CharacterDossierContent` `ContextUsageDial` `PovSelect` `SceneConfigMenu` `SceneMenu` `SceneRailBar` `SceneMemoryPanel` `CoachMark` `CreateImageBar` `SceneImageBeat` `SceneImageModal` · The record: `PlaythroughTray` `BeatControls` `BeatEditor` `BeatTakePager` `RewindNotice` `TranscriptFootBar` · Graph: `GraphView` `GraphCanvas` `GraphInspectorPanel` · Editing: `StatsEditor` `VoiceSamplesEditor` `ScenarioForm` `PromptOverridesEditor` · Panels: `TriagePanel` `StorylineAgentPanel` `TurnInspectorPanel` `ContextFilesPanel` `ContextBudgetMeter` `DocumentsTable` `SourceDocumentsPanel` `ProcessProgress` · Menus: `CreateMenu` `StorylineMenu` `OptionsMenu` |
| Primitives (24) | `components/ui/` | `Button` `Modal` `Drawer` `TextField` `TextArea` `Chip` `ToggleChip` `Tag` `MultiSelect` `IconButton` `CloseButton` `FieldLabel` `SectionHeader` `Eyebrow` `Monogram` `Toast` `QuotedText` `SceneControlSelect` `TypingDots` `Spinner` `Skeleton` `SmartImage` `AsyncPanel` `FieldError` |
| App chrome (7) | `components/layout/` | `AppShell` `AppHeader` `SceneHeader` `MotionProvider` `ThemeSwitcher` `ToastProvider` `VitalsProbe` (flag-gated, inert unless `NEXT_PUBLIC_VITALS=1`) |
| Hooks (13) | `hooks/` | `use-event-stream.ts` (NDJSON consumer) `use-focus-trap.ts` (shared by `Modal` + `Drawer`) `use-media-query.ts` `use-shortcuts-enabled.ts` `use-coach-marks.ts` `use-model-health.ts` `use-scene-shortcuts.ts` `use-exit-transition.ts` `use-delayed-flag.ts` `use-hydrated.ts` `use-field-reveal.ts` `use-font-size.ts` `use-theme.tsx` |
| Helpers (19) | `lib/` | `api.ts` `types.ts` `events.ts` `theme.ts` `fonts.ts` (**self-hosted** via `next/font/local`) `font-size.ts` `shortcuts.ts` `coachMarks.ts` `promptLayers.ts` `motion.ts` `contextBudget.ts` `cardArt.ts` `graphColors.ts` `monogram.ts` `readDocs.ts` `seals.ts` `seed-data.ts` `cn.ts` |
| Styles | `styles/themes.css`, `app/globals.css` | Three themes + `--fs-*` scale; Tailwind v4 `@theme inline` mapping |

**Frontend tests are co-located** (`Foo.tsx` → `Foo.test.tsx`) — 138 files, 1375 cases. `utils/tests/frontend/` is empty; ignore it.

## Backend tests — `utils/tests/backend/`

Five area folders: `api/` `agents/` `services/` `rag/` `data/`, plus a shared `conftest.py`. Add new tests to the matching folder as `test_<behavior>.py`. 1653 cases pass today.

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
node utils/scripts/check_frontend_css.mjs       # Tailwind/stylesheet gate (works offline)
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
