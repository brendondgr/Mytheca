# Velora — Data Flow

How data originates and moves through Velora. The streaming/event path is first-class.

> **Current implementation.** The **Library** is now backend-backed: it reads from and writes to the FastAPI CRUD API via `web/frontend/lib/api.ts` (hand-rolled fetch, await-then-apply), so storylines/characters/settings/scenarios **persist** in Postgres. The backend is seeded with the Embergate world (`web/backend/app/core/seed.py`) so the app looks the same. The **Story player** still runs on in-memory seed data (`web/frontend/features/story-player/scene-data.ts`) — the streaming path below is the planned design. (TanStack Query is still deferred; the hand-rolled client suffices for this CRUD surface.)

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
`id` (incremental `text` chunks, `done` flips true last; a `character_action` immediately
followed by that speaker's dialogue merges into one beat); an `internal_thought` renders as
its own distinct "thinking" bubble (never merged into a speech beat); `state_update` /
`branch_choices` drive the side panels. A scene seeds **narrator-only** (no character speaks
before the player acts), and selecting a branch forwards its `outcome` so the backend plays
the chosen path out. The composer is locked while a turn streams (in-flight guard); a
mid-stream failure surfaces the terminal `error` frame.

The hot path is **read-only** — all mutation (durable consequences, edges) defers to the
cold-path turn-writer (a later phase); stat changes are clamped during validation.

## Stat Change Flow

```
Director/character agent proposes a change (stat key, delta or value, reason)
  → emitted as a state_update event
  → Validator confirms the stat exists and clamps the result to [min, max]
  → event streamed to the UI
  → Stats panel updates; narrator may reference the new state next turn
```

The change carries a **reason**, giving a free audit trail ("Health −25: struck by the falling beam") useful for debugging the model and for showing the player *why* a number moved. Current stat values plus their guidance files feed back into agent context each turn, so a near-dead character fights weakly and a high-strength character can plausibly force a door.

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
```

The LLM API key is **write-only**: stored in the `app_settings` row, never
returned to the browser (reads expose `hasApiKey` + a masked hint). Model listing
and the connection test run on the backend so they work against `localhost:*`
servers that don't send CORS headers, and so the key never reaches the client.
When the multi-agent brain lands it reads the same stored config.

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
        (voice & tone comes FIRST — derived from the drafted prose before stats; best-effort → [])
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
      status → extract→ every attached doc is mined for its distinct subjects
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
found in the attached context docs** — but each doc is **mined** for *every* distinct
subject it names (an extraction pass per doc), so a single markdown file describing
several characters yields several cards instead of being lost or collapsed into one. A
mixed/`other` doc yields both characters and settings; a pure-lore doc yields none (it
still grounds the world). Subjects are de-duped across docs (uncapped). It never invents
a cast from thin air: no docs → no characters/settings. `useStorylineCreator.build()`
sends **every** kept doc — `characterDocs`/`settingDocs` (their triage bucket) plus
`otherDocs` (everything else, mined for both) — and the backend extracts the roster.

The page consumes the stream in `useStorylineCreator.build()`, accumulating into
`proposed` + `planConcepts`; the right pane (`WorldBuildPanel`) renders the cast/settings
as they arrive (a "drafting…" skeleton per not-yet-drafted concept), then becomes the
editable review. **Images render as part of the build** (`renderProposalImages`, best-effort,
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
  Other + Draft/RAG defaults) → drop .txt/.md (read in-browser)
  → files land pre-categorized into that bucket (a whole batch at once, no triage)
  → leftovers left Uncategorized → POST /storylines/triage/stream (Uncategorized only)
      → per file: status {name,index,total} → item {category, includeDraft, includeRag}
      → each row fills in LIVE (the active file shows a "classifying…" badge)
  → author reviews the buckets (Characters / Settings / Other) + Draft/RAG flags
  → on commit: POST /storylines/{id}/context-docs/bulk persists the corpus
      → ContextDocument rows (content stored verbatim, char_count cached)
```

The author can **bulk-categorize on upload** — choose a bucket (and the Draft / RAG
defaults) once, then drop a folder of e.g. character sheets and they all land as
Characters with no triage. **Triage** then sweeps only what's still **Uncategorized**,
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
generation inline (not retrieved, capped at 32K characters).

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
beat it re-decides the next (a character speaks/acts, the narrator sets context, or the turn ends),
so speakers are **unbounded** (a whole-group direction walks the entire cast; `TURN_MAX_BEATS` is a
runaway backstop) — replacing the old capped one-shot Director + rerank/cascade. The planner is
biased toward **narration** between speakers, and a **cold scene open** with no directed character
is narrator-led (the engine emits an opening narration first; no character speaks unprompted).
Selecting a branch sends its `outcome`, which opens the turn with a fuller **progression**
narration (`narrator_agent.interstitial(long=True, lead=…)`) that plays the choice out before the
cast reacts. Each character reply is grounded in its **graph relationships** to whom it addresses
(`graph_reader.relationship_context` — direct edges + 2-hop shared links, folded into the prompt). Relationships are **seeded from the
cast bios** into the graph on a session's first turn (`services/relationships.ensure_seeded` +
`agents/relationship_agent`) and **evolve in play** via a `relationship_update` block →
`validator.validate_relationship` → a relational consequence the cold path writes as a directed edge.
`GET /play/{id}/relationships` exposes the live edges for the story player's Relationships panel.

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
