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
- **10 story-event types**: `narration` · `character_dialogue` · `character_action` · `internal_thought` · `state_update` · `branch_choices` · `character_status_change` · `scene_image` (the player's in-narrative picture) · `scene_prose` (a whole free-text turn — one unattributed passage; see the two-engines note below) · `cast_request` (the scene **asking** for an absent character — never an arrival; the AI has no way to bring anyone in, and presence moves only when the player answers).
- **Streaming is NDJSON in the turn POST response.** No SSE endpoint, no WebSocket for story events, no `message_start`/`message_delta`/`message_end` frames — delta streaming re-emits the *same* event `id`+`seq` with an **incremental** `text` chunk and `done: false`, and the final frame carries `done: true` with an **empty** `text`. Accumulate by `id`; the persisted row holds the full text. Reading the text off the `done` frame alone gets you `""` for every streamed beat.
- **Alembic is in use** (29 migrations), coexisting with `create_all` + an additive reconciler.
- **The player's non-POV mode is the *Playwright*, not the Narrator** (renamed 2026-08-24). One word named two opposite things — the AI voice writing third-person prose *inside* the scene, and the player standing outside it giving instructions — and that overload was the direct cause of a point-of-view defect: a `player` beat rendered as `You:` in both transcripts, so the cast dutifully addressed a person who is not in the room (9 of 10 beats in a live baseline; the narrator wrote *"he reaches out to grab your wrist"*). A `player` beat now renders as **`Direction:`**, unconditionally — under POV the line is stored as the character's own beat instead, so the role already carries the answer. **"Narrator" now means only the AI narrator** (`narrator_agent`, `NARRATOR_SYSTEM`, the `narration` event, `role="narrator"`, `NarratorCard`). `TurnContext.player_embodied` is the one flag every renderer and prompt reads; the second-person rule rides in the character prompt's recency **tail**, not the operator-overridable output contract, so a customised prompt cannot silently lose point of view.
- **Beat length and beats-per-message are adaptive — no number reaches the prompt.** The three-tier `beatLength` control and the `maxTurns` cap are **gone** (2026-08-24), along with the four scene presets, which were defined entirely in terms of them (`GET /options/scene-presets` returns `[]`). The tiers worked exactly as instructed, which was the defect: beats clustered at 3–5 paragraphs regardless of the moment. Never reintroduce a count — and never a **word** count, which EXP-2026-08-007 measured moving the average the *wrong* way. The only ceilings left are runaway backstops: `TURN_MAX_BEATS` (24, floored at `2 × cast + 6`) and one 2048-token prose allowance. The `Scenario` columns survive but are **unread**; old clients sending the fields are ignored, not 422'd.
- **Plan mode, and `sceneFlow`.** `plannerMode` is now `auto | plan | off` (the legacy `planner` normalises to `auto`): under `plan` a turn streams a **`plan` transport frame** and *stops*, and the player sends the beats back on `TurnRequest.approvedPlan`, which the engine executes with **no second planner call**. The control lives in the composer (`PlanModeButton`), not the Config popover; `off` stays in the popover because it changes what the app *is*. Separately, `sceneFlow` chooses how prose is produced: `voiced` (**the default** — `services/turn_settings.DEFAULT_SCENE_FLOW`; one call per speaker, voices stay distinct, and "only one person speaks per beat" is structural rather than guarded) or `continuous` (one call writes the whole planned turn, marking each hand-off with `<speaker:N>`). It shipped as `continuous` on judgement and became `voiced` on 2026-08-26 on measurement — continuous under-renders its own plan, produced the only cross-speaker leak measured, and cannot reuse the prefix cache. `continuous` is still supported and not deprecated; the comparison that would settle it is open. **The frontend needs no new contract for speaker changes** — each hand-off opens its own event with its own `characterId`, which is the boundary `TranscriptBeat` already keys off. A model that emits no tags falls back to the per-speaker path for that turn. Which flow reads better is **unmeasured**; see `docs/checklist.md`.
- **A plan is never a story event**, and neither is a `plan` frame. It states what a turn *intends*, which may not happen. `_TRANSPORT_ONLY` in the turn tests is `trace | error | reasoning | plan`.
- **`utils/scripts/scene_smoke.py` is how you check prose changes.** It builds a throwaway world, plays it through the real engine against the real model, prints every beat with its speaker and paragraph count, and scores each against the point-of-view rules — importing the checks from `services/emission` so the harness and the engine's guards cannot disagree. Run it after any prompt or turn-loop change. It is **not** an experiment (n=1, no arms, recorded nowhere); anything comparative belongs in `docs/research/experiments/`.
- **`utils/scripts/memory_smoke.py` is the same idea for episodic memory.** It plays a scene against the real model and then reads `character_memories` straight out of Postgres, printing whose memory, its salience, its verified quote and its subject tags — plus the four things the Phase 3 checkpoint in `docs/plans/character-memory-graph.md` asks you to judge (are the glosses specific, do two characters' versions differ, did the quotes survive verification, is the write rate plausible). Also not an experiment.
- **`director_agent.who_is_up` and `rerank` are dead code** — tests only. `planner_agent.plan_beats` makes the real decision, and its reply also carries each beat's **register** (`light`/`neutral`/`tense`/`grave`) + `stakes`, which drive the character prompt's tail, voice-sample selection, and sampler.
- **The turn is planned ONCE, up front, and that plan is a contract** (2026-08-26). `turn_planner_lookahead` defaults to **0 = plan the whole turn**; `turn_plan.preflight` makes that single call for `auto` as well as `plan`, and a plan the *model* wrote is **bound** — the loop executes it and **never re-plans**. Only the fallback path (endpoint unreachable, reply unparseable) stays adaptive, because binding a single scripted beat would turn an outage into a one-beat scene. This replaced a ReAct loop that re-planned after every beat and let a turn run away whenever the queue emptied: `elif not planned:` silently asked for more. `EXP-2026-08-016` measured it: the `voiced` arm ran turns of 18, 24 and 22 beats, and the `continuous` arm produced a **38-beat** turn — worse than the "18, 22 and 24" that circulated for a week, which was one arm's three worst turns. That experiment sat `status: planned` with an empty write-up while three documents cited it; it was reconstructed on 2026-08-31 from its surviving event log and now reads `failed`. **Its actual question — `continuous` vs `voiced` — is still open**, as is EXP-2026-08-017's. **Two things still outrank the plan** and both are deliberate: the player's **direction requirements** (an undelivered instruction reschedules and *does* re-plan — the one measured source of extra planner calls, and an open product decision in `docs/checklist.md`), and the **scene-opening narration**, which is emitted before the plan exists.
- **Deliberation lives in planning, not in prose.** `PLANNER_EFFORT` is `HIGH` (1024 thinking tokens, paid **once per turn**); `character_turn_agent.TURN_EFFORT` is **`NONE`**. It was the other way round until 2026-08-26, when the prose call was measured spending **91 % of its output on hidden reasoning** (2646 reasoning characters for 247 of prose). The beat now arrives with its actor, register, stakes **and the plan's `reason`** — so it executes a decision instead of re-deriving one. Dropping the private channel is only safe because `prose_guards.looks_like_scratchpad` and the degeneration guard exist; a test pins that both still do.
- **The LLM layer can bound a model mechanically**, which it could not before: `stop` sequences and `response_format` JSON-schema decoding are both plumbed. **A `stop` sequence matches the REASONING channel too** — measured: `stop: ["<END_SCENARIO>"]` killed a generation mid-thought and returned empty content — so it is dropped unless reasoning is explicitly `NONE` (and `None` is *not* off: it sends no budget key, so the server default applies). A tag that must survive reasoning is parsed out of the finished text, as `<speaker:N>` already is. Constrained planning is on by default and retried unconstrained if the endpoint rejects it.
- **A storyline can carry a NARRATIVE STYLE GUIDE — six blocks saying how the story is *written*.** `content/style_blocks.py`: `attention` · `voice` · `pacing` · `texture` · `never` · `signature`, every one optional, editable and clearable, on `storylines.style_blocks` and overridable per scene on `scenarios.style_blocks`. `services/style_guide.py` is the one owner of resolution and rendering. **Two layers only — `storyline → scenario`, and deliberately no global layer** (unlike `prompt_overrides`), because a global guide would push one voice onto every world; saved presets are a **library, not a layer**, and applying one *copies* its text so editing a preset later cannot rewrite a shipped world. **Placement is the load-bearing part**: the four prose blocks lead `ctx.stable_prefix`, so they sit between the output contract and `WORLD:` in a system message that is byte-identical for every speaker and beat and are paid for **once per scene**; `pacing` (+`never`) is appended to the planner's system message; only the one-clause `signature` rides the volatile tail, fused into the act-now cue. A scenario override is an **appended delta**, never an in-place rewrite — an in-place one would break the cached prefix mid-guide instead of at its last bytes. Block text is **literal, never interpolated** (a `{token}` makes it volatile and destroys the placement), and **no block may contain a count** of paragraphs/beats/sentences/words — tests pin that for the built-in presets *and* for `agents/style_agent`'s output. **No measurement supports a claim that the guide changes the prose.** `EXP-2026-08-018` reported an effect; `EXP-2026-08-019` re-ran its unchanged baseline on the same prompts and moved it by more than the effect, so that number is noise. The placement is justified by COST (it is free per beat), not by measured quality — and the `signature`, which is *not* free per beat, is recorded in `docs/checklist.md` as a deletion candidate. **Both the modal and the storyline Assistant can drive it with the model**: `POST /storylines/style/revise` revises the guide in the editor on a plain-language instruction (an **empty answer means "leave it alone"**, never "clear it"), and `styleBlocks` is a scoped field on the assistant whose edits travel as `styleChanges` — block by block, `after: null` meaning removal, so approving one change never drops the others.
- **There are TWO turn engines, chosen by `sceneMode` per scene (overridable per turn).**
  `structured` (the default, and what `NULL` reads as) is everything below and above this line:
  the intent read, the bound plan, registers, prose decomposed into attributed beats by
  `sceneFlow`. **`freetext`** (`services/freetext_turn`) is the other one, and it is not a
  setting on the first — it is a different loop: **no planner, no intent call, no direction
  requirements, no beats, no attribution.** One generation writes the whole turn as a single
  third-person passage holding the room, emitted as ONE `scene_prose` event with **no
  `characterId`**. Its quality mechanism is a checklist the model writes for itself
  (`agents/task_agent`) and then grades its own passage against; anything short of `yes`
  continues **the same event** (cap 2), so the passage on screen grows rather than a second
  block appearing under it. Retrieval is model-led (`agents/lookup_agent`) rather than the
  regex gate. **The checklist is withheld from the writer under Playwright and sent under POV**
  — a model handed a checklist writes to the checklist. A plain POV turn with no guidance gets
  no checklist, no review and no continuation: two calls, one passage. `sceneFlow` and
  `plannerMode` are **not read at all** in this mode, and the Config popover disables both and
  says why. Every call of a free-text turn shares one byte-identical prompt prefix
  (`services/freetext_context`) carrying the **whole cast**; live stat values ride in the small
  tail so a stat change cannot invalidate it. **Which engine reads better is unmeasured** — the
  mode ships on the owner's judgement, and the cost it pays is per-character prompt isolation.
- **The thinking budget is a per-turn control** (`TurnOverrides.thinking`), six levels mapping
  onto the existing `ReasoningEffort` ladder (128 · 256 · 512 · 1024 · 2048 · 4096). **Unset is
  not a seventh level**: it means "leave every call-site's own budget alone", which is what
  keeps the structured engine's prose call at `NONE`. There is no scenario column for it, by
  the same argument as the pinned register.
- **The LLM layer is provider-dispatched.** `services/llm_providers/` holds four adapters — `openai-compatible` · `anthropic` · `gemini` · `ollama` — and the `provider` field on the `llm` settings row, which existed and was displayed but was **dispatched on nowhere**, is now load-bearing. An adapter owns the six things that differ per backend and each fail *silently*: request URL + auth, body shape, reply parsing, usage accounting, model listing, and **the stream** — its media type, its framing, and where a frame keeps its text, its deliberation, its token counts and its finish reason. **Both paths dispatch, as of 2026-08-31.** They did not: the blocking one built the URL and body through the adapter and then sent a hardcoded `Authorization: Bearer` and read `choices[0].message.content` itself, and the streaming one parsed the OpenAI SSE dialect inline — so on Anthropic a successful call parsed as an empty completion, and on all three non-OpenAI providers every turn silently degraded to blocking. `get_adapter` falls back to `openai-compatible` for an unknown id rather than raising, and legacy `openai`/`local` values normalise to it **on read**, so existing installs migrate with no migration step. The active provider is a **process global** (`llm_providers.set_active`), primed at startup and updated by `settings_store.update_llm` — because there is one settings row, so one active provider; threading it through the `LlmConn` four-tuple would mean touching ~25 destructuring sites for a value identical at all of them. **`POST /options/llm/models` always returns 200**, with `ok: false` for an unreachable endpoint: discovery must never raise into a UI path. Each provider keeps its own credentials in a `providers` map beside the flat fields, which remain the active provider's values. **Only the `openai-compatible` path is verified against a live endpoint**; the other three are verified against their reference docs, an adversarial review and 59 contract tests, and have never made a real request — blocking or streaming. See `docs/checklist.md`, which names the two known gaps that are invisible offline.
- **The graph reaches the prompt via `graph_reader.relationship_context()`**, not `TurnContext.subgraph` (which is diagnostics-only).
- **`web/shared/contracts/` is empty.** The FE↔BE contract is hand-mirrored in `web/frontend/lib/events.ts` + `lib/types.ts`.
- **Frontend tests are co-located** (`Foo.tsx` → `Foo.test.tsx`). `utils/tests/frontend/` is empty.
- **Framer Motion, not GSAP.** No headless UI library, no TanStack, no Zod.
- **The rails are no longer `lg`-only, and below `sm` the scene bar is back + title + menu.** Below `lg`, `CastRail`/`DirectorRail`/`CharacterDossier` open as `Drawer` bottom sheets mounting the *same* `…Content` components with the *same* prop objects — so there is no reduced mobile copy to keep in sync. They open from **`SceneMenu` rows** (2026-08-31); the `SceneRailBar` that used to carry them above the composer is **deleted**, because a third horizontal band of chrome on the narrowest screen in the app is the thing it was meant to help with. A row that opens a sheet sets `closesMenu` — a toggle normally keeps the menu open so the state change stays visible, which is right for the Inspector's docked rail and wrong for a sheet that would land underneath the panel. Below `sm` the header keeps **nothing** inline: the view switch, the model-health light and the theme switcher are `render` rows in the same menu, and the title's setting/genre/tone subline is `hidden sm:block`. `SceneMenu.close` focuses its trigger synchronously, because the row that opened a sheet is gone by the time `useFocusTrap` records what to restore to. **The coach marks are deleted outright** — `CoachMark`, `use-coach-marks`, `lib/coachMarks`.
- **The three type families are self-hosted** (`app/fonts/`, `next/font/local`). `next build` therefore runs with no network — it could not before, which is why this repo had no production bundle and no Core Web Vitals number until `EXP-2026-08-012`.
- **Image generation is no longer watercolor-only.** Three art styles (`painted` — the default and the old look · `anime` · `photoreal`) live in `content/art_styles.py` and reach **every** image surface: character portraits, setting art, scenario art, the in-play scene image, and the "New Storyline" world build. A style sets the prompt-writing agent's wording *and* whether the workflow's LoRA node (`72`) is patched or **bypassed** — `anime`/`photoreal` ship LoRA-less because none is installed, editable per style in Options. `settings_store.resolve_art_style` is the one answer to "what look, with which LoRA?"; unknown ids fall back rather than raise.
- **The 16px form-control floor is split on the POINTER, not on a breakpoint.** `--fs-field` stays pinned ≥ 16px in every preset (iOS Safari zooms a focused control below that), and `components/ui/Select.tsx` is the **one** place allowed under it: `text-field pointer-fine:text-ui`. `pointer: fine` is the same predicate `styles/motion.css` uses for the 44px touch floor. `sm:text-ui` is **not** the same idea and `design-scale.test.ts` still fails it — an iPhone in landscape is 932 CSS px wide. A control's *description* likewise no longer sits in the layout: `InfoTip` shows it on hover/focus/tap while an `sr-only` twin keeps the `aria-describedby` target, which is what took the scene-config popover from 996px of content to a panel that fits.
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
| Active feature plans | `docs/plans/<feature-name>.md` — 39 files (`ls docs/plans/*.md | wc -l`; verify rather than trust this number, it has gone stale twice); `ls docs/plans/` to find one. The five-plan play-experience program is indexed by `docs/plans/play-experience-program.md` |
| Shipped-feature plans (historical — **do not read while routing**) | `docs/plans/archive/` |
| **Research record** — experiments, claims, figures, findings | `docs/research/` — contract: `docs/research/AGENT_INSTRUCTIONS.md` |

## Backend — `web/backend/app/`

| Layer | Path | Files |
| --- | --- | --- |
| API routes (all mounted under `/api`) | `routes/` | `characters.py` `context_documents.py` `graph.py` `options.py` `play.py` (turn streaming) `rag.py` `scenarios.py` `settings.py` `stats.py` `storylines.py` |
| Turn loop / orchestration | `services/` | **The turn loop, decomposed** — `turn_engine.py` is the **orchestrator only** (it defines exactly `validate_turn_inputs` + `run_turn`) and calls: `turn_setup.py` (`prepare_turn` — everything before the first beat) `beat_runner.py` (produce one decided beat) `beat_stream.py` (emission → delta-streamed events, the per-beat stops) `turn_effects.py` (stat / presence / relationship consequences) `turn_emit.py` (`Emitter` `LiveSegment` `Tracer`) `direction_runtime.py` (what the direction still owes mid-turn; `attempted` → `confirm`) `direction_check.py` (did the prose actually reach it — a lexical coverage check, no LLM call) `context_budget.py` (the one owner of the model's context window and the block-quantised transcript depth) `history_compaction.py` (what falls out of the window becomes a rolling per-session summary; invalidated on rewind/edit/re-roll) `turn_plan.py` (plan mode: show a plan and stop, or run an approved one; also owns when the planner may `ask`) `turn_finalize.py` (suggestions → graph write → reflection → recency) `freetext_turn.py` + `freetext_context.py` + `freetext_effects.py` (**the other engine** — see the two-engines note above) `session_state.py` (the one owner of history mutation — truncate, copy, replay, rebuild) `memory_recall.py` (which memories reach a beat — deterministic, **once per turn**, after the plan binds) `memory_cues.py` (reaching a memory nobody present was part of; quotable/shared/private) `memory_store.py` (**episodic memory** — verbatim-quote verification, reinforce-don't-duplicate, lineage-scoped recall, transactional delete on rewind; **Postgres is canonical**, the graph is a mirror) `session_stats.py` (session-scoped stat values) `beat_rerun.py` (re-roll a beat or a turn, keeping takes). Then `assembler.py` (context) `retrieval_gate.py` `emission.py` (a thin-tag emission → ordered segments; **multi-speaker aware**) `prose_guards.py` (whether a passage should be shown at all — degeneration, repetition, scratchpad, second person, cross-speaker leakage; split from `emission` at the line ceiling and re-exported from it) `validator.py` `consistency.py` `presence.py` `events_store.py` `turn_writer.py` `session_export.py` `reflection.py` `relationships.py` `crud.py` `stats.py` `stat_guidance.py` `stat_render.py` `type_registry.py` `storyline_apply.py` `world_populate.py` (create-time cast + settings build, from the author's classified docs) `world_populate_runs.py` (background runs + resumable frame log) `settings_store.py` `llm.py` `llm_backend.py` `graph_reader.py` `graph_writer.py` `concurrency.py` `media.py` `media_cleanup.py` `portraits.py` `scene_art.py` `scene_moment.py` (in-play scene images) `comfyui.py` |
| LLM agents | `agents/` | Turn loop: `planner_agent.py` (ReAct beat plan + register) `character_turn_agent.py` (think→speak) `narrator_agent.py` `intent_agent.py` `direction_agent.py` (the player's direction → outcomes the turn owes + the budget packer) `director_agent.py` (branch/POV suggestions; `who_is_up`+`rerank` are dead) `reflection_agent.py` `relationship_agent.py`. Authoring: `storyline_agent.py` `storyline_edit/` (`scope.py` `core.py` `editor.py` `creation.py`) `character_agent.py` `setting_agent.py` `scenario_agent.py` `triage_agent.py` `roster_agent.py` (invented roster) `extract_agent.py` (the author's docs → named subjects). `scene_script_agent.py` (one call writes a whole planned turn, speaker-tagged — `sceneFlow: "continuous"`). In-play art: `moment_agent.py` (the scene → an appearance-first image prompt). Memory: `recap_agent.py` (dropped beats → the scene's rolling summary). Composer: `ghostwriter_agent.py` (the player's stated intent → their own line, drafted into the composer and never persisted). Free-text: `lookup_agent.py` (what to read before writing) `task_agent.py` (the checklist, and the grade) `freetext_agent.py` (the passage). Shared: `_common.py` `prompt_registry.py` (15 overridable prompt keys) |
| Authored content | `content/` | `graph_registry.py` (7 node + 18 edge built-in types) · `art_styles.py` (3 image looks: `painted` `anime` `photoreal`) + `stats/*.md` (`health` `patience` `suspicion` `trust`) |
| Hybrid RAG | `rag/` | `schema.py` `serializer.py` `tokens.py` `entries.py` `embedder.py` `store.py` `indexer.py` `retriever.py` `const.py` |
| Live turn state | `memory/` | `buffer.py` (Redis recent-turn buffer) `interior.py` |
| Event stream | `events/` | `envelope.py` (9 story events) `stream.py` (NDJSON + trace/error frames) |
| DB models (15 tables) | `models/` | `storyline.py` `character.py` `character_memory.py` (episodic memory — **Postgres is canonical**, unlike the rest of the graph) `setting.py` `scenario.py` `event.py` `stat.py` (StatDefinition + CharacterStat + SessionCharacterStat) `session.py` `turn_trace.py` `context_document.py` (Doc + Link) `graph_type.py` `app_setting.py` |
| Pydantic schemas | `schemas/` | `base.py` + mirrors of `models/` + `play.py` `rag.py` `reasoning.py` `settings.py` `storyline_edit.py` |
| Config/clients | `core/` | `config.py` `db.py` `redis.py` `neo4j.py` `qdrant.py` `bootstrap.py` (preflight) `seed.py` `errors.py` `ids.py` |
| Migrations | `web/backend/alembic/` | `env.py` + `versions/` (29 migrations; non-additive changes only) |
| Docker | `web/backend/docker-compose.yml`, `docker/neo4j/` | Postgres · Redis · Neo4j · Qdrant, started by root `app.py` |

## Frontend — `web/frontend/`

| Layer | Path | Notes |
| --- | --- | --- |
| Routes (8) | `app/` | `page.tsx` (`/`) · `[storylineId]/` · `[storylineId]/[scenarioId]/` (story player) · `play/[scenarioId]/` (legacy redirect) · `storylines/new/` · `storylines/[id]/edit/` · `storylines/[id]/documents/` · `options/`. One root `layout.tsx`; no route handlers. |
| Feature modules | `features/` | `story-player/` (`StoryPlayerRoute` `StoryPlayerView` `useSceneData` `useScenePlay` `turn-stream.ts` `scene-data.ts`) · `library/` (`LibraryView` `LibraryColumns` `useLibraryState` `StorylineCreatorView` `useStorylineCreator` `storylineCreator.ts` `worldBuild.ts` `useStorylineAgent` `storylineAgent.ts` `entityDocs.ts` `editor.ts`) · `options/` (`OptionsView` `useOptionsSettings` `tabs/*`) · `documents/` (`DocumentsView` `useDocuments`) |
| Domain UI (82) | `components/feature/` | Columns: `CharacterColumn` `SettingColumn` `ScenarioColumn` `ColumnChrome` `LibraryTabs` · Cards: `CharacterCard` `SettingCard` `ScenarioCard` `ScenarioCarousel` · Modals: `CharacterModal` `SettingModal` `EntityModal` `SealModal` `PortraitModal` `SceneArtModal` `CharacterProfileModal` `BeginSceneModal` `StorylineDeleteModal` `ScenarioDeleteModal` `PromptOverridesModal` `BuildWorldModal` · Story player: `TranscriptBeat` `TurnStatusStrip` `TranscriptAnnouncer` `JumpToLatest` `SceneIntro` `SceneLoader` `Composer` `DirectionRow` `DirectionChecklist` `MentionMenu` `GhostwriteButton` `CastRail`+`CastRailContent` `DirectorRail`+`DirectorRailContent` `CharacterDossier`+`CharacterDossierContent` `ContextUsageDial` `PovSelect` `SceneConfigMenu` `SceneMenu` `SceneMemoryPanel` `CreateImageBar` `SceneImageBeat` `SceneImageModal` · The record: `PlaythroughTray` `BeatControls` `MemorySource` `BeatEditor` `BeatTakePager` `RewindNotice` `TranscriptFootBar` · Graph: `GraphView` `GraphCanvas` `GraphInspectorPanel` · Editing: `StatsEditor` `VoiceSamplesEditor` `ScenarioForm` `PromptOverridesEditor` · Panels: `TriagePanel` `StorylineAgentPanel` `TurnInspectorPanel` `ContextFilesPanel` `ContextBudgetMeter` `DocumentsTable` `SourceDocumentsPanel` `ProcessProgress` · Menus: `CreateMenu` `StorylineMenu` `OptionsMenu` |
| Primitives (29) | `components/ui/` | `Icon` `Button` `Modal` `Drawer` `Page` `Reveal` `TextField` `TextArea` `Chip` `ToggleChip` `Tag` `MultiSelect` `IconButton` `CloseButton` `FieldLabel` `SectionHeader` `Eyebrow` `Monogram` `Toast` `QuotedText` `Select` `SceneControlSelect` `InfoTip` `TypingDots` `Spinner` `Skeleton` `SmartImage` `AsyncPanel` `FieldError` |
| App chrome (7) | `components/layout/` | `AppShell` `AppHeader` `SceneHeader` `MotionProvider` `ThemeSwitcher` `ToastProvider` `VitalsProbe` (flag-gated, inert unless `NEXT_PUBLIC_VITALS=1`) |
| Hooks (12) | `hooks/` | `use-event-stream.ts` (NDJSON consumer) `use-focus-trap.ts` (shared by `Modal` + `Drawer`) `use-media-query.ts` `use-shortcuts-enabled.ts` `use-model-health.ts` `use-scene-shortcuts.ts` `use-exit-transition.ts` `use-delayed-flag.ts` `use-hydrated.ts` `use-field-reveal.ts` `use-font-size.ts` `use-theme.tsx` |
| Helpers (18) | `lib/` | `api.ts` `types.ts` `events.ts` `theme.ts` `fonts.ts` (**self-hosted** via `next/font/local`) `font-size.ts` `shortcuts.ts` `promptLayers.ts` `motion.ts` `contextBudget.ts` `cardArt.ts` `graphColors.ts` `monogram.ts` `readDocs.ts` `seals.ts` `seed-data.ts` `cn.ts` |
| Styles | `styles/themes.css`, `app/globals.css` | Three themes + `--fs-*` scale; Tailwind v4 `@theme inline` mapping |

**Frontend tests are co-located** (`Foo.tsx` → `Foo.test.tsx`) — 152 files, 1565 cases. `utils/tests/frontend/` is empty; ignore it.

## Backend tests — `utils/tests/backend/`

Five area folders: `api/` `agents/` `services/` `rag/` `data/`, plus a shared `conftest.py`. Add new tests to the matching folder as `test_<behavior>.py`. 2273 cases pass today.

## Root-level essentials

| File | Purpose |
| --- | --- |
| `app.py` | Launches backend + frontend (`python app.py`), one side (`… backend`\|`frontend`), or stops both (`… stop`). Frees ports 3345/3346 first and owns Docker. |
| `pyproject.toml` / `.python-version` | uv-managed backend project, Python 3.13 |
| `.env.example` | Every env var, documented — copy to `.env` |
| `Makefile` | Research-record targets only (`new-experiment` `validate-research` `research-index` `figures`). Does **not** replace `app.py`. |
| `CONTRIBUTING.md` | Validation gate + how to run an experiment |
| `utils/scripts/line_counter.py` | Standalone LOC utility, not part of the app |

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
