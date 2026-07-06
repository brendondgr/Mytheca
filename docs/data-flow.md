# Velora — Data Flow

How data originates and moves through Velora. The streaming/event path is first-class.

> **Current implementation.** The **Library** is now backend-backed: it reads from and writes to the FastAPI CRUD API via `web/frontend/lib/api.ts` (hand-rolled fetch, await-then-apply), so storylines/characters/settings/scenarios **persist** in Postgres. The backend is seeded with the Embergate world (`web/backend/app/core/seed.py`) so the app looks the same. The **Story player** streams live turns over the backend and **persists every play-through**: each turn's events (incl. hidden thoughts) and the diagnostic trace are saved, so reopening a scenario **resumes its most recent session** with the full history and continues forward (see *Scene Persistence, Resume & Export* below). The seed data (`web/frontend/features/story-player/scene-data.ts`) is now only the fallback opening for a never-played scene. (TanStack Query is still deferred; the hand-rolled client suffices for this CRUD surface.)

## Sources

| Source | Examples | Where it lives |
| --- | --- | --- |
| PostgreSQL (core state) | users, storylines, characters, settings, scenarios, events, stat definitions, stat values | `web/backend/app/models/` |
| Redis (live/cache) | active scenario state, stream pub/sub, cached reads | `web/backend/app/core/` (client), used by `services/` |
| Neo4j (Story Graph) | character/setting nodes + their edges (the one knowledge graph); instances only — the type system lives in Postgres | `app/core/neo4j.py` (client), `app/services/graph_{writer,reader}.py` |
| YAML config | hand-authored storylines, characters, settings, stat definitions | loaded by `app/core/` → `services/` (State manager) |
| Markdown guidance | one file per stat (what raises/lowers it, bands, behavior) | `app/core/` loader → injected into agent context |
| LLM providers | model completions for agents | `web/backend/app/core/` (provider interface) → `app/agents/` |
| Client-only state | UI state, draft input, panel toggles, theme | `web/frontend/` (React state) |
| Derived/cached | computed scenario state, summaries | `app/services/`, cached in Redis |
| Qdrant (hybrid RAG) | named dense + sparse vectors for all entities/context-docs; hybrid dense+BM25+RRF retrieval injected into authoring agents | `app/core/qdrant.py` (client), `app/rag/{store,indexer,retriever}.py` |

## Read Path (e.g. open a scenario)

1. Frontend route loads → calls `GET /scenarios/{id}` (and related storyline/characters/settings) via the `lib/` API client.
2. FastAPI route → service → Postgres model → Pydantic schema → JSON response.
3. Frontend renders; server-state caching via TanStack Query if/when adopted.

## Write + Streaming Path (submit a turn — the response *is* the stream)

The turn engine (`web/backend/app/services/turn_engine.py`) runs the turn and streams
the resulting story events directly in the `POST /play/{scenarioId}/turn` response body
(NDJSON, reusing the `postNdjson` / `StreamingResponse` pattern) — there is no separate
stream connection for the single-player case (the `GET /stream/{sessionId}` + Redis pub/sub
fan-out is a deferred seam, see `api-contract.md`).

```
Story player (useScenePlay) → lib/api.postTurn → POST /play/{scenarioId}/turn  {text, directedAt?, sessionId?}
  → routes/play (pre-flight: scenario exists, text present, session valid)
  → turn_engine.run_turn:
      events_store: resolve/create PlaySession · record user_turn (seq 0, Postgres)
      assembler.assemble_context (Band-1, read-only): ordered cast + clamped stats + loaded
        stat guidance + recent buffer (Redis, best-effort) + scenario subgraph (Neo4j,
        best-effort) + cacheable stable prefix + GATED RAG (retrieval_gate: a cheap
        model-free skip-or-fetch — off-roster entity / world-history question; on fetch,
        _common.rag_block retrieves + injects a fenced RETRIEVED LORE block, best-effort)
      memory.buffer.push_turn (player line → recent-turn buffer, best-effort)
      _pick_speaker → character_turn_agent.generate_line (ONE isolated, bookended LLM call)
        → services.llm.chat_complete (configured endpoint; reasoning budget; guided-decoding seam)
      emission.parse_emission: thin <speaker:N>/<type:…> tags → typed segments (name→id; out-of-roster drop)
      _Emitter: assign per-session seq · validate (build_event) · persist (Postgres) · push buffer
        · internal_thought → private_to_user (streams as the thought bubble; NOT pushed to
          turn_beats, so later speakers never see it) · yield visible events
  → StreamingResponse NDJSON ──▶ client
```

On the client, `useScenePlay` (via the generic `useEventStream` hook + `postTurn`) consumes
the stream: **delta-streamed prose** (`narration`, `character_dialogue`) accumulates by event
`id` (incremental `text` chunks, `done` flips true last). A speaker's `internal_thought`,
`character_action`, and `character_dialogue` **all fold into one `char` beat** (the thought
opens it, action + dialogue merge in as they arrive — `mergeFrame`/`isOpenCharBeat`), so a
message reads as one moment: the character's name, then **one bubble** holding their muted
**thinking** line and the spoken line at the **same text size** (`QuotedText` bolds any quoted
run, keeping the quotes). `state_update` / `branch_choices` drive the side panels. A scene seeds
**narrator-only** (no character speaks before the player acts); selecting a follow-up suggestion
**writes its text into the composer** (focused, for review/editing) rather than auto-sending —
the player edits and sends it as an ordinary turn. A **scene-config menu** (`SceneConfigMenu`, a
popover now rendered by **`SceneHeader` left of Export**) sets three per-scene controls — Max
turns, Suggestions, and **Number of beats** (the context-window depth, 5–100, with a live
approximate token readout via `lib/contextBudget.estimateBeatsTokens`) — persisted on the
scenario (`updateScenario` PATCH); four suggestions render as a **2×2 grid**.

**Type-while-streaming:** the composer's `sendDisabled` prop (renamed from `disabled`) blocks
only the Send button and Enter key while a turn is in-flight — the `<textarea>` remains editable
so the player can compose their next message while characters respond. `useScenePlay.send`/`submit`
still guard against concurrent submissions. A mid-stream failure surfaces the terminal `error`
frame.

**Context-usage estimate path.** `useScenePlay` fetches `getLlmContextWindow()` once on mount
(best-effort; the bar is hidden on failure). The denominator is the `maxContextTokens` field from
`GET /options/llm/context-window` (`source: "detected"` when the engine was probed successfully,
`source: "configured"` when the stored fallback is used). The numerator is `estimateUsedTokens`
from `lib/contextBudget.ts` — the sum of each beat's combined text (text + action + thought) over
the last `contextBeats` transcript beats, converted to tokens by the char/4 heuristic. The result
drives `ContextUsageBar` (rendered by `StoryPlayerView` above the composer), which color-codes
fill as green < 50 %, gold 50–75 %, danger ≥ 75 %, and surfaces `5.2K / 16K`-style counts via
`fmtTokensK` in the hover `title` and `aria-valuetext`.

**Activity feed + per-character status (live-only).** `turn-stream.applyActivity` derives
`ActivityEntry` items from incoming frames — trace steps (`speaker` → "X is about to speak",
`plan`, `branch`) and story events (first `narration`/`character_dialogue` chunk, `internal_thought`,
`character_action`, `state_update` with reason, `character_status_change`) — and keeps the newest
12 entries (newest first). `turn-stream.applyCharacterActivity` derives a per-character
`idle | thinking | speaking` status: a `speaker` trace step or `internal_thought` event sets
`thinking`; the first `character_dialogue` chunk sets `speaking`; `done: true` resets to `idle`;
all statuses are cleared to `idle` when the stream finishes (`submit`'s `.finally`). Both feed
arrays are held in `useScenePlay` state, folded on `onFrame`, and are **live-only** —
`rehydrateFromHistory` seeds neither (the pulse and indicators reflect only the current in-flight
turn).

**Model output is sanitized centrally.** Reasoning models inline their chain-of-thought and
harmony-style channel tokens (`<|channel|>…`, `<think>…</think>`, `*Check:*`/`*Revised:*`) in
`message.content`. `services.llm.chat_complete` — the one generation call every agent shares —
runs each reply through `_common.strip_reasoning` (drop `<think>` blocks, keep only the text
after the last channel marker, scrub residual control tokens) before returning it. So the
**narrator** prose, the **character emission** (parsed downstream by `emission.parse_emission`),
and the **authoring JSON** agents all receive only the model's final answer; the scrub keeps
the app's own `<speaker:>`/`<type:>`/`<thinking>` markers intact.

The hot path is **read-only** — all mutation (durable consequences, edges) defers to the
cold-path turn-writer (a later phase); stat changes are clamped during validation.

## Scene Persistence, Resume & Export

Every turn already persists its story events to Postgres (`events`), including the hidden
`internal_thought` rows and the `user_turn` player line. Two additions make a scenario's
play-through **fully reviewable and continuable**:

- **The diagnostic trace is persisted.** `turn_engine._Tracer` writes each step to
  `turn_traces` (keyed by `(session_id, turn, n)`, where `turn` is the turn's opening
  `user_turn` seq) on **every** turn — independent of the opt-in *streaming* flag — so the
  knowledge-graph writes (`commit` / `relationships`) and the RAG/lore look-up (`lore`) that
  were previously transport-only survive for later review. `PlaySession` gains `updated_at`
  (bumped each turn) and `closed_at`.

```
Open a scenario (useScenePlay)
  → GET /play/{id}/sessions → resume the most-recent play-through
  → GET /play/{id}/sessions/{sessionId} → { session, events, traces }
      → turn-stream.rehydrateFromHistory REPLAYS the persisted rows through the SAME
        reducers used live (mergeFrame / applyStatUpdate / applyStatByChar / foldTrace;
        a persisted user_turn → a player beat; a stale branch_choices is skipped)
      → transcript + thoughts + live stats + Inspector trace restored; sessionRef continues it
Leave the scene (unmount / beforeunload)
  → POST /play/{id}/sessions/{sessionId}/close (navigator.sendBeacon) — the save-on-close
    signal (every turn already persisted; this stamps closed_at + recency)
Export (header control, left of the theme switcher)
  → GET /play/{id}/sessions/{sessionId}/export?format=json|md → attachment download
      → services/session_export renders ONE turn grouping into JSON (structured) or Markdown
        (readable): player line → beats (thought/action/dialogue/stat) → the turn's trace
        steps (graph + RAG). Server-side, so a live OR long-closed scene exports identically.
```

Because reload is **replay through the live reducers**, a reopened scene reads
byte-identically to how it was played — there is no second rendering path to keep in sync.

## Stat Change Flow

```
Director/character agent proposes a change (stat key, delta or value, reason)
  → emitted as a state_update event
  → Validator confirms the stat exists and clamps the result to [min, max]
  → event streamed to the UI (carries the change's characterId, key, clamped value, reason)
  → Director rail's Scene-state chips update (flat, global) AND the per-character store
    (`statsByChar`, keyed by characterId) updates
  → narrator may reference the new state next turn
```

The change carries a **reason**, giving a free audit trail ("Health −25: struck by the falling beam") useful for debugging the model and for showing the player *why* a number moved. Current stat values plus their guidance files feed back into agent context each turn, so a near-dead character fights weakly and a high-strength character can plausibly force a door.

**Current-band injection into the character prompt (`{Character}` substitution).** Rather than showing the acting character a bare `stamina=45`, `character_turn_agent._compose` now calls `services/stat_render.render_character_stats(ctx.stat_defs, speaker.stats, speaker.name)` for the HEAD state block. For each stat the character holds, the helper resolves the **current band** (the first `{min,max}` range containing the value — mirrors the frontend `bandLabelFor`) and renders `Display value/max (BandLabel) — <stat description> <current band description>`, substituting the literal `{Character}` (and lowercase `{character}`) placeholder in both descriptions with the character's name. So the model reads, e.g., *"Stamina 45/100 (Capable) — Mara's capacity for sustained exertion… Mara still has the fight to continue forward."* Bands/descriptions are optional; a def-less speaker falls back to the old compact `k=v` line. The `_BLUEPRINT_SYSTEM` generator (build) is instructed to author 1–2 sentence stat descriptions and per-band descriptions using the `{Character}` placeholder; the stat-proposal agent (`character_agent._bands_text`) also folds band descriptions into its context.

The client keeps stats **two ways** so both right-rail surfaces stay live: a flat `StatChip[]`
(`applyStatUpdate`) drives the Director rail's global Scene-state chips, and a per-character
map (`applyStatByChar`, keyed by the event's `characterId`) drives the **character dossier**
and the **cast rail** — their stat sliders/rows (`StatSchema`/`StatSlider`, `CastRail`'s
`CastMemberStats`, sharing one `liveValueFor` matcher) render that character's live value +
band, falling back to the schema default only for a stat never explicitly set.

**`statsByChar` is baseline-seeded, not just event-driven.** Before P3 (Play-experience fixes)
`statsByChar` started **empty** and only ever filled in from `state_update` events — so a
character whose persisted starting stat differed from the schema default read as "never
changing" until that exact stat happened to move in the current session (a user-reported bug:
values shown didn't match what the Inspector traced). `useScenePlay` now fetches each cast
member's **persisted starting stats** (`GET /characters/{id}/stats`, best-effort per character)
on scene load and folds them into a baseline (`turn-stream.baselineStatsByChar`) *before* any
turn runs; a resumed session's persisted deltas (`rehydrateFromHistory`'s optional
`initialStatsByChar` param) layer on top of that baseline instead of replacing it, so an
untouched stat still reads as the character's real value across reload too. The Director
rail's own "Character stats" section — which rendered the schema **defaults only**, with no
character context at all — was removed as redundant now that the cast rail and dossier both
show correct, live, per-character values.

**Library-side (no play session) stat display is Scenario-hero-only, by design.** Several
iterations passed through `useLibraryState`'s `statsByCharId` (loaded once, keyed by character
id, refreshed whenever the character list changes) — first threading it into the Library's
`CharacterCard`/"Characters" column and the `CharacterProfileModal` popup too, but the user
settled on a narrower scope: real per-character stat values are shown **only** in the
`ScenarioCarousel` hero's `CastStats` flyout (the per-card "Statistics" panel toggled by the
`❯`/`❮` arrow). `CharacterCard` and `CharacterProfileModal` intentionally render no stats at all;
`statDefs`/`statsByCharId` are threaded from `LibraryView` to `ScenarioCarousel` only.

**`CastStats`'s "Statistics" flyout showed nothing at all for real-world stat schemas** —
a separate bug found once the flyout was the sole remaining stat surface: it filtered defs on
`d.appliesTo.length === 0 || d.appliesTo.includes(c.id)`, treating `appliesTo` as a per-character
id allowlist. `appliesTo` is actually a **node-type tag** (`["character"]` vs. e.g. a future
`["setting"]`) — the backend model's own default (`applies_to` on `StatDefinition`) — so a real
character id like `"maerin"` never matched the literal string `"character"` and every stat with
a non-empty `appliesTo` (i.e. every stat created through the normal editor) was silently dropped.
Fixed by filtering on `visibility === "public"` alone, matching every other stat consumer
(`CastRail`, `DirectorRail`, `CharacterDossier`).

The cold-path **graph trace** (Inspector's green *Graph* steps) reports *what* was written,
not just a count: the `commit` step lists each durable `Consequence.summary` (e.g. "suspicion
+12: old guilt"), and the first-turn `relationships` step lists the seeded edges
(`ensure_seeded` returns one `"A <type> B — reason"` summary per edge).

The event schema is shared via `web/shared/contracts/` and documented in `docs/api-contract.md`. Keep all three in sync.

## Settings Flow (Options menu)

```
Options page (/options) → lib/api.ts → GET/PATCH /api/options
  → settings_store reads/writes the app_settings rows (one per namespace)
  → LLM tab: POST /api/options/llm/{models,test}
      → backend httpx proxy → {baseUrl}/models · {baseUrl}/chat/completions
      → result returned to the UI (CORS-free; API key stays server-side)
  → Image Generation tab: GET /api/options/comfy/workflows · POST /api/options/comfy/status
      → comfyui client → {baseUrl}/system_stats (status); the full generate
        pipeline (POST /prompt → WebSocket wait → /history → /view) is server-side
  → Prompts tab: PATCH /api/options/prompts
      → settings_store.set_prompts_overrides (PROMPTS_KEY namespace, registry-key gated;
        blank value clears a key) → folded into TurnContext.prompts each turn
```

The LLM API key is **write-only**: stored in the `app_settings` row, never
returned to the browser (reads expose `hasApiKey` + a masked hint). Model listing
and the connection test run on the backend so they work against `localhost:*`
servers that don't send CORS headers, and so the key never reaches the client.
When the multi-agent brain lands it reads the same stored config.

## Writing-Agent Prompt Resolution Flow

```
Per-turn assemble_context (Band-1, read-only):
  prompt_registry.resolve_prompts(
      settings_store.get_prompts_overrides(db),   # global layer
      storyline.prompt_overrides or {},            # storyline layer
      scenario.prompt_overrides   or {},           # scenario layer
  )
  → TurnContext.prompts: dict[registryKey, text]
      (fold: registry default → global → storyline → scenario; last non-blank wins;
       blank / unknown keys ignored)
  → character_turn_agent reads ctx.prompts["character.output_contract"]
  → narrator_agent     reads ctx.prompts["narrator.system"] / "narrator.system_long"
  → director_agent     reads ctx.prompts["director.who_is_up"] / "director.rerank" / "director.branch"
  → planner_agent      reads ctx.prompts["planner.system"]
  (each falls back to prompt_registry.default(key) when the key is absent from ctx.prompts)
```

The **prompt registry** (`web/backend/app/agents/prompt_registry.py`) is the single source of
truth for the four writing agents' system prompts. It defines `PromptSpec` (key, agent, label,
description, default) and `PROMPT_REGISTRY` with exactly seven keys. `resolve_prompts(*layers)`
folds the layers left-to-right; an empty/None value at any layer is skipped. The global layer is
stored in `app_settings` (a `PROMPTS_KEY` namespace) via `settings_store.get_prompts_overrides` /
`set_prompts_overrides`. Per-storyline and per-scenario overrides are nullable JSONB columns
(`prompt_overrides`) persisted through the existing storyline/scenario PATCH endpoints. Authors
edit global overrides via **Options › Prompts**; per-storyline overrides via the library's gear
icon; per-scenario overrides via the scenario editor's "⚙ Writing prompts" button. The innermost
(scenario) layer always wins when set.

## Reasoning-Budget Flow (engine detection + thinking cap)

```
App startup (lifespan) → background poller every LLM_BACKEND_POLL_SECONDS
  → llm_backend.refresh_for_config → probe configured endpoint
      GET {root}/version → vLLM · GET {root}/props → llama.cpp · else unknown
  → cached per base URL (LLM_BACKEND_CACHE_TTL_SECONDS)

Authoring call → agent passes a backend-set reasoning effort
  → llm.chat_complete(reasoning=) → llm_backend.get_backend (cached)
      → apply_reasoning: vLLM thinking_token_budget / llama.cpp thinking_budget_tokens
      → unknown: no key added (unchanged behaviour)
GET /api/options/llm/backend → read-only view of the detected engine + budgets
```

The effort is **never user-controllable** for Storyline/Character/Setting creation —
it is fixed at each call-site (**Triage = Low**, build + standalone drafts =
**Medium**). The poller lets the server adapt when the operator swaps engines without
a restart; it is skipped under SQLite (the test/offline profile).

## Storyline Authoring Flow (creation-time agent)

```
Create modal (StorylineModal) → lib/api.ts
  → POST /api/storylines/draft   {seed, docsOverview?}  → {title, genre, tagline, premise}
  → POST /api/storylines/primer  {premise, seed?, docsOverview?} → {worldPrimer}
      → routes/storylines → agents/storyline_agent
          → settings_store resolves the configured endpoint/model/key
          → services/llm.chat_complete → {baseUrl}/chat/completions
  → drafted fields + primer fill the form; author edits, then the normal
    POST/PATCH /api/storylines persists premise + worldPrimer
```

This is a **one-time, creation-time** generation, not a per-turn cost. There is
**no retrieval / RAG**: `docsOverview`, when present, is text read from dropped
reference files *in the browser* and passed inline for that one call only — the
files are never uploaded, persisted, or indexed (the corpus/RAG layer is a later
plan). The agent reuses the same stored LLM config as the Options menu.

## Character Authoring Flow (creation-time agent + portrait)

```
Character modal (CharacterModal) → lib/api.ts
  → POST /api/characters/draft            {seed, docsOverview?, storylineId?}
        → {name, role, traits, speech, goal, secret, appearance, background, personality, color}
  → POST /api/characters/portrait-prompts {name, appearance, traits, species?, ...} → {positive, negative}
  → POST /api/characters/portrait         {positive, negative}  → {portrait: "/media/portraits/<id>.webp"}
        → routes/characters → agents/character_agent (draft/prompts/voice/stats; same
          settings_store + services/llm.chat_complete as the storyline agent)
        → routes/characters → services/portraits → services/comfyui.generate
          (watercolor pipeline) → PNG → Pillow → WebP saved under MEDIA_DIR, served at /media
  → POST /api/characters/voice-samples    {name, background, personality, ...} → {samples:[{situation,sample}]}
        (voice & tone comes FIRST — derived from the drafted prose before stats; best-effort → [];
         the model plans the character's distinctive voice first, then each pair is a previous
         situation paired with the character's SINGLE in-voice response to it — one turn, never
         a back-and-forth exchange — reacting to that situation's specifics, not a generic blurb)
  → POST /api/characters/starting-stats   {storylineId, ...} → {proposals:[…]}  (proposal only)
  → drafted fields + portrait fill the form; author edits (incl. the Voice & tone
    section, above Starting stats), then the normal POST/PATCH
    /api/storylines/{id}/characters persists the fields + portrait URL
    + portraitPositive/portraitNegative (the prompts that produced it, so the
    portrait editor re-hydrates them on re-edit) + voiceSamples (the voice/tone
    profile); accepted starting stats are applied via PUT /api/characters/{id}/stats
```

The `voiceSamples` then feed the runtime turn loop: `assembler._build_cast` renders
each character's pairs into a `CastMember.voice_samples` block, and
`character_turn_agent` injects it into the generation prompt HEAD — anchoring both
the spoken line and the hidden `<thinking>` step to the character's authored voice.
The samples are framed as a **baseline** ("how you sound at rest"), not a script:
the person stays constant but the register **flexes with the stakes** of the moment
(see the situational-voice-adaptation note in the turn-loop section below).

Same **creation-time, no-RAG** rules as storyline authoring. Everything produced
is a character's **own base identity** (§1 node properties) — no graph structure
is built here. Portrait generation is an explicit, opt-in step (it spends GPU
time on the local ComfyUI server); starting stats are **proposal-only** until the
author saves them. **"Draft with Velora" fires on a seed sentence, a Draft-tagged
context file, or both** — the modal enables the button (and the backend accepts
the request) whenever either is present, and only refuses when both are empty.

## Setting Authoring Flow (creation-time agent + scene art)

```
Setting modal (SettingModal) → lib/api.ts
  → POST /api/settings/draft               {seed, docsOverview?, storylineId?}
        → {name, type, desc, atmosphere, features, currentState}
  → POST /api/settings/scene-art-prompts   {name, atmosphere, features, ...} → {positive, negative}
  → POST /api/settings/scene-art           {positive, negative}  → {image: "/media/scenes/<id>.webp"}
        → routes/settings → agents/setting_agent (draft/scene-art prompts; same
          settings_store + services/llm.chat_complete as the storyline agent)
        → routes/settings → services/scene_art → services/comfyui.generate
          (watercolor pipeline) → PNG → services/media (Pillow → WebP) saved under
          MEDIA_DIR/scenes, served at /media
  → drafted fields + image fill the form; author edits, then the normal
    POST/PATCH /api/storylines/{id}/settings persists the fields + image URL
    + sceneArtPositive/sceneArtNegative (the prompts that produced it, so the
    image editor re-hydrates them on re-edit)
```

Same **creation-time, no-RAG** rules. Everything produced is a setting's **own
base description + current state** (§4.1 Setting-node properties) — never the
play-accrued **event timeline** (ships empty, written async once play exists) and
never graph edges. Scene art is an explicit, opt-in step (it spends GPU time on
the local ComfyUI server). As with characters, **"Draft with Velora" accepts a
seed sentence, a Draft-tagged context file, or both** (only both-empty is
refused).

## Scenario Authoring Flow (creation-time agent)

```
Scenario modal (EntityModal + ScenarioForm) → lib/api.ts
  → POST /api/scenarios/draft   {seed, docsOverview?, storylineId?}
        → routes/scenarios → agents/scenario_agent.draft_scenario
            world_context + numbered ROSTER (crud.list_characters / list_settings,
              capped at 40 each) → services/llm.chat_complete (same settings_store)
            model returns names → resolve names→ids (case/whitespace-folded):
              drop unknown cast · setting → "" when unmatched · dedupe cast
        → {title, genre, tone, goal, opening, castIds, settingId}
  → drafted fields + the resolved cast (MultiSelect multiple) + setting (MultiSelect
    single) fill the form; author edits, then the normal
    POST/PATCH /api/storylines/{id}/scenarios persists it
```

Same **creation-time, no-RAG** rules. The key invariant: the drafted `castIds` /
`settingId` are **always real members of the active storyline** — the agent never
trusts model-emitted ids, it resolves names against the live roster and drops
anything that doesn't match, preserving `resolveScenario`'s soft-reference
fallback by construction. The scenario modal grounds on **seed + world roster**
only (no `ContextFilesPanel` yet); branches are not drafted in this first cut.

## Scenario Scene Art Flow (creation-time agent + image)

```
Scenario modal (EntityModal) → lib/api.ts
  → POST /api/scenarios/scene-art-prompts
        {title?, genre?, tone?, goal?, opening?, settingName?, settingDesc?, notes?}
        → routes/scenarios → agents/scenario_agent.generate_scene_art_prompts
            builds a setting-atmosphere watercolor prompt (no people)
            → services/llm.chat_complete (same settings_store)
        → {positive, negative}  (SceneArtPromptResponse)
  → POST /api/scenarios/scene-art   {positive, negative}
        → routes/scenarios → services/scene_art.generate_scene_art
            (watercolor pipeline, landscape 16:9) → PNG → services/media (Pillow → WebP)
            saved under MEDIA_DIR/scenes, served at /media/scenes
        → {image: "/media/scenes/<uuid>.webp"}
  → image URL stored in draft.image; author edits in SceneArtModal, then
    POST/PATCH /api/storylines/{id}/scenarios persists image + sceneArtPositive + sceneArtNegative
```

Same **creation-time, no-RAG** rules. Scene art depicts the setting atmosphere shaped
by the scenario's tone — no characters or people. The active setting's name/description
are passed as context when available. Scene art is an explicit, opt-in step (it spends
GPU time on the local ComfyUI server). The prompt pair is saved alongside the image URL
so it can be refined and re-rendered.

## Orphaned-Media Cleanup Flow (maintenance)

```
Options → About tab → Maintenance section → lib/api.ts
  → GET  /api/options/media/orphans?min_age_hours=24   (dry-run scan)
        → routes/options → services/media_cleanup.scan_orphans
            referenced = {basenames of Character.portrait} ∪ {Setting.image} ∪ {Scenario.image}
            for *.webp in MEDIA_DIR/portraits + MEDIA_DIR/scenes:
              orphan   = basename ∉ referenced
              eligible = orphan AND mtime older than min_age_hours (grace period)
        → {portraits, scenes, orphanCount, eligibleCount, totalBytes, eligibleBytes, minAgeHours}
  → author reviews counts, confirms, then
  → POST /api/options/media/cleanup?min_age_hours=24   (delete eligible only)
        → services/media_cleanup.delete_orphans (re-scans; unlinks eligible orphans)
        → {deletedCount, freedBytes, skippedRecentCount}
```

A WebP is written to disk the moment ComfyUI renders it — before the entity is
saved — so a cancelled draft or a deleted Character/Setting leaves an unreferenced
file behind. Cleanup cross-references disk against the two media columns. The
**grace period** (`min_age_hours`, default 24) is the safety valve: a just-generated
file from an in-flight draft counts as an orphan but is *not eligible*, so an
author mid-creation never loses their pending image. Deletion is doubly guarded
(unreferenced AND grace-expired), `.webp`-only, and scoped to the two media subdirs.

## Build Everything Flow (the New Storyline world build)

```
New Storyline page → "Build the whole world" → POST /storylines/build {seed?, docsOverview?, …Docs?}
  → build_agent orchestrates (configured LLM):
      draft_storyline → metadata
      generate_world_primer → World Primer
      blueprint → universal stat schema (its invented concepts are ignored)
      extract_agent.extract_entities × (one per attached doc) → the roster of
        distinct characters + settings each doc contains (deduped across docs)
      draft_character × N (one per extracted character, grounded in the world brief)
      draft_setting   × M (one per extracted setting)
        ↑ N and M drafts run CONCURRENTLY (bounded by the operator's
          authoringConcurrency; the LLM connection is pre-resolved once so the
          worker threads never touch the request Session). 1 → sequential.
          A per-entity draft failure is skipped (best-effort), never fatal.
  → ProposedWorld returned for REVIEW (nothing persisted yet)
  → author edits/prunes → "Create world" commits via normal CRUD:
      POST /storylines → POST …/stats × → POST …/characters × (+ portrait if ComfyUI)
        + PUT …/stats → POST …/settings × (+ scene-art if ComfyUI)
        + POST …/context-docs/bulk (the triaged corpus)
  → navigate to /{newStorylineId}
```

The build is a **one-time, creation-time** orchestration (not a per-turn cost) and
**persists nothing** — it returns a proposal so the author reviews before a dozen
AI-drafted rows are written. Images are **opt-in** and rendered at commit only when
ComfyUI is configured (best-effort per entity; a failed render never aborts the build).
Same **no-retrieval** rule as the other authoring agents: `docsOverview` is inline
dropped-file text, bounded and used for the build only.

### Live build (streaming) — the default UI path

```
New Storyline page → "Build the whole world" → POST /storylines/build/stream  (NDJSON)
  → for-await over the response body (lib/api.postNdjson):
      status → meta  → left fields fill (Title/Genre/Tagline/Premise)
      status → primer→ World Primer fills
      status → extract→ ONLY the Extract-checked docs are mined (opt-in per doc,
                        default off), for NAMED subjects, RESPECTING the triage bucket
                        (character→named chars, setting→named settings, uncategorized→
                        either strictly, other→lore-only-never-extracted), CONCURRENTLY
                        (bounded by authoringConcurrency) + per-doc progress
                        ("Read k/N: <name>"); an unreadable uncategorized doc is retried
                        once then SKIPPED (named), never fatal
      status → plan  → stat schema + skeleton labels (the EXTRACTED subject names)
      character × N  → one per extracted character, fills its skeleton card
      setting   × M  → one per extracted setting, fills its skeleton card
        ↑ drafted CONCURRENTLY → events arrive OUT OF ORDER; the page places each by
          its `index` (storylineCreator.upsertAt), so a sparse card fills as its
          draft completes. Image rendering (renderProposalImages) stays sequential.
      done           → canonical ProposedWorld swapped in (review mode)
  → if ComfyUI REACHABLE (status preflight): renderProposalImages renders each
      portrait/scene-art and patches the displayed entity → IMAGE previews pop in live
  → "Create World" commit → persists everything; attaches already-rendered images and
      renders any still missing (renderPortrait/renderSceneArt) → navigate to /{id}
```

The build creates the storyline, the stat schema, and **only the characters/settings
mined from docs the author checked Extract on**. Extraction is **opt-in per document**:
a doc's `extract` flag (default **off**) gates whether it is mined at all — a new
storyline never auto-extracts. For the Extract-checked docs, extraction then **respects
the author's triage bucket** — it never invents an entity by expanding lore:

- **`characterDocs`** → mined for explicitly NAMED characters only (usually exactly
  one — the doc *is* that character; split into several only if it clearly names
  several). A classified doc with no explicit name still becomes **one** character (the
  classification asserts it is one) — never lost, never invented.
- **`settingDocs`** → the same, for named settings.
- **`uncategorizedDocs`** (the `select` bucket) → read strictly; produce an entity
  **only if a genuinely NAMED** character/setting is present. Lore/history/rules/
  atmosphere → **nothing** (0 is valid — no fallback).
- **`otherDocs`** → **LORE/GROUNDING ONLY**; never turned into entities (their text
  folds into the drafting grounding so drafts stay consistent with them).

Subjects are de-duped across docs in document order (uncapped). It never invents a cast
from thin air: no Extract-checked entity docs → no characters/settings.
`useStorylineCreator.build()` routes each kept doc to its bucket's list **with its
`extract` flag**, and `build_agent` mines only the Extract-checked docs before applying
the bucket policy above.

The **extract stage is parallel + fault-tolerant** (matching the drafting phase): the
per-doc extraction calls run through `concurrency.imap_unordered` bounded by
`authoringConcurrency` (connection pre-resolved once so worker threads never touch the
request `Session`), each at **LOW** reasoning effort (segmentation — faster, far less
JSON truncation) with a **strict, named-only** prompt (no inventing/expanding from
lore); an **unreadable uncategorized** doc is **retried once then skipped** (the build
continues and names it in a status line) instead of aborting the whole build with
`"The model did not return valid JSON."` — a classified character/setting doc instead
**falls back to one entity** so it is never lost; and a `BuildStatusEvent(stage="extract")`
streams **per doc** so the UI shows movement rather than freezing on "Reading docs…".
Cross-doc de-dup runs in **document order** (index slots) so the roster is stable
regardless of which extraction finished first. (The larger RAG-first ingestion + on-
demand ReAct redesign is the follow-up plan `docs/plans/rag-first-ingestion.md`.)

The page consumes the stream in `useStorylineCreator.build()`, accumulating into
`proposed` + `planConcepts`; the right pane (`WorldBuildPanel`) renders the cast/settings
as they arrive (a "drafting…" skeleton per not-yet-drafted concept), then becomes the
editable review.

**Real-time field feedback (presentational — no new backend events).** As those
events arrive, the page also surfaces *where it is*: `meta`/`primer` drive a
left-pane **active-field highlight** (`.velora-field-active`, via `useFieldReveal`),
each `character`/`setting` event marks the **active card** in `WorldBuildPanel`
(`activeEntity`), the `status` `stage` feeds a **`ProcessProgress`** stepper
(metadata → primer → stats → docs → cast → settings), and an in-band `error` (or a
thrown stream) raises a **top-right error toast** (`useToast`). This is a frontend
presentation layer over the existing stream — the NDJSON contract is unchanged.
The all-at-once draft endpoints (character/setting/scenario drafts, voice/stats,
portrait/scene-art prompts) reuse the same primitives via a **choreographed reveal**
in `useLibraryState` (fields filled one at a time after the JSON lands; reduced-motion
fills at once) plus per-surface progress + error toasts. **Images render as part of the build** (`renderProposalImages`, best-effort,
skipping entities that already have one) — but only after a ComfyUI **status preflight**
confirms the server is actually reachable (`imagesAvailable` just means a URL is
configured), and a **circuit breaker** stops on the first failed render so a stopped
ComfyUI never produces a 502-per-entity storm. The image-gen endpoints are id-agnostic
so no persistence is needed yet; the **commit** then attaches those URLs (and renders any
still missing, with the same one-failure-then-stop guard). Hitting *Create World*
mid-render aborts the build's image loop (no double-render, no race). The non-streaming
`/build` collector remains for back-compat.

## Context Document Flow (the triaged RAG corpus)

```
New Storyline page → pick an upload target (Uncategorized / Character / Setting /
  Other + Draft/RAG/Extract defaults) → drop .txt/.md (read in-browser)
  → files land pre-categorized into that bucket (a whole batch at once, no triage)
  → leftovers left Uncategorized → POST /storylines/triage/stream (Uncategorized only)
      → per file: status {name,index,total} → item {category, includeDraft, includeRag,
        includeExtract} (Extract suggested conservatively, default off)
      → each row fills in LIVE (the active file shows a "classifying…" badge)
  → author reviews the buckets (Characters / Settings / Other) + Draft/RAG/Extract flags
  → on commit: POST /storylines/{id}/context-docs/bulk persists the corpus
      → ContextDocument rows (content stored verbatim, char_count cached)
```

The author can **bulk-categorize on upload** — choose a bucket (and the Draft / RAG /
Extract defaults) once, then drop a folder of e.g. character sheets and they all land as
Characters with no triage. **Extract is opt-in (default off)** — it is a separate per-doc
check-off (like Draft/RAG) that gates whether **Build the whole world** mines a file for
named characters/settings; a new storyline never auto-extracts. **Triage** then sweeps only what's still **Uncategorized**,
leaving the manual buckets alone. Triage runs **per file** (one LLM call each) so the
panel sorts documents in front of the author; the batched `POST /storylines/triage`
remains for back-compat. A per-doc failure falls back to `other`/RAG-on without
aborting the run.

The **context budget** (the inline grounding cap + the meter on the page) is **32000
characters** (`_common.DOCS_CAP` / `readDocs.DOCS_CHAR_CAP`; ~8000 tokens), raised from
the original 8K so larger lore/corpus batches can ground generation.

This is the **persistence seam** for retrieval: the documents are durably stored
per storyline and survive reload. The **Hybrid RAG** (see `docs/rag.md`) now reads
`content` at runtime — `includeRag` docs are embedded on save and retrieved by the
authoring agents. `includeDraft` docs additionally ground the creation-time
generation inline (not retrieved, capped at 32K characters). `includeExtract` is the
build-time opt-in — persisted so a re-opened storyline remembers which docs to mine
when **Build the whole world** is re-run; it has no runtime/retrieval effect.

## Story Graph Flow (Neo4j substrate)

```
Write (authoring) — on Character/Setting create/edit/delete:
  routes → services/crud (commit to Postgres)
    → graph_writer.sync_character / sync_setting / remove_node  (best-effort, after commit)
        → validate the instance against the Type Registry (§6.5)
        → neo4j.write_session → MERGE (:Node {id}) SET dynamic label + metadata (§6.2)
  (graph down/disabled → logged + skipped; CRUD still succeeds)

Read (scenario load) — GET /api/scenarios/{id}/graph:
  routes/scenarios → graph_reader.scenario_graph
    → ensure_scenario_materialized: upsert the cast + setting (+ present_at edges)
      from Postgres into Neo4j (idempotent; so the seeded world appears on first load)
    → neo4j.read_session (READ access mode, §7.4) → parameterized Cypher templates (§7.2)
    → { available, scenarioId, nodes[], edges[] }   (available:false when off/unreachable)
```

The **Type Registry** (`graph_type_definitions` in Postgres) is the semantic
source of truth — what node/edge types exist, their field schema, and edge valence
(§1.4); Neo4j holds the instances. Built-in types (§5) are global + immutable; users
add per-storyline types via `POST /storylines/{id}/graph/types`.

The **cold-path turn-writer** (§8) now runs after a turn streams (`services/turn_writer.py`,
called by `turn_engine.run_turn` once the last event is yielded — never blocks the player):
on **consequence turns** it routes each consequence by the "…toward whom?" rule (relational
target → an edge with a reified `:Consequence` node as shared provenance; no target → a stat,
already applied + clamped on the hot path), and appends an `:Event` node (`occurred_at` the
setting) so the moment is traversable + RAG-indexable. Best-effort: no consequences, or Neo4j
disabled/down → a clean no-op (Postgres stays canonical). **Deferred seams:** the vector
entry-point (§7.1) and Text2Cypher (§7.3). See `docs/story-graph-neo4j.md`.

The **read-time reflection interlude** (Band 4, `services/reflection.py` + `agents/reflection_agent.py`)
runs after the same stream: each character reflects *while the player reads* and writes a short,
overridable **interior state** (`disposition` + retrospective + branch-keyed stances) to Redis at
`interior:{session}:{character}` (`memory/interior.py`, volatile — never written to the graph).
Band-1 assembly reads it back next turn (`CastMember.disposition` → the generation prompt's HEAD),
so a character re-enters already carrying the shift. In a crowd (N>2) reflection is **universal**
(silent watchers update too); a two-hander reflects only who spoke. It is off the hot path, runs the
cast **concurrently** (`services/concurrency.run_all`, capped by `TURN_MAX_CONCURRENCY`), and — with
`TURN_ASYNC_FINALIZE` on — is dispatched to a background worker so the stream closes immediately
(`concurrency.submit_background`; inline + deterministic by default / on SQLite). Multi-party turns
also add a **live speaker queue**: a high-impact beat (Σ|stat delta|) re-consults the Director
mid-turn (`director_agent.rerank`) and **cascades** a disposition refresh to the not-yet-spoken
(`reflection.refresh_dispositions`, width scaled to impact), and a **consistency guard**
(`services/consistency.py`) checks each later line against the established beats before it streams,
regenerating once on a clear contradiction. All best-effort (Redis/LLM down → the turn still runs).

**Reactive Turn Director (Produce band overhaul).** The player's line is first **interpreted**
(`agents/intent_agent`) into narrate / address / **puppet** / whole-group intent; a puppeted
character then *performs* the direction in its own voice (not a bystander answering the player).
A **ReAct planner** (`agents/planner_agent.next_beat`) drives the turn beat-by-beat — after each
beat it re-decides the next (a character speaks/acts, the narrator sets context, or the turn ends).
The back-and-forth is bounded by the scenario's **`max_turns`** (a hard per-scene ceiling on
**every emitted beat — character replies AND narrator beats** — for one player message, default
**5** — the loop ends there even if the planner would continue; the narrated open and puppet
performances count too; `TURN_MAX_BEATS`/`2*cast+6` remains a secondary runaway backstop). The
planner leans on **narration to PROGRESS the scene** to the next beat (especially in action) —
narrating what the characters are *doing* and carrying an action through to its consequence — and a
character **speaks only after** the scene has moved and has a genuine point-of-view reaction, so
characters stop over-talking; a **cold scene open** with no directed character is narrator-led. Each
character always **`<thinking>`**s (a real in-voice deliberation — a short paragraph in their own
terminology at turn effort **MEDIUM**, streamed `private_to_user` and kept out of `turn_beats`), but a
spoken line is **optional** — in an action moment they act or simply think with no forced dialogue.
**Situational voice adaptation:** the `<thinking>` step **appraises the moment first** (how grave/light,
what changed, how much danger or feeling is in the air) before reasoning toward a response, and the
output contract's manner-adaptation rule makes personality **constant** while manner **adapts** — the
habitual act (constant quips, needless cruelty, forced levity) drops when the moment turns grave, and
the character's own state + the scene's mood (restated as a recency "read the moment" cue in the prompt
TAIL) reach their voice. The between-turn **`disposition`** carries the resulting emotional/situational
state (shaken, grieving, afraid, relieved) forward, so an adapted manner persists rather than snapping
back to the default next beat. The
character conditions on the scene's **`context_beats`** most-recent beats (5–100; `assembler` fetches
that depth from the Redis buffer, which retains up to `turn_buffer_size` = 100). At the **end of
every turn**, up to the scenario's **`suggestions_count`** (0–4; `0` disables) follow-up suggestions
are generated from the **recent beat sequence** (`director_agent.propose_branches(count=…)`, which
feeds the last ~6 beats via `_recent_sequence` **in chronological order**, newest last) and emitted
as `branch_choices` — count-driven, no longer gated on the planner's rarely-set `needsBranch` flag.
Suggestions are **situation-based** (what happens next from a general, story-wide perspective, not a
character's spoken line), must **continue the story FORWARD from the latest beat** (never repeat,
undo, or rewind events already shown — the fix for suggestions that latched onto earlier beats), and
are written to **match the player's own recent tone/pace** (`director_agent._player_voice`). **Selecting a suggestion** no longer submits a turn: the story
player **writes its text into the composer** for the player to review, edit, and send as an ordinary
`text` turn — so the chosen text itself carries the intent (the earlier open-ended `guidance` steer
is retired). Each character reply is grounded in its **graph relationships** to whom it addresses
(`graph_reader.relationship_context` — direct edges + 2-hop shared links, folded into the prompt). Relationships are **seeded from the
cast bios** into the graph on a session's first turn (`services/relationships.ensure_seeded` +
`agents/relationship_agent`) and **evolve in play** via a `relationship_update` block →
`validator.validate_relationship` → a relational consequence the cold path writes as a directed edge.
`GET /play/{id}/relationships` exposes the live edges for the story player's Relationships panel.

### Scene presence (who's still in the scene)

A character who has died or left keeps being an active member of the static cast (`cast_ids`)
unless the loop knows they're gone — so the engine tracks **runtime presence** per character.
Presence is **derived from the session's event log** (`services/presence.current_presence` folds
the session's `character_status_change` events, latest per character; default `present`) — no new
column or Redis dependency, so it survives reload and rehydrates through the same reducers the
transcript uses. The `assembler` stamps each `CastMember.presence`, and only **`present`** members
are **selectable**: `planner_agent` builds its roster from present members only (a dead/departed/
unconscious one never appears, so it can't be picked), and the fallback + reflection paths skip
them too. Four detection paths feed one store (all `auto: true`): (1) a `health`-keyed stat clamped
to its floor → `unconscious` (`presence.vital_status_for`, in `_apply_stat_change`); (2) the
planner's **`exit`** beat ratifying a death/exit the story already showed; (3) a character's
self-declared **`<type:presence_change>`** block (`validator.validate_presence`, gated by
`presence.can_transition`); (4) the manual **`POST /play/{id}/presence`** override (`auto: false`).
Each emits a `character_status_change` event; `turn_engine._apply_presence_change` also **mutates
the in-memory cast member** so the removal takes effect the very next beat. The story player folds
the event into `presenceByChar` (`turn-stream.applyPresence`), and `CastRail` groups present vs.
out-of-scene members, strikes the dead, and offers a per-character presence `<select>` (manual
control). An `auto` change raises an **Undo** toast that restores the character to `present`.

## Hybrid RAG Flow

### Ingest-on-save

```
CRUD write (character / setting / scenario / context-doc create or update)
  → services/crud (commit to Postgres)
  → indexer.sync_* hook (best-effort, after commit)
      → entries.py: entity → LoreEntry (Frontmatter + body)
      → serializer.py: prefix-fusion → dense embed text + BM25 vocabulary text
      → embedder.py: FastEmbedEmbedder (fastembed bge-large) or HashEmbedder (offline)
      → store.py: Qdrant upsert — named dense + sparse vectors, content-hash idempotency,
          uuid5 point id, storyline-scoped payload
  (Qdrant down/disabled → logged + skipped; CRUD still succeeds)
```

### Retrieval (agent draft)

```
agents/character_agent / setting_agent / scenario_agent → draft call
  → agents/_common.rag_block(db, storyline_id, query)
      → retriever.py: build_filter (storyline_id payload pre-filter)
      → store.py: dense search + sparse (BM25) search
      → retriever.py: RRF fusion (k=60) over both ranked lists → top-N entries
      → format: name · type · body excerpts → bounded grounding block
  → injected into the authoring prompt alongside world_context + docs_block
```

### Delete-from-index

```
CRUD delete (entity or context-doc)
  → indexer.remove_* hook (best-effort)
      → store.py: Qdrant delete by uuid5 point id
  storyline delete → store.py: delete all points for storyline_id (drops the whole corpus)
```

### Reindex progress stream

```
Storyline editor footer → "Re-embed" → POST /api/storylines/{id}/rag/reindex/stream
  → indexer.iter_reindex_storyline
      → per entry: { "stage": "embedding", index, total, name, type }  (NDJSON)
      → terminal: { "stage": "done", indexed, skipped, total, available }
  → frontend: live "Embedding i / N" progress banner updates
```

See `docs/rag.md` for the full pipeline, component reference, and configuration.

## State Ownership

- Authoritative state: backend (Postgres) — validated server-side, stats clamped.
- Live/ephemeral state: Redis (active scenario).
- UI/interaction state: frontend only (panel toggles, theme, draft input).
- Never trust client-sent state as authoritative; always re-validate on the backend.
