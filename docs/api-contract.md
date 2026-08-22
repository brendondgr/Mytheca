# Mytheca — API & Event Contract

The contract between the Next.js frontend and the FastAPI backend. Request/response schemas are owned by the backend (Pydantic, `web/backend/app/schemas/`). The live TypeScript mirror of the event schema and API types is hand-maintained in `web/frontend/lib/events.ts` and `web/frontend/lib/types.ts`, kept in sync with `web/backend/app/events/envelope.py` by hand; `web/shared/contracts/` is a reserved-but-empty seam (only a `.gitkeep`) for eventually formalizing that mirror. This document and those files must stay in sync.

**Status:** the Storyline / Character / Setting / Scenario CRUD groups, the stat endpoints, the **Options** (global settings + LLM endpoint proxy) group, the **Story Graph** (Type Registry + scenario subgraph read), the **Hybrid RAG** (status, reindex stream, query), and **Play** (turn streaming, presence, relationships, sessions) are **implemented** (`web/backend/app/routes/`, served under `/api`). Auth, the separate `GET /stream` fan-out seam, and Admin remain **planned**. Wire payloads are camelCase (`castIds`, `settingId`, `displayName`) to match `web/frontend/lib/types.ts`.

**Identifiers:** the two **URL-facing** ids are short, bare hex (no prefix) so they read cleanly in `/{storylineId}/{scenarioId}` — **Storyline = 8-hex** (`1a2b3c4d`), **Scenario = 4-hex** (`9f8e`), both collision-checked at create time (`services/crud.py`). All other entities keep prefixed ids (`c_…`, `s_…`, `stat_…`, `ev_…`). Ids are string primary keys, so hand-authored seed slugs (`embergate`, `maerin`) and any client-supplied id still pass through unchanged.

## Conventions

- Base path: `/api`.
- JSON request/response; auth via the backend-owned session/token (mechanism TBD — see `docs/architecture.md`).
- Standard error shape:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

- Validation errors return 422 with field-level details. Auth failures return 401; permission failures 403.

## Endpoint Groups

| Group | Endpoints | Notes |
| --- | --- | --- |
| Auth | `POST /auth/sign-up`, `POST /auth/sign-in`, `POST /auth/sign-out`, `GET /me`, `PATCH /me` | Backend owns session/token. |
| Storylines | `GET /storylines`, `POST /storylines`, `GET /storylines/{id}`, `PATCH /storylines/{id}`, `DELETE /storylines/{id}` | The world container; owns the baseline stat schema. Read/write shape: `id`, `title`, `genre`, `tagline` (one-line switcher descriptor), `premise` (nullable multi-paragraph human-facing world description), `worldPrimer` (nullable agent-facing runtime context — generated at creation, editable; see Authoring below), `symbol` (seal shape glyph shown left of the name, default `◆`), `symbolColor` (seal hex color, default `#C8862A`), `promptOverrides` (nullable JSON object `{registryKey: text}` — per-storyline writing-agent prompt overrides; coerced to `{}` when NULL on read; see Writing-Agent Prompt Overrides below). The list (`GET /storylines`) and single-get (`GET /storylines/{id}`) responses also include **`scenarioCount`**, **`characterCount`**, and **`settingCount`** (integers, default `0`) — computed via SQL COUNT subqueries so the header switcher always shows accurate totals for every world without loading full child arrays. Create/update responses return `0` for all three (newly created worlds have no children; clients re-fetch the list on next load). |
| Stat definitions | `GET /storylines/{id}/stats`, `POST /storylines/{id}/stats`, `PATCH /storylines/{id}/stats/{key}`, `DELETE /storylines/{id}/stats/{key}` | The world's universal stat schema, shared by every character. Freely add/edit/remove: `PATCH` edits name/description/range/bands (range narrowing re-clamps character values); `DELETE` prunes the stat's values from every character. Each definition carries labeled `bands` ("tickers"), each with an optional `{Character}`-templated `description` surfaced to the acting character at play time. |
| Characters | `GET /storylines/{id}/characters`, `POST /storylines/{id}/characters`, `GET /characters/{id}`, `PATCH /characters/{id}`, `DELETE /characters/{id}` | Belong to a storyline; each holds a stat block. Read/write shape: `id`, `name`, `role`, `color`, `mono` (derived), `traits`, `speech`, `goal`, `secret`, plus base-identity prose `appearance`, `background`, `personality` (all nullable), `portrait` (nullable relative `/media/...` URL of the generated WebP avatar), `portraitPositive` / `portraitNegative` (nullable ComfyUI prompt strings that produced the portrait — persisted so the author can tweak-and-re-render on re-edit), and `voiceSamples` (a list of `{ situation, sample, moment }` pairs — the character's voice & tone profile, each pair a previous situation paired with the character's *single* in-voice response to it (never a back-and-forth exchange); empty list when unauthored, derived from background/personality before starting stats and injected into the turn loop). **`moment`** tags which kind of moment the pair demonstrates — `"light"` \| `"neutral"` \| `"tense"` \| `"grave"`, or `""` for "any moment" (an unrecognized value is coerced to `""` rather than rejected). Only the pairs matching the beat's **register** (plus untagged ones) reach the turn prompt, so a character has a concrete exemplar of itself *not at rest*. |
| Settings | `GET /storylines/{id}/settings`, `POST /storylines/{id}/settings`, `GET /settings/{id}`, `PATCH /settings/{id}`, `DELETE /settings/{id}` | Places within a storyline. Read/write shape: `id`, `name`, `type`, `desc` (short base description), plus §4.1 Setting-node metadata `atmosphere` (sensory character), `features` (notable fixtures/points of interest), `currentState` (initial here-and-now), and `image` (nullable relative `/media/scenes/...` URL of the generated WebP establishing shot) — all nullable; `sceneArtPositive` / `sceneArtNegative` (nullable ComfyUI prompt strings that produced the image — persisted for re-edit); and `timeline` (append-only event log, **empty at authoring**, play-accrued; defaults `[]`). |
| Scenarios | `GET /storylines/{id}/scenarios`, `POST /storylines/{id}/scenarios`, `GET /scenarios/{id}`, `PATCH /scenarios/{id}`, `DELETE /scenarios/{id}` | The live situations; may add/override stats. Read/write shape includes `image` (nullable relative `/media/scenes/...` URL of the generated WebP scene art), `sceneArtPositive`, and `sceneArtNegative` (nullable prompt strings), plus four **per-scene play controls** set from the composer's scene-config menu: `maxTurns` (hard ceiling on the beats a player message produces — character replies **and** narrator beats — ≥1, default **5**; the loop may still end earlier), `suggestionsCount` (how many follow-up suggestions to offer at the end of a turn, 0–4, `0` disables, default **4**), **`contextPolicy`** (`"auto"` | `"fixed"`; `null` reads as auto) and `contextBeats` (5–100, default **14**). Under the default **auto** policy the transcript window fits itself to the model's real context budget each turn (`services/context_budget`) and `contextBeats` is **ignored**; under `fixed` the scene keeps its own depth. Asking the player for a beat count was asking a question only the app can answer, so the control is gone from the UI — what the scene actually reached is *reported* on the new `window` trace step (`windowBeats`, `windowSource` ∈ `detected|configured|fallback|fixed`, `droppedBeats`, `budgetTokens`), which also rides on the `assemble` step's payload. When `TURN_CONTEXT_COMPACTION` is on, beats that fall out of the window are folded into a rolling per-session summary and a **`compaction`** trace step reports it (`beatsFolded`, `throughSeq`, `summaryChars`); `SessionSummary` carries **`summaryThroughSeq`** so a reload knows where verbatim recall ends without a second request. The summary is cleared whenever history is rewritten at or below that seq (rewind, beat edit, beat re-roll), because a stale summary is worse than none. `contextBeats` still validates (an out-of-range value is a 422), because it remains a real setting under `fixed`, and `beatLength` (how much a **character** says in one beat — `"short"` 1–2 paragraphs, `"medium"` 2–4, `"long"` 5–6, each paragraph at most 3–4 sentences **not counting quoted dialogue**; default **`"medium"`**, which is the closest match to the behaviour before the control existed). `beatLength` is a strict enum: any other value is a **422**, so an unrecognised tier can never reach the prompt builder and silently do nothing. It governs character beats only — narration has its own sentence spec and is unaffected. Also includes **`directionVerbs`** — the scene's own one-tap direction verbs, appended to the built-in bar's groups: a list of `{label, group, text}` where `label` is the chip, `group` is a strict enum (`pace`|`tone`|`event`|`exit`, anything else a **422**, since the bar draws by group and an unknown one would be a verb that silently never renders) and `text` is the phrasing written into the player's direction box for them to edit. Both strings are required and non-empty, and the list is capped at **8** — the bar is a glance-and-tap surface. Nullable in the DB, so a scenario written before the column reads as `[]`. Also includes `promptOverrides` (nullable JSON object `{registryKey: text}` — per-scenario writing-agent prompt overrides, the innermost layer of the four-layer resolution chain; coerced to `{}` when NULL on read; see Writing-Agent Prompt Overrides below). |
| Context documents | `GET /storylines/{id}/context-docs`, `GET /storylines/{id}/context-docs/index`, `POST /storylines/{id}/context-docs`, `POST /storylines/{id}/context-docs/bulk`, `PATCH /context-docs/{docId}`, `DELETE /context-docs/{docId}`, `POST /context-docs/{docId}/links`, `DELETE /context-docs/{docId}/links` | **Implemented.** The persisted **triaged RAG corpus** for a world (written by the New Storyline page's Triage → commit; managed post-creation at `/storylines/[id]/documents`). Each doc carries a `category` (`character`/`setting`/`other`) and inclusion tiers `includeDraft` / `includeRag` / `includeExtract` (opt-in build-time mining, default off). Docs are **storyline-level** (Triage default) or **entity-scoped** — a doc with `entityType` + `entityId` reappears in that editor on re-edit and is removed (with its embedding) when the entity is deleted. Each doc also carries **provenance `links`** (which entities it is context *for* — build lineage + manual). `GET /storylines/{id}/context-docs` accepts `?entityType=&entityId=` (owned scope) or `?linkedEntityType=&linkedEntityId=` (provenance). Docs with `includeRag` are embedded on save (hybrid RAG). `GET …/context-docs/index` is a **name-only** listing (`id`, `name`, `category`, `charCount`, `entityType`, `entityId` — no `content`) in the same order, backing the story player's `@` file-tagging menu so opening it never ships document bodies. See Context Document Shape below. |
| Hybrid RAG | `GET /storylines/{id}/rag/status`, `POST /storylines/{id}/rag/reindex/stream`, `POST /storylines/{id}/rag/query` | **Implemented.** Vector-store status, NDJSON reindex progress stream, and debug retrieval query for a world's corpus. Best-effort (`available: false` when Qdrant is down/disabled). See RAG Shapes below. |
| Story Graph | `GET /scenarios/{id}/graph` | **Implemented.** Loads the scenario's Story-Graph subgraph (cast + setting nodes + the edges among them), read live from Neo4j (§7.2). Returns `{ available, scenarioId, nodes[], edges[] }`; `available` is `false` with empty lists when the graph is disabled/unreachable (best-effort). See Story Graph Shapes below. |
| Graph types | `GET /storylines/{id}/graph/types`, `POST /storylines/{id}/graph/types`, `PATCH /graph/types/{typeId}`, `DELETE /graph/types/{typeId}` | **Implemented.** The Type Registry (§1.4): list the node/edge types visible to a storyline (global built-ins + its own user types), and register/patch/delete user-defined types. Built-in types are immutable (409). Edge types require a `valence`; user types default `status: experimental`. |
| Authoring | `POST /storylines/draft`, `POST /storylines/primer`, `POST /storylines/triage` | **Implemented.** The agent process of building a storyline: draft metadata from a one-sentence seed, generate the agent-facing World Primer, and **triage** dropped reference docs into Characters / Settings / Other with Draft/RAG inclusion (see Authoring Shapes below). Run over the configured LLM; no retrieval. |
| World population | `POST /storylines/{id}/populate/stream` | **Implemented.** NDJSON. Fills a newly-created world with a generated cast + settings: plan a roster, draft each entry through the existing character/setting draft agents, persist it, and stream `status` / `entity` / `error` / `done` frames. Artwork is opt-in and best-effort; a per-entity failure never aborts the run. Pre-flight `404`/`400`. See World Population Stream below. |
| Authoring (live) | `POST /storylines/triage/stream` | **Implemented.** NDJSON (`application/x-ndjson`) streaming triage so the New Storyline page renders the classification **as it happens** — one `status`+`item` per doc then a terminal `done`. Pre-flight failures (no context / unconfigured LLM) return a normal `400` before the stream opens; a per-doc failure falls back to `other`/RAG-on rather than aborting. See Live Authoring Stream below. |
| Storyline agent (editing) | `POST /storylines/agent/create/stream`, `POST /storylines/{id}/agent/edit/stream`, `POST /storylines/{id}/agent/apply` | **Implemented.** The conversational, scope-aware agent that **replaced "Build the whole world"** on the storyline create/edit pages: chat about the storyline's own fields (title/genre/tagline/premise/World Primer/stat schema) within an author-set **write scope**, review a proposed `StoryPlan`, then approve to write it (create: fills the form; edit: applies through validated writes). Nothing is written before `…/agent/apply`. See Storyline Agent Shapes below. |
| Character authoring | `POST /characters/draft`, `POST /characters/portrait-prompts`, `POST /characters/portrait`, `POST /characters/voice-samples`, `POST /characters/starting-stats` | **Implemented.** The agentic Character Creator (prep phase): draft a character's base identity from a seed (optionally grounded in the world + dropped docs), write watercolor portrait prompts, render the portrait via ComfyUI (saved as WebP, served at `/media`), derive a **voice & tone profile** (situation → sample-response pairs) from the character's prose, and propose starting stats keyed to the storyline's stat schema. Produces §1 *node properties* only — no graph. See Character Authoring Shapes below. |
| Setting authoring | `POST /settings/draft`, `POST /settings/scene-art-prompts`, `POST /settings/scene-art` | **Implemented.** The agentic Setting Creator (prep phase): draft a setting's base description + current state from a seed (optionally grounded in the world + dropped docs), write watercolor establishing-shot prompts, and render the scene art via ComfyUI (saved as WebP under `/media/scenes`). Produces §4.1 Setting-*node properties* only — never the play-accrued event timeline or graph edges. See Setting Authoring Shapes below. |
| Scenario authoring | `POST /scenarios/draft`, `POST /scenarios/scene-art-prompts`, `POST /scenarios/scene-art` | **Implemented.** The agentic Scenario Creator: draft a scenario (title/genre/tone/goal/opening) from a seed, plus a **valid cast + setting chosen from the active world's real roster**. The model returns names from a numbered roster; the agent resolves names→ids server-side, **dropping** unknown cast and falling back to `""` for an unmatched setting — so the draft never invents or dangles a reference. Scene-art prompts and image generation follow the same watercolor pipeline as Setting authoring. Declared above `/scenarios/{id}`. See Scenario Authoring Shapes below. |
| Media | `GET /media/portraits/{file}.webp`, `GET /media/scenes/{file}.webp`, `GET /media/moments/{file}.webp` | **Implemented.** Read-only static mount (not under `/api`) serving generated character portraits, setting scene art, and in-play scene images from `MEDIA_DIR`. |
| Options | `GET /options`, `PATCH /options/llm`, `PATCH /options/library`, `POST /options/llm/models`, `POST /options/llm/test`, `GET /options/llm/backend`, `GET /options/llm/context-window`, `PATCH /options/comfy`, `GET /options/comfy/workflows`, `POST /options/comfy/status`, `GET /options/media/orphans`, `POST /options/media/cleanup`, `PATCH /options/prompts` | **Implemented.** Global settings (LLM endpoint + library defaults + ComfyUI image generation + writing-agent prompt overrides), read-only inference-engine detection (`/llm/backend`), context-window probe (`/llm/context-window`), and orphaned-media maintenance (`/media/orphans`, `/media/cleanup`). Prefix is `/options` (the Setting entity owns `/settings`). |
| Play | `POST /play/{scenarioId}/turn` | **Implemented.** Submit a player turn; the response body **is** the NDJSON event stream (`application/x-ndjson`, one event per line). Body: `{ text, directedAt?, sessionId?, mode?, trace?, outcome?, povCharacterId?, guidance?, taggedDocIds?, continuation? }` (omit `sessionId` to start a session). **A turn no longer requires `text`** — it is valid when **any** of `text`, `guidance`, `outcome` or `continuation` is present, and 400s with *"Say something, direct the scene, or press Continue."* otherwise. `continuation: true` with empty `text` is the **Continue** control: the scene runs on with no line from the player. `guidance` with empty `text` is a **direction-only** turn: the player steers without speaking — necessary under POV, where the message box is the character's own words and can no longer double as direction. The two are distinguished in the trace (`turn.data.directionOnly`) and in the export (`_(direction only)_` vs `_(let the scene continue)_`), and a direction-only turn's `guidance` becomes the play-through's tray label when no spoken line exists yet. A text-less turn still writes its `user_turn` row (so it keeps its trace grouping and its place in the export), but pushes **nothing** into the recent-turn buffer — a blank player beat would sit in the transcript window of every later prompt — seeds no `turn_beats`, and **skips the intent call** entirely, since classifying an empty string invites the model to invent an ask the player never made. **`directedAt`** now has a UI producer: the composer's `@` menu offers the **present cast** alongside the storyline's context files, and the first character `@`-named in the *message* box becomes `directedAt` (a character named in the *direction* box is the subject of the direction, not the addressee, so it does not). No backend change — the engine already appended it to `intent.addressed` and promoted `freeform` to `direct`. **`povCharacterId`** (Player POV) makes the player's line the chosen present character's own beat — seeded/persisted as a `character` line, `data.pov` on the `user_turn`, and that character locked out of the AI roster (see Turn Stream below). **`guidance`** is the narrator direction for the turn (the composer's second box, POV only) — see *Scene direction* below. The engine **interprets the line** (narrate / address / **puppet** a character / whole-group), then runs a **ReAct planner** that decides the next beat after each one — a character speaks/acts (in their own voice; a puppeted character *performs* the direction), the narrator sets context, or the turn ends. Speaker order is dynamic; the back-and-forth is bounded by the scenario's **`maxTurns`** (a hard ceiling on **every emitted beat — character replies and narrator beats** — so the loop ends there even if the planner would continue). A **cold scene open** with no directed character is **narrator-led**. At the end of the turn, up to **`suggestionsCount`** follow-up suggestions (0–4) are generated from the **most recent line**, written as **situation-based** moves from a general perspective matched to the player's own tone, and emitted as `branch_choices`; **selecting one writes its text into the composer** for the player to edit and send (it does not auto-submit) — a suggestion is a starting point, and the player's own wording is the point of the app. Each chip also carries **"Play it out"**, which submits it immediately as a direction-only turn with **`outcome`** set: the turn then opens with a fuller *progression* narration that plays the choice out over several beats rather than answering it in one line. `outcome` had been engine-supported all along with no UI producer; this is it. **`mode` is deprecated and inert** — it reaches exactly one place in the engine (the `turn` trace payload) and changes nothing about how a turn runs. Still accepted so no caller breaks, and deliberately never exposed: whether the narrator sets context between beats is the planner's call, from the scene. See `docs/architecture.md`. Character replies are grounded in their **graph relationships** (direct + 2-hop). Pre-flight failures (unknown scenario → 404, empty text → 400, bad session → 404/400) return a normal error envelope before the 200 stream opens; a mid-stream failure is the terminal `{ "type": "error", "message": "…" }` frame. See Turn Stream below. |
| Scene image | `POST /play/{scenarioId}/moment/stream` | **Implemented.** The player's **Create image** action at the foot of the transcript: paint the moment the scene is in. The response body **is** an NDJSON stream. Body: `{ sessionId, beats?, prompt?, negative? }` (`beats` narrows the look-back window, clamped 2–40, default 8). **`prompt`** is the player's own wording from the enlarged view's editable prompt: when present the `moment_agent` call is **skipped entirely** — they have already said what they want painted, and re-deriving it would cost a call and override them. It is still passed through `moment_agent.strip_names`, so the appearance-not-names guarantee (`EXP-2026-08-002`) is not bypassed by hand-written input. A blank `prompt` falls back to the agent. The `moment_stage` frame sequence is unchanged either way, so the client's staged progress keeps working. Purely additive — this produces a **new** beat and removes nothing. Two stages, streamed as `{ "type": "moment_stage", "stage": "prompt" \| "render", "message", "positive", "caption" }` — `agents/moment_agent.py` writes an appearance-first ComfyUI prompt from the recent beats, the present in-frame cast, and the place; `services/scene_moment.py` renders it at a **landscape 1216×832** frame with a fresh seed, writes the WebP to `/media/moments`, and persists a `scene_image` event, which is the stream's last line. The `render` stage frame doubles as the keep-alive heartbeat. Pre-flight failures (unknown scenario → 404, unknown/mismatched session → 404/400, a scene with no beats yet → 400, unconfigured ComfyUI or model → 400) return a normal error envelope before the 200 opens; a mid-stream failure is the terminal `error` frame. |
| Presence | `POST /play/{scenarioId}/presence` | **Implemented.** Manually set a character's scene presence (the cast-rail control + its undo). Body: `{ sessionId, characterId, status }` (`status` ∈ `present`\|`unconscious`\|`departed`\|`left`\|`dead`). Persists a `character_status_change` event (`auto: false`) on the session and returns it in the wire-envelope shape; folds into presence like an engine-driven change and survives reload. A manual override is **not** bound by the engine's transition guard — the player may resurrect a `dead` character. 404 (unknown scenario/session/character), 422 (unknown status). Undo = the inverse call. |
| Relationships | `GET /play/{scenarioId}/relationships` | **Implemented.** The scenario's live character↔character relationships from the story graph — `{ relationships: [{ source, sourceName, type, target, targetName, reason }] }`. Best-effort: an empty list when the graph is off/unreachable (the story player keeps its seed placeholder). 404 only when the scenario is unknown. |
| Sessions | `GET /play/{scenarioId}/sessions` | **Implemented.** Every saved play-through of a scenario, most-recently-played first (the play-through tray) — `{ sessions: [{ id, scenarioId, createdAt, updatedAt, closedAt, turnCount, preview, name, parentSessionId, forkSeq }] }`. `preview` is the first **non-empty** player line (a text-less *Continue* turn writes a blank one); `name` is the player's own label and `null` falls back to `preview`; `parentSessionId` + `forkSeq` are set together on a forked play-through (a branch, or a rewind's pre-cut snapshot) and record which session it came from and the parent `seq` the copy ran through, inclusive. 404 when the scenario is unknown. |
| Start a play-through | `POST /play/{scenarioId}/sessions` | **Implemented.** Opens a **fresh, empty** play-through and returns its `SessionSummary` (201). Body `{ name? }`. It deliberately never touches the scenario's existing sessions — before it existed the only way to open a new one was to send a turn with no `sessionId`, which the story player never did, so a scenario could only ever hold one story. 404 when the scenario is unknown. |
| Rename a play-through | `PATCH /play/{scenarioId}/sessions/{sessionId}` | **Implemented.** Body `{ name }`; a blank or whitespace-only name clears the label and restores the `preview` fallback. Returns the updated `SessionSummary` and bumps recency. 404/400 on unknown/mismatched session. |
| Delete a play-through | `DELETE /play/{scenarioId}/sessions/{sessionId}` | **Implemented.** 204. Deletes the session together with its `events` and `turn_traces` rows — explicitly, not via the FK cascade, because SQLite does not enforce foreign keys unless `PRAGMA foreign_keys` is on and the behaviour would otherwise differ between Postgres and the test/dev database. The Redis buffer is cleared best-effort. A play-through forked *from* this one survives and simply loses its recorded lineage (`parentSessionId` is `ON DELETE SET NULL`). 404/400 on unknown/mismatched session. |
| Re-roll a beat | `POST /play/{scenarioId}/sessions/{sessionId}/beats/{eventId}/reroll` | **Implemented.** NDJSON; the response body *is* the stream. Body `{ scope: "beat"|"turn", expectedSeq? }`. **`beat`** re-generates that beat alone, in place — the new take streams into the **same event id and seq**, so the transcript's shape is byte-identical afterwards — against the context the beat originally saw (`turn_setup.context_for_replay`, walking persisted rows rather than the Redis window, which the beat may have fallen out of). The accompanying `internal_thought` is replaced too, not appended. **Consequences are not re-applied**: a re-take changes the wording, not the world, and applying the new take's stat/relationship/presence changes would drift a character further on every re-roll. **`turn`** truncates to the turn boundary and replays the player's persisted line through the ordinary loop — a composition of rewind and the turn engine, and it keeps no takes (a per-beat pager cannot express "these four lines, or those four"; branch before re-running a turn). The stream leads with a **`beat_reroll`** transport frame `{ type, eventId, take }` telling the client to clear that beat, since the deltas that follow re-emit the same id and would otherwise append to the take being replaced. |
| Choose a take | `PATCH /play/{scenarioId}/sessions/{sessionId}/beats/{eventId}/take` | **Implemented.** Body `{ take }`. Flips a re-rolled beat to one of its kept versions, mirrors it into `data.text` and rebuilds the buffer so the cast reads the take the player is reading. 422 on a beat with a single version, or an index that does not exist. |
| Model health | `GET /options/llm/health` | **Implemented.** `LlmHealthResponse { state, backend, model, checkedAt, detail }` where `state` ∈ `reachable` · `model_missing` · `unreachable` · `unconfigured`. **Four states, not a boolean**, because they are four different problems with four different fixes: an endpoint that is *up while the configured model is absent* produces exactly the same silence as one that is down, and the first is a typo in Options while the second is a dead process. A `GET /models` against the same TTL-cached probe machinery `detect_backend` uses, so the header can poll it at ~1 request/minute; never raises (a transport failure or a `>= 400` is `unreachable`, and an endpoint listing no models is `reachable` rather than falsely accusing the setting). Without it a player on a local model learns their endpoint died by sending a turn and waiting out `LLM_GEN_TIMEOUT_SECONDS` — five minutes to be told nothing. |
| Recap the scene | `POST /play/{scenarioId}/sessions/{sessionId}/recap` | **Implemented.** Body `{ throughSeq? }` (defaults to the whole scene) → `{ text }`. "Tell me what happened", in prose. Runs the **same** `agents/recap_agent.summarize_history` compaction uses — deliberately not a second summarisation path, because two model calls with two prompts drift apart in tone and in what each counts as a fact worth keeping, and the recap a player reads would then disagree with the memory the cast reads. Incremental in the same way: when the requested range starts above the stored summary's boundary, that summary is the starting point. Capped at 120 beats per call. **Never 500s** — an unreachable model, no configured model, or an empty session each return `{ "text": "" }`, because a recap is a convenience and must not be able to fail a page. 404 on an unknown session. |
| What the scene knows | `GET /play/{scenarioId}/sessions/{sessionId}/context` | **Implemented.** The player-facing read of the last turn's context — the same facts as the Inspector, written for someone playing rather than someone debugging. `SceneKnowledgeResponse`: `windowBeats`, `windowSource`, `droppedBeats`, `budgetTokens`, `promptTokens` (nullable — the endpoint's own count, the one non-estimated number), `taggedNames[]`, `retrieval {fired, reason, matched}`, `relationships[]`, `direction {text, items[], delivered[], outstanding[]}`, `summary {text, throughSeq, updatedAt}`. Assembled from the **already-persisted `TurnTrace` rows of the most recent turn** plus the session's summary columns — so it costs the turn path nothing and works on a *resumed* scene, which is exactly when a player most wants to ask what a long session still remembers. Only the latest turn: "what does the scene know **now**" is a question about the state the next beat will be written against. A session with no turns answers with zeroes, **not** a 404 — "nothing has happened yet" is a legitimate question. 404 on an unknown session. |
| Ghostwrite a line | `POST /play/{scenarioId}/ghostwrite/stream` | **Implemented.** NDJSON. Body `{ sessionId, intent, povCharacterId?, mode: "character"|"narrator" }`. Turns the player's **note about what they want the line to do** into the line itself, in their POV character's voice or the narrator's, streamed as `{ type: "ghostwrite", text, done }` deltas. **Nothing is persisted** — no event row, no trace, no buffer push — which is what makes it safe to offer: a draft the player rejects leaves no trace anywhere, because it never entered the record. It becomes part of the story only if they send it, through the ordinary turn path. 400 on an empty intent, 404 on an unknown session; an unconfigured model reports in-band rather than streaming nothing. Overridable via the `ghostwriter.line` prompt key. |
| Edit a beat | `PATCH /play/{scenarioId}/sessions/{sessionId}/beats/{eventId}` | **Implemented.** Body `{ text, expectedSeq? }`. Rewrites one beat's prose and returns the row as a `PersistedEvent`. Allowed on `narration`, `character_prose`, `character_dialogue`, `character_action`, `internal_thought` and `user_turn` — including **any** player line, not just the last. A beat with no prose of its own (`state_update`, `branch_choices`, `character_status_change`, `scene_image`) is refused **422** rather than silently accepted. Sets `data.editedByPlayer`, and **rebuilds the recent-turn buffer**, without which the cast would keep reading the old wording out of Redis while the player reads the new one. Non-destructive: what followed the beat stays — discarding it is what rewind is for. The diagnostic trace deliberately still records what the model originally produced. |
| Branch a play-through | `POST /play/{scenarioId}/sessions/{sessionId}/branch` | **Implemented.** 201. Body `{ atEventId, name?, expectedSeq? }`. Forks the play-through at the **end of the turn** containing `atEventId` into a new session with `parentSessionId` + `forkSeq` set, copying its events and traces (fresh ids, **same seqs**) and its session stat values. The source is untouched. `expectedSeq` is an optimistic precondition — a mismatch 409s. |
| Rewind a play-through | `POST /play/{scenarioId}/sessions/{sessionId}/rewind` | **Implemented.** Body `{ atEventId, keepSnapshot=true, expectedSeq? }`. Cuts at a **turn boundary**: the whole turn containing `atEventId` goes, with everything after it — the opening `user_turn` row included, because the player is about to rewrite that line. With `keepSnapshot` the pre-cut history is forked into `Before rewind · <hh:mm>` first, so undo is a row in the tray rather than soft-deletion. Re-derives session stats by replaying the surviving `state_update` rows, rebuilds the Redis buffer, prunes the cut turns' Neo4j `:Event` nodes. Returns `{ session, cutSeq, removedEvents, removedTraces, snapshotSessionId, restoredTurn }` — `restoredTurn` being the deleted player line with its `guidance`, `pov` and `taggedDocIds`, which is what lets the client hand the player their own words back to edit. |
| *(event fields)* | `takes` / `activeTake` on `narration`, `character_prose`, `character_dialogue`, `scene_image` | **Implemented.** Alternate versions of a beat, kept when the player re-rolls it, and which one is showing. Both default to empty/zero, so every row written before takes existed parses unchanged. `text` (and for an image, `url`/`prompt`/`caption`) **always mirrors the active take**, so the buffer, the export, reload and the moment prompt keep working without knowing takes exist. Capped at 5, oldest dropped. Takes live inside the beat's own row — never as extra events, which would need a `seq` and either break `(sessionId, seq)` uniqueness or poison the ordering. |
| Session history | `GET /play/{scenarioId}/sessions/{sessionId}` | **Implemented.** The full record of one play-through so the story player can **resume** it: `{ session, events, traces }`. `events` are the persisted story events in `seq` order in the **wire-envelope shape** (incl. the hidden `internal_thought` rows and the `user_turn` player lines) so the client replays them through the same reducers it uses live; `traces` are the persisted diagnostic steps ordered by `(turn, n)` (`{ turn, n, step, title, detail, data }`) — the graph/RAG/thinking activity. 404/400 on unknown/mismatched session. |
| Close session | `POST /play/{scenarioId}/sessions/{sessionId}/close` | **Implemented.** The save-on-close signal — stamps `closedAt` + bumps recency and returns the `SessionSummary`. Idempotent (every turn already persists; this only marks the close). 404/400 on unknown/mismatched session. |
| Export session | `GET /play/{scenarioId}/sessions/{sessionId}/export?format=json\|md` | **Implemented.** Downloads the **full conversation record** as an attachment: turn-by-turn flow, each character's thinking, and the knowledge-graph + RAG activity (from the persisted trace). `format=json` → structured turns; `format=md` → a human-readable transcript. Server-rendered from the DB so it works identically for a live or a long-closed scene. `422` on an unknown format. |
| Stream (seam) | `GET /stream/{sessionId}` (SSE) or WS `/ws/{sessionId}` | **Deferred seam.** A separate fan-out connection (Redis pub/sub, reconnect/replay-from-`seq`, multi-watcher) for cases the single-response stream above doesn't cover. Not built. |
| Admin (future) | `GET /admin/*` | High-permission only. |

## Stat Definition Shape

A stat definition (on a storyline, optionally overridden by a scenario):

```json
{
  "key": "health",
  "displayName": "Health",
  "description": "Physical condition and vitality.",
  "min": 0,
  "max": 100,
  "default": 100,
  "guidance": "stats/health.md",
  "visibility": "public",
  "appliesTo": ["character"],
  "bands": [
    { "min": 0, "max": 20, "label": "Nearly dead", "description": "{Character} can barely stand." },
    { "min": 81, "max": 100, "label": "Very healthy", "description": "" }
  ]
}
```

Stats are **freely editable** — name, description, range (`min`/`max`/`default`), and bands all change via `PATCH` (only `key` is immutable). When a range narrows, the service **re-clamps** every character's value for that stat in the same transaction so no stored value sits out of bounds. `DELETE /storylines/{id}/stats/{key}` removes the definition **and prunes that stat's values from every character** (the value link is by key, not a FK). The validator clamps every stat change to `[min, max]`. `bands` ("tickers") are an ordered list of `{ min, max, label, description? }` describing what value ranges *mean*; they need not tile the range or be contiguous, but each requires `min ≤ max` and a non-empty label. The stat `description` and each band's optional `description` may contain the literal placeholder `{Character}` — at play time the assembler resolves the character's **current** band from their value and substitutes `{Character}` with the character's name, injecting that into the character-turn prompt (see `docs/data-flow.md`; band descriptions default to `""` on read and in generation output). `visibility` ∈ `public | private_to_user | private_to_character | hidden`. A character holds values only: `{ "health": 80, "strength": 14 }` — `GET /characters/{id}/stats` reads that map back (only keys ever explicitly set; a stat never touched is absent, and every reader falls back to the schema `default`), read alongside `PUT` by both the Library (`lib/api.getCharacterStats`, for the CharacterCard/carousel stat display) and the story player (seeding each cast member's live per-character stats before any turn runs).

## Context Document Shape

A persisted, triaged reference document on a storyline (the RAG-corpus seam):

```json
{
  "id": "cd_…",
  "storylineId": "embergate",
  "name": "maerin.md",
  "content": "Maerin Voss is a harbor smuggler …",
  "category": "character",
  "includeDraft": false,
  "includeRag": true,
  "includeExtract": false,
  "source": "upload",
  "charCount": 812,
  "entityType": "character",
  "entityId": "c_abc123",
  "links": [{ "id": "cdl_…", "entityType": "character", "entityId": "c_abc123" }]
}
```

`category` ∈ `character | setting | other` — a doc about **one** character/setting
lands in that bucket; one holding **multiple** characters or settings, or a general
world doc, lands in `other` (set by Triage). `includeDraft` marks world-setting docs
that ground generation; `includeRag` (default `true`) marks the retrieval corpus;
`includeExtract` (default `false`) is a **legacy** per-doc flag from the retired
**Build the whole world** flow — still settable via Triage and persisted for
back-compat, but no longer consumed by any agent (the storyline agent that replaced
Build the whole world edits the storyline's own fields only; it does not mine
context docs for new characters/settings).
`entityType` + `entityId` (both nullable) scope a doc to a specific
character/setting/scenario: a scoped doc reappears in that editor on re-edit and is
deleted (with its Qdrant point) when the entity is deleted. A doc without these
fields is storyline-level (the Triage/bulk default). `GET /storylines/{id}/context-docs`
accepts `?entityType=character&entityId=c_abc123` to filter by scope.
`POST …/context-docs/bulk` takes `{ docs: [ContextDocumentCreate…] }` and persists
the whole corpus in one call (the New Storyline commit). Docs with `includeRag: true`
are embedded on save and pruned on delete (hybrid RAG).

**Provenance links (`links[]`).** A doc→entity **many-to-many** reference recording
which entities a document was used as context **for** — distinct from the single
`entityType`/`entityId` OWNERSHIP scope above (a link never changes the doc's
storyline-level membership, and one doc may link to several entities). Auto-captured
when **Build the whole world** mines a doc into a character/setting (the commit turns
each proposed entity's `sourceDocNames` into links), plus manual links from the entity
editor's **Source documents** section. Endpoints: `POST /context-docs/{docId}/links`
`{ entityType, entityId }` (idempotent) and `DELETE /context-docs/{docId}/links?entityType=&entityId=`
both return the updated `ContextDocumentRead`; deleting a doc cascades its links,
deleting a linked entity drops the dangling links but keeps the doc. Links are pure
provenance metadata — no effect on embeddings/retrieval.
`GET /storylines/{id}/context-docs?linkedEntityType=character&linkedEntityId=c_abc123`
returns the docs an entity is a context reference of (the Source-documents panel).

## Story Graph Shapes

The scenario subgraph (`GET /scenarios/{id}/graph`) — cast + setting and the edges among them, read live from Neo4j:

```json
{
  "available": true,
  "scenarioId": "sc_…",
  "nodes": [
    { "id": "maerin", "type": "Character", "label": "Maerin Voss", "storyline": "embergate", "metadata": { "appearance": "…" } },
    { "id": "saltworn", "type": "Setting", "label": "The Saltworn Tavern", "storyline": "embergate", "metadata": { "atmosphere": "…", "kind": "Social Hub" } }
  ],
  "edges": [
    { "source": "maerin", "target": "saltworn", "type": "present_at", "metadata": { "weight": 1.0, "visibility": "public", "status": "active" } }
  ]
}
```

A Type Registry entry (`GET/POST /storylines/{id}/graph/types`):

```json
{
  "id": "gt_…",
  "storylineId": null,
  "kind": "edge",
  "typeName": "loves",
  "fieldSchema": [{ "name": "potency", "kind": "numeric", "min": 0, "max": 1 }],
  "description": "A character's love toward another.",
  "valence": "positive",
  "decay": { "half_life_turns": 40, "floor": 0.05 },
  "status": "built_in"
}
```

`kind` ∈ `node | edge`; `valence` ∈ `positive | negative | neutral` (edges only; required on create); `status` ∈ `built_in | experimental | trusted`. Built-in types have `storylineId: null` and are immutable; user types are storyline-scoped and start `experimental` (only `built_in`/`trusted` reach the hot path — §10). See `docs/story-graph-neo4j.md`.

## RAG Shapes

Three storyline-scoped endpoints for the hybrid RAG layer. All return `available: false`
(with no error) when Qdrant is disabled or unreachable — best-effort, like the Story Graph.

**`GET /api/storylines/{id}/rag/status`** — reachability + indexed count:

```json
{ "available": true, "indexed": 42 }
```

**`POST /api/storylines/{id}/rag/reindex/stream`** — re-embeds the world's corpus
streaming NDJSON (`application/x-ndjson`). Emits one `embedding` event per entry,
then a terminal `done` event:

```json
{ "stage": "embedding", "index": 1, "total": 42, "name": "Maerin Voss", "type": "character" }
{ "stage": "done", "indexed": 41, "skipped": 1, "total": 42, "available": true }
```

`skipped` counts entries whose content hash is unchanged (idempotent — no re-embed
for unchanged entries). `available: false` in the `done` event when Qdrant is
unreachable. Entries embed **concurrently** (bounded by the operator's
`authoringConcurrency`; Qdrant writes are serialized), so `embedding` events arrive
as each entry *completes* — `index` is a 1..N completion counter, not a fixed
position, and its order is arbitrary.

**`POST /api/storylines/{id}/rag/query`** — debug retrieval for a query string:

Request body:
```json
{ "query": "who controls the harbor?", "k": 5, "prefilter": {} }
```

Response:
```json
{
  "available": true,
  "results": [
    { "entryId": "character:c_abc123", "name": "Maerin Voss", "type": "character",
      "score": 0.87, "body": "Maerin Voss is a harbor smuggler …" }
  ]
}
```

`k` (default 5) is the number of top entries after RRF fusion. `prefilter` is an
optional payload filter passed to Qdrant (e.g. `{ "type": "character" }`). This
endpoint is for debugging retrieval — the authoring agents call `rag_block` directly.

## Options / Settings Shape

Global settings for the `/options` page. There is no auth yet, so this is a
single global document (one DB row per namespace in `app_settings`). The LLM API
key is **write-only**: it is stored server-side and never returned in clear.

`GET /options` →

```json
{
  "llm": {
    "baseUrl": "http://localhost:7070/v1",
    "model": "llama-3.1-8b",
    "provider": "openai-compatible",
    "params": { "temperature": 0.7, "maxTokens": 512, "topP": 1.0, "frequencyPenalty": 0.0, "presencePenalty": 0.0 },
    "hasApiKey": true,
    "apiKeyHint": "…AB12",
    "authoringConcurrency": 3,
    "maxContextTokens": 16384
  },
  "library": { "defaultStorylineId": "embergate", "openLastStoryline": true },
  "comfy": {
    "baseUrl": "http://localhost:8199",
    "workflow": "ZiT-Workflow.json",
    "params": { "steps": 4, "cfg": 1.0, "width": 1024, "height": 1024, "batchSize": 1, "negativePrompt": "" }
  },
  "prompts": {
    "catalog": [
      { "key": "character.output_contract", "agent": "Character", "label": "Output contract", "description": "How a character voices a beat — thinking + action + dialogue (carries the strict parsing tags).", "default": "…" },
      { "key": "narrator.system", "agent": "Narrator", "label": "Transition beat", "description": "The short narration used to progress the scene between beats.", "default": "…" }
    ],
    "overrides": { "narrator.system": "You are a terse, literary narrator…" }
  }
}
```

- `PATCH /options/llm` — body may include `baseUrl`, `model`, `provider`, `params`,
  `apiKey`, `authoringConcurrency`, and `maxContextTokens`. **`apiKey` semantics:** omitted = keep the
  stored key; `""` = clear it; any other value = replace it. The base URL is
  normalized (trailing slash trimmed). **`authoringConcurrency`** (default from
  `BUILD_MAX_CONCURRENCY`, clamped ≥1) bounds how many characters/settings the world
  build drafts concurrently **and** how many entities a RAG re-index embeds
  concurrently (single-slot llama.cpp → 1, vLLM → higher; image generation stays
  sequential). **`maxContextTokens`** (default 16384, floor-clamped to 1024, persisted
  in the `llm` namespace) is the configurable fallback used when the running inference
  engine cannot be probed for its context window (see `GET /options/llm/context-window`
  below). Returns the masked `LlmConfigRead`.
- `PATCH /options/library` — body may include `defaultStorylineId`,
  `openLastStoryline`. Returns `LibraryDefaultsRead`.
- `POST /options/llm/models` — `{ baseUrl?, apiKey? }` (fall back to stored).
  Proxies `GET {baseUrl}/models` server-side (dodges browser CORS, keeps the key
  off the client) → `{ "models": ["id", …] }`. Upstream non-2xx →
  `502 upstream_error`; network/timeout → `502 bad_gateway`; missing URL →
  `400 bad_request`.
- `POST /options/llm/test` — `{ baseUrl?, apiKey?, model, params? }`. Proxies a
  tiny `POST {baseUrl}/chat/completions` → `{ ok, model, latencyMs, sample }`.
- `GET /options/llm/backend` — read-only diagnostics for the auto-detected
  inference engine of the configured endpoint → `{ "backend": "vllm" | "llamacpp" |
  "relay" | "unknown", "budgets": { "low": 256, "medium": 512, "high": 1024,
  "very_high": 2048, "max": 4096 }, "budgetKeys": [...], "budgetApplied": true }`
  (budget keys are the effort enum values, not camelized). The engine is probed in
  order — `GET /version` → vLLM, `GET /props` → llama.cpp, then the OpenAI
  `GET /models` listing, whose entries name an upstream engine when the endpoint is a
  **relay** (`owned_by: "relay:llama.cpp · local"`) — then cached and refreshed by a
  background poller. `budgetKeys` names the request key(s) the thinking budget rides
  under and `budgetApplied` says whether any is sent; a `relay`/`unknown` endpoint gets
  **both** keys rather than none. See **Reasoning budget** below. Surfaced read-only in
  the Options **About** tab (`getLlmBackend` in `lib/api.ts`): the detected engine, how
  the budget is delivered, and the budget ladder, degrading to "unavailable" on error.
- `GET /options/llm/context-window` — returns the effective context-window token count
  for the currently configured LLM endpoint →
  `{ "maxContextTokens": 32768, "source": "detected" | "configured" }`. `source` is
  `"detected"` when `llm_backend.get_context_window` successfully probed the engine
  (llama.cpp `GET /props` → `default_generation_settings.n_ctx`, top-level `n_ctx`
  fallback; vLLM `GET /v1/models` → first model's `max_model_len`); `"configured"` when
  the probe is unavailable or fails, in which case the stored `maxContextTokens` LLM
  setting (default 16384) is returned. The detection result is cached per base URL with
  the same TTL as the backend probe; `clear_cache()` resets both. Consumed by
  `getLlmContextWindow()` in `lib/api.ts` — the story player fetches it once on mount
  to power the **context usage bar** (bar is hidden on error, i.e. best-effort).
  Also surfaced as the "Max context (tokens)" fallback field in the Options **Language
  Models** tab, so the operator can configure the denominator when the engine is not
  auto-detectable.

**Writing-Agent Prompt Overrides** — the global layer of the four-layer resolution chain. The
`prompts` field on `GET /options` contains:
- `catalog` — the full registry of the **ten** overridable prompt keys, each with `key`, `agent`
  (which agent owns it), `label`, `description`, and `default` (the built-in text). Keys: `character.output_contract`,
  `narrator.system`, `narrator.system_long`, `director.who_is_up`, `director.rerank`, `director.branch`,
  `director.pov_branch` (POV-mode follow-up suggestions, `director_agent.propose_pov_lines`), `planner.system`,
  `ghostwriter.line` (drafts the player's own line from a note about what they want it to do),
  `recap.summarize` (folds beats that have passed out of the context window into the scene's rolling memory).
  **`director.who_is_up` and `director.rerank` are inert on the live turn path** — `director_agent.who_is_up`
  and `director_agent.rerank` are dead code, called only from `utils/tests/backend/agents/test_director_agent.py`;
  the per-beat decision on a real turn is made by `planner_agent.plan_beats`. Overriding either key has no
  effect on actual play.
- `overrides` — the current global overrides map (`{registryKey: text}`); only keys with active
  overrides appear.

`PATCH /options/prompts` — body: `{ "overrides": { "narrator.system": "Your text…" } }`.
Patches the stored global overrides: a non-blank value replaces the key; a blank value (`""`)
clears it, reverting to the registry default; unknown keys are silently ignored. Returns
`PromptsConfigRead { catalog, overrides }`. At runtime, prompts resolve via the four-layer chain:
**registry default → global override → storyline `promptOverrides` → scenario `promptOverrides`**
(last non-blank wins; blank/None/unknown keys are ignored). The per-storyline and per-scenario
overrides are persisted through the existing PATCH endpoints for those resources (no new endpoints).

**Orphaned-media cleanup** (maintenance — generated WebPs that no DB row references,
left by cancelled drafts or deleted entities):

- `GET /options/media/orphans?min_age_hours=24` — dry-run scan (deletes nothing).
  Cross-references the `*.webp` files under `MEDIA_DIR/portraits` + `MEDIA_DIR/scenes`
  against every `Character.portrait` / `Setting.image` basename. Response →
  `{ "portraits": {...}, "scenes": {...}, "orphanCount", "eligibleCount", "totalBytes",
  "eligibleBytes", "minAgeHours" }` where each per-dir object is
  `{ "orphanCount", "eligibleCount", "totalBytes", "eligibleBytes" }`. An orphan is a
  WebP whose basename is unreferenced; it is *eligible* only when its mtime is older
  than `minAgeHours` — the **grace period** that protects files from an in-flight draft
  (generated but not yet saved).
- `POST /options/media/cleanup?min_age_hours=24` — deletes only **eligible** orphans
  (unreferenced AND grace-expired); recent orphans are skipped. Response →
  `{ "deletedCount", "freedBytes", "skippedRecentCount" }`. Safe by construction: never
  touches referenced files, non-`.webp` files, or anything outside the two media subdirs.
  Surfaced in the Options **About** tab's Maintenance section (scan → confirm → delete).

**ComfyUI image generation** (the local Comfy server — its own HTTP + WebSocket
protocol, not OpenAI-compatible):

- `PATCH /options/comfy` — body may include `baseUrl`, `workflow`, `params`
  (`steps`, `cfg`, `width`, `height`, `batchSize`, `negativePrompt`). Base URL is
  normalized. Returns `ComfyConfigRead`.
- `GET /options/comfy/workflows` — `{ "workflows": ["ZiT-Workflow.json", …] }`,
  the `*.json` files saved in `utils/workflows/`.
- `POST /options/comfy/status` — `{ baseUrl? }` (fall back to stored). Server-side
  `GET {baseUrl}/system_stats` → `{ ok, comfyuiVersion, device, pythonVersion }`.
  Network/timeout → `502 bad_gateway`; missing URL → `400 bad_request`.

The full generation pipeline (load workflow → patch prompt → `POST /prompt` →
WebSocket wait → `GET /history` → `GET /view`) lives in
`web/backend/app/services/comfyui.py` (`generate(...)`), used by the story engine;
the Options tab exposes config + the status check only.

## Reasoning budget (backend-controlled thinking cap)

Local reasoning models spend most of their wall-clock on hidden *thinking* tokens.
Mytheca caps that **per authoring operation** so quick work finishes fast. The effort
is set on the **backend** at each call-site and is **never exposed to the user** for
Storyline / Character / Setting creation — there is no request field or settings
toggle for it.

- **Efforts → thinking-token budget:** `none` 0 · `low` 256 · `medium` 512 · `high` 1024 ·
  `very_high` 2048 · `max` 4096 (`web/backend/app/schemas/reasoning.py`).
- **`none` means do not think**, carried by the ordinary budget key: measured on the deployed
  vLLM route, a `0` budget produced 0 reasoning characters where `512` produced 826–2084.
  Also forcing `chat_template_kwargs.enable_thinking = false` was tried and **rejected** — it
  suppressed nothing extra and made the model terser (15–63 completion tokens against 67–76).
- **Per call-site:** **the character turn = High (1024)** — the beat needs a scratchpad
  that is not the prose. With the channel off entirely a live run caught the model writing
  its own deliberation into the passage and degenerating into a repetition loop at 29,660
  characters; the cap keeps it bounded without putting it in the story. The character's
  in-POV interiority is separate — it lives in the passage itself. The passage is **not**
  token-capped: it delta-streams, so length costs the reader nothing.
  **The beat planner = Quick (128)** — it runs after every beat, so it wants an instinctual
  read of the room rather than deliberation. **Triage = Low**; the standalone storyline/character/setting drafts + the
  storyline agent's converse/plan calls = **Medium** (`DEFAULT_AUTHORING_EFFORT`).
- **Transport:** `services/llm.chat_complete(..., reasoning=)` detects the engine and
  adds the matching key — **vLLM** `thinking_token_budget`, **llama.cpp**
  `thinking_budget_tokens`. A **relay** or **unknown** endpoint gets **both** keys: an
  engine ignores a body key it does not recognise, whereas sending none leaves a
  reasoning model to think until it exhausts `max_tokens` or the generation timeout.
  Requires reasoning enabled server-side (vLLM `--reasoning-parser`; llama.cpp
  `--jinja --reasoning on` with no CLI `--reasoning-budget`).

## Authoring Shapes (storyline creation agent)

The agent process that builds a storyline at creation time, run over the
configured LLM (the `/options` endpoint above). **No retrieval / RAG:** when
present, `docsOverview` is inline text read from dropped reference files in the
browser and used for that single generation only — it is never persisted or
indexed. Inline grounding is capped at **32000 characters** server-side
(`_common.DOCS_CAP`; the frontend mirrors it via `readDocs.DOCS_CHAR_CAP` and the
on-page context-budget meter).

- `POST /storylines/draft` — `{ seed, docsOverview? }`. Drafts metadata from a
  one-sentence seed → `{ "title", "genre", "tagline", "premise" }` (the create
  form prefill). Empty `seed` → `400 bad_request`; unconfigured LLM →
  `400 bad_request` ("Configure a model in Options first."); a reply that is not
  valid storyline JSON → `502 upstream_error`.
- `POST /storylines/primer` — `{ premise?, seed?, docsOverview? }` (at least one
  of `premise`/`seed` required). Generates the agent-facing **World Primer** →
  `{ "worldPrimer": "…prose…" }`. The result is stored on the storyline via the
  normal `worldPrimer` field on create/PATCH. Same unconfigured-LLM /
  empty-completion error mapping as above.
- `POST /storylines/triage` — `{ docs: [{ name, text }], storylineId? }`. Classifies
  each dropped reference document in one call → `{ "items": [{ name, category, includeDraft,
  includeRag, includeExtract, rationale }] }`. `category` ∈ `character | setting | other` (a doc about
  ONE character/setting → that bucket; multiple/mixed/general → `other`); `includeDraft`
  marks world-setting docs that ground drafting, `includeRag` (default on) marks the
  retrieval corpus; `includeExtract` (default **off**) is a **conservative opt-in**
  suggestion — set only for a clear, single, explicitly-named character/setting profile.
  Empty `docs` → `{ "items": [] }` (no LLM call); a doc the model omits
  falls back to `other`/RAG-on/Extract-off; unconfigured LLM → `400`; non-JSON reply → `502`. The
  classified docs are persisted on commit via the **Context documents** bulk endpoint.
### Live Authoring Stream (NDJSON)

Streaming triage. The response is `application/x-ndjson` — **one JSON object per
line** — so the New Storyline page renders the classification *as it happens*.
**Pre-flight** errors (no context, unconfigured LLM) are validated before the `200`
stream opens and returned as the usual error envelope; once the stream is open the
status can't change, so a per-doc failure falls back to `other`/RAG-on rather than
aborting the run. The non-streaming `/triage` route above is unchanged (a collector
over the same generator).

- `POST /storylines/triage/stream` — same body as `/triage`, but classifies **one
  document per LLM call** (genuinely live). Emits, per file:
  `{ "type": "status", "name", "index", "total" }` then `{ "type": "item", "item": TriageItem }`,
  and a terminal `{ "type": "done" }`. A per-doc failure falls back to `other`/RAG-on
  (it does not abort the run). Empty/blank docs stream straight to `done` with no LLM call
  (and need no configured LLM).

### World Population Stream (NDJSON)

`POST /storylines/{id}/populate/stream` — fill a **newly-created** world with its cast
and places. The New Storyline page runs this immediately after `commitWorld`, once the
author confirms in the Build-world dialog, so the redirect lands them in a populated
Library instead of an empty one. Body:

```json
{ "docsOverview": "…", "source": "auto", "maxCharacters": 5, "maxSettings": 3,
  "withArtwork": false, "fromSeq": 0 }
```

**`source`** decides whose people get built. `documents` builds exactly the characters
and places the author's own context files name; `invent` makes them up from the premise;
`auto` (the default) uses the documents when the world has any and only invents when it
has none. `documents` with no usable files builds nothing and says so — it never falls
back to inventing.

`maxCharacters` (0–8, default 5) and `maxSettings` (0–6, default 3) bound **invention
only**; out-of-range values are a `422`. The author's own files are never capped —
dropping their seventh character file would be the same defect as inventing one.
`docsOverview` is the same Draft-selected file text the authoring agents take.
`withArtwork` is **opt-in**: every image is a full ComfyUI render, so it defaults off, is
gated on one up-front reachability probe, and a failed render never costs the entity.
**`fromSeq`** re-attaches to a run already in flight (see *Resumable* below).

**Where the roster comes from.** The build reads the world's storyline-level context
documents and sorts them by the author's own classification: `character` and `setting`
docs are mined by `agents/extract_agent.py` for the subjects they **explicitly name and
profile** (strictly scoped — a Character doc can never yield a phantom setting), and each
extracted subject is drafted from its own paragraph and linked back to its source file
(`ContextDocumentLink`). `other` docs are lore: they ground every draft and become
nothing. A corpus where *nothing* is classified is mined for either kind, since an
untriaged file persists as `other` and ignoring it would silently discard the upload. A
classified file that names nobody still becomes one entity — the author filed it under
Characters, so it is about someone.

The run plans a roster (`agents/roster_agent.py`), then builds each entry through the
*same* agents the per-entity creators use and persists it through the normal CRUD path —
so a populated world picks up the usual Story-Graph and RAG sync. A character is built
**whole**, in the order the retired world build used: draft (`/characters/draft`) →
**voice & tone profile** (`/characters/voice-samples`) → **starting stats** keyed to the
world's schema (`/characters/starting-stats`, skipped with no LLM call when the world
defines no stats) → portrait when artwork is on. A setting is drafted
(`/settings/draft`), then given scene art when artwork is on. Every step after the draft
is best-effort: it emits an `error` frame and the entity still stands.

Names are **de-duplicated against the whole world** (existing rows included): two draft
agents can independently invent the same name, and the turn loop resolves speakers and
relationships by name, so a collision would make two characters indistinguishable to the
engine. Preference order is the drafted name, the roster's proposed name, the drafted
name qualified by role/type, then a numeric suffix.

Frames:

- `{ "type": "status", "stage": "roster"|"character"|"setting", "message", "name", "index", "total" }`
  — one per step, including the per-character voice / stats / portrait sub-steps, so the
  client can show the build happening.
- `{ "type": "entity", "stage": "character"|"setting", "id", "name", "role", "image" }` — one
  per **persisted** row, emitted once that entity is finished (`role` is the character's
  role or the setting's type).
- `{ "type": "error", "message", "fatal": false }` — one item (a draft, a proposal, a render)
  failed; the run continues and the world is never rolled back.
- `{ "type": "done", "characters": <int>, "settings": <int> }` — the counts that actually landed.

**A stream that ends without `done` is a failure, not a success.** The client
(`features/library/worldBuild.ts`) treats a truncated run — dropped connection, restarted
server, a proxy cutting an idle socket — as a failed build and says so, rather than
walking the author into a half-built world.

Plus, once the roster is settled and before anything is drafted:

- `{ "type": "plan", "source": "documents"|"invent", "characters": [RosterEntry],
  "settings": [RosterEntry], "note" }` — what the run is about to build, named. Each
  `RosterEntry` carries `name`, `source` (the paragraph it was drawn from), and
  `docId`/`docName` when it came from one of the author's files.

**Resumable.** The run lives server-side (`services/world_populate_runs.py`): a background
thread with its own Session, appending **sequenced** frames to an in-memory log. This
endpoint only *watches* it. Every frame carries `seq`; a client whose connection drops
re-attaches with `fromSeq = lastSeq + 1` and the endpoint replays what it missed before
following live. A `fromSeq > 0` request **never starts a build** — it attaches to the
existing run or, if the process restarted and there is none, returns a terminal `error`
frame. That is what stops a reconnect from building the world twice. Requesting a fresh
watch (`fromSeq: 0`) for a world already building attaches to that run rather than
starting a second one. The registry is in-process and non-durable: a backend restart ends
a run, and the client reports it honestly.

**Pre-flight** failures return the usual error envelope before the `200`: `404` unknown
storyline, `400` unconfigured LLM. A failure *after* the stream opens cannot change the
status, so it arrives as a terminal `error` frame with `fatal: true`. Long gaps between
entities are filled with `status` keep-alive frames (`seq: -1`, never resumed from).

## Storyline Agent Shapes (conversational, scope-aware editor)

The agent that **replaced "Build the whole world"** on both `/storylines/new` and
`/storylines/[id]/edit`. Instead of one orchestrated build call, the author sets a
**write scope** (which of the storyline's own fields the agent may change), chats
with it, and reviews a proposed **plan** before anything is written. The agent owns
only the storyline's own fields — cast and settings keep their existing per-entity
"Draft with Mytheca" flows. Conversation history is **client-session memory**: held
in the page's React state and sent back to the server every turn (`messages[]`); a
**New chat / reset** clears it. Run over the configured LLM.

**Write scope.** `FieldScope { writable: boolean, readable: boolean }`; `ScopeState
= { [fieldKey]: FieldScope }` over the six fields `title | genre | tagline | premise
| worldPrimer | statistics`. The scope object is the single source of truth shared
by client and server — the client renders it as a checkbox/pill list, and the same
object is sent with every request so the server can build a matching response
schema and prompt.

**Plan shapes:**

```json
{
  "changes": [
    { "field": "tagline", "before": "A city of ash.", "after": "A city that forgets its own fires.", "rationale": "Tighter, more evocative." }
  ],
  "statChanges": [
    { "key": "suspicion", "changeType": "update", "before": { "max": 100 }, "after": { "max": 120 }, "schemaAltering": true, "rationale": "Widen the ceiling for the endgame arc." }
  ],
  "notes": "…"
}
```

`FieldChange { field, before?, after?, rationale }` — one row per non-stat field the
plan touches (`before` omitted on create, where there is no prior value). `StatChange
{ key, changeType: "add"|"update"|"remove", before?, after?, schemaAltering, rationale
}` — one row per stat-definition change; `schemaAltering: true` flags an add/remove or
a range/band change so the plan renderer marks it as higher-risk. `StoryPlan {
changes[], statChanges[], notes? }` is the terminal payload of a conversation turn
that asked for a change; a purely discursive turn returns no plan at all.

**Stream frames** (NDJSON, `application/x-ndjson`, one JSON object per line):

```json
{ "type": "message", "delta": "Here's what I'd change: ", "done": false }
{ "type": "message", "delta": "a tighter tagline.", "done": true }
{ "type": "plan", "plan": { "changes": […], "statChanges": […], "notes": "…" }, "baseVersion": "a1b2c3…" }
{ "type": "status", "message": "…" }
{ "type": "error", "message": "…" }
```

`message` frames chunk the assistant's conversational reply (same shape as the turn
stream's delta convention — accumulate by arrival order, `done: true` on the last
chunk). A terminal `plan` frame carries the reviewable `StoryPlan`; on the **edit**
stream it also carries `baseVersion` — a content hash of the current writable-field
values, used later to detect a stale read (see Apply below). A turn that is purely
conversational (no change requested) ends with no `plan` frame. `status` frames are
optional progress markers; `error` is the terminal in-band failure shape shared with
every other NDJSON stream in this contract.

**Endpoints:**

- `POST /storylines/agent/create/stream` — the **creation** agent, for a blank/partial
  draft on `/storylines/new`. Body: `{ scope: ScopeState, messages: AgentMessage[],
  fields: <current in-progress field values>, docsOverview?: string }`
  (`AgentMessage { role: "user"|"assistant", content }`). `docsOverview` is the inline
  text of the context files the author kept selected for **Draft** in `TriagePanel`,
  concatenated client-side by `concatDocs` and re-capped server-side at `DOCS_CAP`
  (32 000 chars); it grounds the turn through `_common.docs_block` — the same block the
  `/draft` and `/primer` endpoints use — and is re-read per turn, so a file dropped
  mid-conversation is picked up by the next message. It is optional: omit it and the
  agent reasons from `fields` alone. The corpus itself is persisted separately via the
  context-document CRUD; this field carries no ids and writes nothing. Streams `message`
  + an optional terminal `plan` (no `baseVersion` — there is no persisted row yet). No
  writes; unconfigured LLM or an empty last user message → `400 bad_request`.
- `POST /storylines/{id}/agent/edit/stream` — the **editor** agent, scoped to an existing
  storyline. Same body shape as create — including `docsOverview` — plus the storyline is
  loaded server-side to ground the conversation (world context + best-effort RAG over its
  own corpus, restricted to `readable_keys(scope)`); the selected context files are
  appended to that grounding. The terminal `plan` frame carries `baseVersion`. `404` if the
  storyline is missing; `400` if the LLM is unconfigured or the last message has no user
  turn. No writes.
**Keep-alive frames.** Both agent streams emit a `status` frame every **10 idle
seconds** while the model is generating. The agent produces nothing until its LLM call
returns, so without them the response sends headers immediately (measured 4–16 ms) and
then holds a byte-for-byte silent socket for the whole generation (measured 24 s for one
turn; minutes on a large local reasoning model), which any idle-connection reaping takes
down mid-thought. `status` frames carry no state — **clients must ignore frame types
they do not handle**, exactly as `foldAgentFrame` already does.

**Stat changes in a plan.** A `statChanges` entry's `after` is the *full* stat
definition. Its `bands` must be a list of **objects** (`{min, max, label,
description?}`), never bare thresholds — both the prompt contract and the `guided_json`
schema now spell this out, because models default to emitting `[0, 3, 6, 9]`. Server
side, an unsalvageable band list is **dropped and the stat kept**: bands are optional
and re-addable by hand, whereas rejecting the stat used to empty the whole plan and
return a reply with no proposal at all.

- `POST /storylines/{id}/agent/apply` — approves and writes a plan. Body:
  `{ scope: ScopeState, plan: StoryPlan, baseVersion?: string }` → `{ storyline:
  StorylineRead, applied: string[] }` (`applied` lists the field/stat keys actually
  written, for an audit trail). Applies **inside one transaction**: text/primer fields
  through the normal storyline write path, statistics through the existing clamped
  stat-definition services (`create_stat_definition`/`update_stat_definition`/
  `delete_stat_definition` — ranges re-clamp character values, adds/removes behave exactly
  as the by-hand Stats editor); any failure rolls back the whole plan (never a
  half-applied storyline). Create-mode approval does **not** call this endpoint — it fills
  the on-page form directly and the author commits via the existing "Create World" path.

**Enforcement is belt-and-suspenders**, since the local stack is prompt-instructed JSON
(no constrained decoding by default):

1. **Schema-shaped prompt (always).** The response schema passed to the model is built
   dynamically from the scope (`response_schema_for(scope)`) so its properties are
   *exactly* the writable fields — the prompt and shape make an out-of-scope change hard
   to even express.
2. **`guided_json` when available.** The same schema is passed as `extra_body.guided_json`
   only when the configured endpoint is detected as **vLLM** (`llm_backend.detect_backend`)
   — constrained decoding where the backend supports it, a no-op elsewhere.
3. **Server-side diff guard (load-bearing).** `diff_guard(plan, scope)` recomputes the
   changed-field set from the plan and rejects it — **`422 scope_violation`** — if any key
   lies outside `writable_keys(scope)`. This runs at **plan time** (in the converse stream,
   before the plan frame is even emitted) **and again at apply time** as a backstop, so a
   hand-crafted request that skips the client can never write out of scope even if layers 1
   and 2 are bypassed.

**Stale-read reconcile.** The apply endpoint does not add a `version` column to
`Storyline` — it recomputes a **content hash of the writable fields** from the current DB
row and compares it to the `baseVersion` the client planned against (itself a hash of the
snapshot the plan was generated from). A mismatch — a concurrent manual edit landed between
plan and approve — is rejected as **`409 stale_storyline`** rather than silently overwritten;
the author re-opens the panel to plan against the fresh state.

## Character Authoring Shapes (agentic Character Creator)

The agent process that fleshes out a **character's base identity** at creation
time (§1 node properties of `Documents/Plans/3.character-graph-structure-prep.md`
— never graph structure). Run over the configured LLM. Same **no retrieval**
rule: `docsOverview` is inline dropped-file text used for one generation only.

- `POST /characters/draft` — `{ seed, docsOverview?, storylineId? }`. Drafts a
  full character → `{ name, role, traits, speech, goal, secret, appearance,
  background, personality, color }`. **`seed` and `docsOverview` are each
  optional individually but at least one must be non-empty** — with no seed the
  draft is grounded purely on the Draft-tagged reference docs. When `storylineId`
  is given, the draft is also grounded in that world's primer/genre (best-effort).
  Empty `seed` **and** empty `docsOverview` → `400 bad_request`; unconfigured LLM
  → `400 bad_request`; a reply that is not valid JSON → `502 upstream_error`.
- `POST /characters/portrait-prompts` — `{ name?, role?, appearance?, traits?,
  personality?, species?, notes? }` (at least one descriptive field required).
  Writes the watercolor ComfyUI prompts → `{ positive, negative }`: short
  comma-separated phrases leading with the subject's species/race so the image
  depicts that being.
- `POST /characters/portrait` — `{ positive, negative?, baseUrl?, workflow?,
  width?, height?, steps?, cfg? }`. Renders the portrait through the configured
  ComfyUI watercolor pipeline, converts the result to **WebP**, saves it under
  `MEDIA_DIR`, and returns `{ portrait: "/media/portraits/<uuid>.webp" }`. The URL
  is carried into the normal character create/PATCH `portrait` field (id-agnostic,
  so it works during creation before a row exists). The `positive` / `negative`
  prompts that produced it are carried into the same payload's `portraitPositive` /
  `portraitNegative` fields, so they persist and re-hydrate the editor on re-edit
  (mirrors the Setting `sceneArt*` and Scenario `sceneArt*` fields). Empty
  `positive` / unconfigured ComfyUI URL → `400 bad_request`; a Comfy failure →
  `502`. **Opt-in — it spends GPU time on the local Comfy server.**
- `POST /characters/voice-samples` — `{ name?, role?, traits?, speech?,
  background?, personality?, storylineId? }`. Derives a **voice & tone profile** —
  2–3 (capped at 4) situation → single-response pairs — from the character's prose
  (grounded in the world when `storylineId` is given) → `{ samples: [{ situation,
  sample }] }`. The model first reasons through the character's distinctive voice
  (diction, rhythm, tics, formality) before writing; each `situation` is a previous
  situation the character was confronted with (often another character's dialogue)
  and each `sample` is the character's SINGLE in-voice response to it — one turn,
  never a back-and-forth exchange — reacting to that situation's specifics rather
  than restating a generic voice description. Runs **before** starting stats
  (voice/tone is defined first).
  **Best-effort** — an empty description or a malformed/absent LLM reply returns
  `{ samples: [] }` (never a 5xx). **Proposal only** — the caller carries the samples
  into the character create/PATCH `voiceSamples` field.
- `POST /characters/starting-stats` — `{ storylineId, name?, role?, traits?,
  personality?, background? }`. Proposes starting values for the storyline's stat
  definitions → `{ proposals: [{ key, displayName, value, min, max, rationale }] }`.
  Each definition's **bands** are folded into the prompt so the model picks a value
  whose band matches the character's intended starting condition. Values are clamped
  to each definition's range, unknown keys dropped, and any skipped stat filled with
  its default. Returns `{ proposals: [] }` (no LLM call) when the world defines no
  stats. **Proposal only** — the caller applies them via `PUT /characters/{id}/stats`.

## Setting Authoring Shapes (agentic Setting Creator)

The agent process that fleshes out a **setting's base description + current
state** at creation time (§4.1 Setting-node properties of
`Documents/Plans/4.story-graph-structure-prep.md` — never the play-accrued event
timeline, never graph edges). Run over the configured LLM. Same **no retrieval**
rule: `docsOverview` is inline dropped-file text used for one generation only.

- `POST /settings/draft` — `{ seed, docsOverview?, storylineId? }`. Drafts a full
  setting → `{ name, type, desc, atmosphere, features, currentState }`. `type` is
  chosen from the canonical setting-type list. **`seed` and `docsOverview` are
  each optional individually but at least one must be non-empty** — with no seed
  the draft is grounded purely on the Draft-tagged reference docs. When
  `storylineId` is given, the draft is also grounded in that world's primer/genre
  (best-effort). Empty `seed` **and** empty `docsOverview` → `400 bad_request`;
  unconfigured LLM → `400 bad_request`; a reply that is not valid JSON →
  `502 upstream_error`.
- `POST /settings/scene-art-prompts` — `{ name?, type?, desc?, atmosphere?,
  features?, currentState?, notes? }` (at least one descriptive field required).
  Writes the watercolor ComfyUI prompts → `{ positive, negative }`: an atmospheric
  establishing shot of the location itself, no people.
- `POST /settings/scene-art` — `{ positive, negative?, baseUrl?, workflow?, width?,
  height?, steps?, cfg? }`. Renders the establishing image through the configured
  ComfyUI watercolor pipeline (landscape 16:9 default), converts to **WebP**, saves
  it under `MEDIA_DIR/scenes`, and returns `{ image: "/media/scenes/<uuid>.webp" }`.
  The URL is carried into the normal setting create/PATCH `image` field (id-agnostic,
  so it works during creation before a row exists). Empty `positive` / unconfigured
  ComfyUI URL → `400 bad_request`; a Comfy failure → `502`. **Opt-in — it spends GPU
  time on the local Comfy server.**

## Scenario Authoring Shapes (agentic Scenario Creator)

The agent process that assembles a **scenario** at creation time — the present-
moment "truth object" — from a one-line scene seed. Run over the configured LLM.
Same **no retrieval** rule: `docsOverview` is accepted for parity but the scenario
modal does not wire dropped files yet (first cut grounds on **seed + world
roster** only).

- `POST /scenarios/draft` — `{ seed, docsOverview?, storylineId? }`. Drafts a
  scenario → `{ title, genre, tone, goal, opening, castIds, settingId }`.
  - **Roster grounding, name→id resolution.** When `storylineId` is given, the
    agent builds a **numbered roster** of that world's real characters and settings
    (`crud.list_characters` / `list_settings`, capped at 40 each, ordered by
    position) and instructs the model to return character/place **names drawn only
    from the roster**. Names are resolved back to ids server-side via a
    case/whitespace-folded match: **unknown cast names are dropped**, an **unmatched
    setting falls back to `""`** (the soft-reference contract), and cast ids are
    de-duplicated in order. So `castIds`/`settingId` are **always** real members of
    the active world — never invented or dangling.
  - World grounding (primer/genre) is folded in the same way as the character and
    setting drafts (shared `agents/_common.world_context`).
  - Empty `seed` → `400 bad_request`; unconfigured LLM → `400 bad_request`; a reply
    that is not valid JSON → `502 upstream_error`.
  - Persists nothing — the draft fills the create form; the author reviews, then the
    normal `POST /storylines/{id}/scenarios` saves it.

- `POST /scenarios/scene-art-prompts` — `{ title?, genre?, tone?, goal?, opening?,
  settingName?, settingDesc?, notes? }`. Calls the LLM to produce a watercolor
  establishing-shot prompt pair for the scenario's setting atmosphere (no characters
  or people). Returns `{ positive, negative }` (`SceneArtPromptResponse`). At least
  one non-empty field required; unconfigured LLM → `400 bad_request`.

- `POST /scenarios/scene-art` — `{ positive, negative?, baseUrl?, workflow?, width?,
  height?, steps?, cfg? }`. Renders the scene-art image through the configured
  ComfyUI watercolor pipeline (landscape 16:9 default), converts to **WebP**, saves
  it under `MEDIA_DIR/scenes`, and returns `{ image: "/media/scenes/<uuid>.webp" }`.
  The URL is stored in the scenario's `image` field. Empty `positive` /
  unconfigured ComfyUI → `400 bad_request`; a Comfy failure → `502`. **Opt-in —
  spends GPU time on the local Comfy server.**

**`ScenarioRead` shape** — includes the three scene-art fields added alongside the
original draft fields:

```json
{
  "id": "9f8e",
  "title": "The Salt Ledger",
  "genre": "Intrigue",
  "tone": "Tension · rising",
  "goal": "Keep the ledger safe.",
  "opening": "Lamplight gutters over the wet dock.",
  "castIds": ["c_abc123"],
  "settingId": "s_def456",
  "branches": [],
  "image": "/media/scenes/abc123.webp",
  "sceneArtPositive": "misty harbor, lamplit cobblestones, watercolor",
  "sceneArtNegative": "people, text, anime, cartoon",
  "promptOverrides": {}
}
```

`image`, `sceneArtPositive`, and `sceneArtNegative` default to `null`; they are
populated when the author generates scene art in the Scenario Creator.
`promptOverrides` defaults to `{}` (NULL coerced on read); keys must be valid registry
keys — unknown keys are ignored on write. See Writing-Agent Prompt Overrides above.

## NDJSON Event Stream

> **Status:** the event envelope (the types below + `internal_thought` + `StatPatch`, as a discriminated union) lives in `web/backend/app/events/envelope.py`. The **turn transport is implemented** (P1): `POST /play/{scenarioId}/turn` streams a validated, `seq`-monotonic event set (DB-authoritative `seq` via a `(session_id, seq)` unique constraint; persisted to the `events` table). The **diagnostic trace is persisted too** (to `turn_traces`, keyed by `(session_id, turn, n)`) so a scene is fully reviewable/exportable after the fact, and `PlaySession` carries `updated_at`/`closed_at` for resume + save-on-close (see the Sessions / Session history / Close / Export endpoints above). Per-character generation, delta streaming, the Director, gated RAG, the cold-path turn-writer, and the read-time reflection interlude land in the later turn-loop phases (`docs/plans/turn-loop-runtime.md`).

The stream emits one JSON object per line. Every event shares a base envelope:

```json
{ "type": "string", "id": "string", "seq": 0, "scenarioId": "string", "sessionId": "string", "ts": "ISO-8601", "visibility": "public", "data": {} }
```

`visibility` ∈ `public | private_to_user | private_to_character | hidden` — some content is shown to the player, some only affects agent reasoning.

### Event types

Each maps to one frontend component.

| `type` | UI rendering | `data` highlights |
| --- | --- | --- |
| `narration` | Teal narrator card (prose **sanitized** — reasoning/channel tokens stripped) | `text` (may delta-stream), `done` |
| `character_dialogue` | Character chat bubble (speaker's avatar/color) | `characterId`, `text` (may delta-stream), `done` |
| `character_action` | Action label on the speaker's beat | `characterId`, `text` |
| `internal_thought` | **Inline thinking** — a muted line folded into the speaker's beat, between the name and the spoken bubble (`visibility: private_to_user`) | `characterId`, `text`, `done` (delta-streams to the player; kept out of other characters' context) |
| `state_update` | Updates side panels (no chat message) | `patch` — partial scenario state; **stat changes ride here** |
| `branch_choices` | Branch-choices panel | `prompt` (a planner question, usually empty), `choices[]` (`label`, `outcome`) |
| `character_status_change` | Updates the cast rail (no chat message); an `auto` change also raises an **Undo** toast | `characterId`, `status` (`present`\|`unconscious`\|`departed`\|`left`\|`dead`), `reason`, `auto` |
| `scene_image` | Centered, clickable landscape picture of the moment in the transcript (enlarges in a lightbox) | `url` (relative `/media/moments/…`), `prompt`, `negative`, `caption` (alt text), `characterIds` |
| `cast_request` | A centred card in the transcript: *"The scene is asking for Kael"*, with **Bring them in** / **Not now**. Settles to a quiet line once answered | `characterId`, `reason` (the requirement or phrase that named them — the player's own words, quoted back) |

**No dice (D11):** `branch_choices` options carry `label` + `outcome` (a narrative-direction
tag) only — there is no `check` field. A branch is a narrative fork resolved by the player's
selection + the characters' in-character response, never a stat test.

**The planner may ask (`prompt`):** when the player's line leaves the direction genuinely
open, the planner can return an **`ask`** beat instead of guessing — a question plus up to
four suggested answers. It rides on the same `branch_choices` event with `data.prompt` set,
so it renders, round-trips into the composer and replays with no new event type; the client
leads with the question instead of the "Your move" eyebrow, and a question that arrived with
no options renders alone (the player answers in the composer). `prompt` is empty for the
ordinary end-of-turn follow-ups, which are *offered* rather than asked.

Asking is bounded hard, because a planner that can ask will ask instead of deciding. The
**engine** owns the permission (`may_ask`) and grants it only when nothing has happened yet
this turn, the scene is not opening, no scene direction is outstanding, nobody is being
puppeted, and the previous turn did not already end on a question
(`events_store.ended_on_a_question`). The planner may only place the question as the turn's
**first** beat, and anything it planned after one is discarded — the answer decides what
follows. A turn that asked emits no holding narration, no follow-up suggestions and no
silent-turn backstop beat: the question is the turn's last word, which is also what makes
"never twice in a row" a single-row check.

**Scene presence (`character_status_change`):** a character's runtime status within the scene.
`present` is the only **selectable** status (the planner may pick them to speak); the others
keep them in the cast but out of the speaking pool — which is what stops a dead/departed
character from continuing to chat. It is **derived from the session's event log** (the fold of
these events, latest per character; default `present`) — no column, so it survives reload and
rehydrates through the same reducers. Four detection paths, all `auto: true`: a `health`-keyed
stat clamped to its floor → `unconscious`; the planner's `exit` beat (ratifying a death/exit
the story already showed); a character's self-declared `<type:presence_change>` block; and the
manual override endpoint (`auto: false`). Transitions: `present ⇄ {unconscious, departed,
left}`, any → `dead` (terminal); the engine never auto-leaves `dead`, but a manual override may.

**`internal_thought`** is the character's private think→speak block (the turn-loop plan
Step 5 / §7). It streams to the **player** with `visibility: private_to_user` and, on the
client, is **folded into the same beat as the character's speech** — rendered as a muted
"thinking" line between the name and the spoken bubble (the thought event precedes the
speaker's action/dialogue, which merge into that beat). It is **kept out of other characters'
context** — never appended to the shared transcript later speakers condition on. (The type's
default visibility is `hidden`; the engine overrides it to `private_to_user` so the player
sees the thought while the other characters do not.)

**Scene images (`scene_image`)** are the only story event the *player* triggers directly, and
the only one not produced by the turn loop: they come from `POST /play/{scenarioId}/moment/stream`
(see below). The event is persisted like any other beat, so a picture keeps its position in the
transcript, in the session history, and in the export. `prompt`/`negative` are retained on the
event so the picture is reproducible and reviewable; the prompt itself never names a character —
it describes each figure's appearance and what they are doing (see `agents/moment_agent.py`).

**Model output is sanitized centrally:** a reasoning model's chain-of-thought and
harmony-style channel tokens (`<|channel|>…`, `<think>…</think>`) are stripped in
`services.llm.chat_complete` (`_common.strip_reasoning`) — the one call every agent shares —
before the text is returned. This covers narrator prose, the character emission (parsed by
`emission.parse_emission`), and authoring JSON alike; the app's own
`<speaker:>`/`<type:>`/`<thinking>` markers are preserved.

**Stat changes** are carried on `state_update`:

```json
{ "type": "state_update", "data": { "stat": {
  "characterId": "kira", "key": "health", "delta": -25, "value": 55,
  "reason": "Struck by the falling beam." } } }
```

The validator confirms the stat exists and clamps `value` to `[min, max]`; the Stats panel re-renders and the narrator may reference the new state next turn. When bespoke rendering is wanted (an animating bar, a floating "+5 / −10"), promote stat changes to a dedicated `stat_update` event later — the data shape is the same.

Additional types to layer in later: `relationship_update`, `goal_update`, `turn_update`.

### Streaming modes

- **Full events** (one complete object) — used for `state_update`, `branch_choices`, and `character_action`. Easy to validate and render.
- **Delta streaming** — visible prose (`narration`, `character_dialogue`) is delta-streamed by emitting the **same event** (identical `id` + `seq`) repeatedly with an *incremental* `text` chunk and `done: false`, until the final chunk sets `done: true`. The client accumulates the chunks by `id` (`"".join` of the pieces == the full line); the **persisted** row holds the full text. This reuses the `done` field already on those payloads rather than a separate `message_start`/`message_delta`/`message_end` frame set. (`character_action` has no `done` field, so it streams as one full event.)

### Turn Stream (`POST /play/{scenarioId}/turn`)

The response **is** the stream — `application/x-ndjson`, one event per line, in `seq`
order — for the same `postNdjson`/`StreamingResponse` reasons as the build/triage streams.
Request body: `{ "text": "…", "directedAt": "ch_id" | null, "sessionId": "ps_…" | null,
"mode": "pov" | "narrator", "outcome": "…" | null, "povCharacterId": "ch_id" | null,
"guidance": "…" | null, "taggedDocIds": ["cd_…"] }` (omit `sessionId`
to open a new play session; the streamed events carry the resolved `sessionId`; `mode`
defaults to `pov`). `outcome` is the legacy branch-direction tag that opened with a
progression narration. **`povCharacterId` (Player POV)** — when set to a *present* cast
member's id, the player's line **is that character's line**: it is seeded into the turn as a
`character` beat (later speakers react to it as "Mei said X"), persisted on the `user_turn`
row (`data.pov`), and the visible character event is **withheld** (the client already renders
the line optimistically / on rehydrate). The POV character is **removed from the AI's
selectable roster** (planner *and* puppet paths) so the model never voices a second beat for
them; the loop then ends on its own once the rest of the cast is done. `null` (default) is the
guide/narrator behavior. It is **orthogonal to `mode`** (`mode` = narrator-interstitial
rendering; `povCharacterId` = who the player speaks as); an id that is not a present cast
member is ignored (falls back to the default behavior, `data.pov = null`). The back-and-forth is capped by the scenario's `maxTurns`, which
counts **every emitted beat — narrator beats included, not just character replies**. A cold
scene open with no directed character opens narrator-first.

**@-tagged context files (`taggedDocIds`).** The storyline `ContextDocument` ids the player
tagged with `@` in either composer box. The server loads each one (ignoring any id belonging
to a different storyline), bounds the text — at most 5 documents, 6 000 characters each,
12 000 overall, marking anything it trims — and folds it into the **character** and
**narrator** prompts as reference for that one turn. This is the deterministic override for
hybrid RAG: the `retrieval_gate` skips most turns, and when it does fire `rag_block` truncates
each hit to 600 characters, so the specific passage the player cared about routinely never
arrived. Tagging bypasses both.

It is the **opposite of `guidance`**, and four mechanisms keep it that way — two structural,
two prompt-level:

1. Tagged text is **never parsed into requirements** — `intent_agent` and `direction_agent`
   read `text` and `guidance` only, so a tagged file can never create a beat the turn owes.
2. The **planner never sees it** — it reaches only the two writing agents, so it cannot
   change whose beat it is or where the scene goes.
3. **Position:** it sits in the character prompt's MIDDLE, after the gated lore and *before*
   the direction line, so the direction keeps the recency advantage; in the narrator prompt it
   sits ahead of the direction cue for the same reason. The act-now TAIL is untouched.
4. The block **states the precedence outright**: the notes keep facts straight in what is
   said, the beats and the direction decide what happens, and on conflict the scene wins.

The composer strips the `@name` tokens before sending, so the player's line reaches the
intent and direction agents as clean prose; the ids are re-derived from the final text at send
time, so hand-deleting a mention untags it. A `files` trace step reports which documents
landed (`data.names`, `data.injected`).

**Scene direction (`guidance`).** The player directs: they say what happens next and how the
cast should react, and the turn delivers it. The direction text is **`guidance`** when the
request carries one — the composer's second box, which appears above the message box under
Player POV, because there `text` is the character's own line and cannot double as direction —
and otherwise, **when `povCharacterId` is null**, the player's own `text` (the message box *is*
the narrator's box in that mode). Under POV with no `guidance`, the turn carries no direction
and behaves exactly as before. Vague ("things get worse") and highly specific ("Mei storms out,
Aldous grabs her wrist, the lamp goes over") both work.

The direction is parsed into an ordered list of **requirements**, each an outcome that must be
true by the end of some beat and optionally bound to a cast member. POV guidance gets its own
low-effort structural call (`direction_agent.parse`); in narrator mode the requirements ride on
the intent call that already reads that line, so no extra round-trip is spent. A requirement
naming an **absent** character — or the **POV** character, whom the AI never voices — is rebound
to the narrator. The planner is shown what is still owed and how many beats remain and paces it;
once what is owed would fill every remaining beat, the engine **schedules the rest itself**
(`direction_agent.schedule`), bundling same-owner requirements and collapsing the final beat to
a narrator beat when several owners are still waiting. A planner `end` while anything is
outstanding is overridden. **`maxTurns` stays hard** — nothing is delivered by overrunning it; a
direction longer than the scene's budget is absorbed by the opening narration, and anything
genuinely undeliverable is named in a `direction` trace step rather than silently dropped. Each
beat carries only *its* requirements into the prompt, stated as an outcome (never a line to
recite), so the speaker reaches it in their own voice and stays in character.

**A requirement is confirmed by the prose that landed, not by entering a prompt.** Each beat
first *attempts* what it carries (`direction` trace with `data.attempted`), and delivery is
confirmed afterwards from the text the beat actually emitted (`data.delivered` /
`data.unconfirmed`). A beat that produced nothing confirms nothing, so an empty generation, a
withheld scratchpad leak or a failed request leaves the requirement outstanding instead of
ticking it off — which is what used to happen. Confirmation is a cheap lexical coverage check
(`DIRECTION_COVERAGE_THRESHOLD`, default 0.34, ignoring the bound actor's own name and abstract subject placeholders like "a character"); an
unconfirmed requirement is retried up to `DIRECTION_MAX_ATTEMPTS` (default 2). The closing
`direction` trace carries `delivered` (count), `total`, `unconfirmed` (attempted but never
confirmed), `never` (the turn ran out of beats first) and `undelivered` (everything not
confirmed, kept for the client reducer). How many requirements ride on one beat is
`ceil(owed / remaining beats)` — one per beat while there is room, more only when the budget
forces it.

**Bringing someone in.** The scene may **ask** for a character who is not in it, and that is all it can do — there is **no planner action** that introduces a character, so the AI can never bring one in on its own initiative. A `cast_request` is emitted (before any beat) only when the *player* named an absent storyline character: a pinned directive whose actor is away, or a plain longest-first name match of the direction text. It changes nothing. Presence moves only through the ordinary manual `POST /play/{scenarioId}/presence`, which now accepts **any character of the scenario's storyline** rather than only its authored cast (one from a different storyline is still a 404). Declining is written as `status: "departed", reason: "declined"` — a decline has to leave a mark, because a `character_status_change` on the session is exactly what stops the same ask being re-raised every turn. A guest belongs to the **play-through**: `assembler` unions the authored cast with anyone carrying a presence event on this session, and the scenario row is never mutated.

**`directives`** lets the client state the targets instead of having them inferred:
`[{ text, actorId }]`, one per line of the direction box, with `actorId` set from an `@` cast
mention on that line. Non-empty `directives` **replace** `guidance` parsing — the requirements
are built from them verbatim with **no LLM call** — and a directive with a resolved `actorId`
is *pinned*: never re-owned by the narrator, and marked `blocked` (reported on its own
`direction` trace row, excluded from scheduling, carried over) when that character is not in
the scene. An `actorId` outside the cast degrades to `null` rather than being guessed at. Empty
(the default) keeps today's behaviour exactly.

**Carry-over.** Whatever a turn does not deliver is stored on
`play_sessions.standing_direction` and re-owed on the next turn, ahead of whatever is asked
then. `GET …/sessions/{id}` returns it as `standingDirection`
(`[{ id, text, actorId, pinned, fromTurn }]`, `fromTurn` being the seq it was **first** asked
for). **`POST /play/{scenarioId}/sessions/{sessionId}/standing-direction`** — body
`{ "itemIds": [...] | null }` — drops the named entries, or all of them with `null`; returns
the remainder. Idempotent, and it must exist: a debt the player cannot cancel is a bug. Best-effort
throughout: with no LLM configured the whole direction becomes one narrator-owned requirement.
`guidance` **is** persisted on the `user_turn` row (`data.guidance`, `null` when the turn carried
no direction), alongside `data.taggedDocIds`. Both used to die with the turn; the row is what a
reload restores into the composer, what an export renders, and what a rewind or a turn-scope
re-roll replays, so all three need them. Rows written before this carry neither key — read them
with a default rather than assuming presence.
Multiple speakers stream **sequentially** in the planner's order — a later speaker reacts to
its predecessor (each character's `internal_thought` streams to the player but is withheld
from later speakers). A
speaker may propose a stat change (a thin `state_update` block): the validator confirms the
stat exists, applies the **delta/value clamped to `[min,max]`** on the hot path (keeping the
`reason`), and emits a `state_update` event — an unknown stat is dropped. A speaker may also
propose a **`relationship_update`** block (`{target, type, reason}`): validated against the
cast + the registry's character↔character edge types, it becomes a cold-path graph edge
(`source -[type]-> target`) rather than a wire event — so relationships evolve in play. A
speaker may also emit a **`presence_change`** block (`{status, reason}`) to remove *themselves*
from the scene (leaving/collapsing); the planner may emit an **`exit`** beat to remove any
present character the story already wrote out; and a `health`-keyed stat hitting its floor
auto-knocks the character `unconscious` — each emits a `character_status_change` event and drops
that character from the selectable roster for the rest of the scene (see Scene presence above). At the
end of every turn, up to the scenario's `suggestionsCount` (0–4; `0` disables) `branch_choices`
options are generated from the **most recent line** and offered as `label` + `outcome` (no dice —
D11; count-driven — no longer gated on a rarely-set planner flag). Options are **situation-based**
— what happens next in the scene from a general, story-wide perspective, not a single character's
spoken line — and written to **match the tone/pace of the player's own recent moves**; stats inform
which surface, never gate them. **Under Player POV** (`povCharacterId` set) the same `branch_choices`
event instead carries **first-person candidate next lines in the POV character's own voice** (they
flow into the composer as the player's own next line); no new event type or client reducer is needed. Selecting one **writes its text into the composer** for the player
to review, edit, and send as an ordinary `text` turn (it no longer auto-submits). The player's input is persisted as a
`user_turn` event at `seq` 0 of the turn (not streamed back — the client already shows it
optimistically), carrying `data = { text, directedAt, pov }` where `pov` is the Player-POV
character id the line was spoken as (`null` for the default guide/narrator line); the bot's events follow at the next seqs. A mid-stream failure is the terminal `{ "type": "error", "message": "…" }`
frame; pre-flight failures (unknown scenario, empty text, bad session) are a normal error
envelope before the 200 opens.

**Trace steps mark the START of their work.** `reading` (before the intent call) and
`planning` (before each planner call) are emitted *before* the step they name, while
`intent`, `direction`, `speaker` and the rest report a result and therefore follow it. This
matters because the client derives its status label from these frames: when every step was
reported only on completion, the label could name nothing but the step the turn had just
finished, and the real waits went unlabelled. The `speaker` step additionally carries the
planner's `reason`, `register` and `stakes`, so the player can be told *why* this character
is up rather than merely that they are.

**Live reasoning (on by default, ephemeral).** When Options › Language models › *Reasoning
visibility* is `full` — **the default** — the turn interleaves
`{ "type": "reasoning", "characterId", "text", "done" }` frames carrying the model's
reasoning channel as it is produced (`reasoning_content` on llama.cpp, `reasoning` on vLLM) — the deliberation behind the beat, visible
while the player waits. It is **not** a story event and **not** persisted: no `seq`, no
`events` row, no `turn_traces` row, absent from resume and export. `done` marks the end of
one speaker's reasoning; a `characterId` of `null` is the narrator's. `full` is the default
because the first reasoning token arrives at ~0.4 s on the deployed endpoint against
roughly ten seconds before any prose (EXP-2026-08-005) — it is what makes the longest part
of a turn show something. Setting `summary` keeps these frames off the wire entirely, for
players who mind that raw deliberation routinely states what a character is about to say
before they say it; `hidden` additionally suppresses the muted thought line client-side.
A stored value that is missing or unrecognised resolves to the same default (`full`), so
an older config behaves like a fresh one rather than like a third mode nobody chose. Clients ignore unknown frame types, so a
client that does not implement this is unaffected.

**Diagnostic trace (opt-in).** Set `"trace": true` in the request body to interleave
`{ "type": "trace", "n", "step", "title", "detail", "data" }` frames that narrate, **in
order**, what the turn loop did and why — the story player's **Inspector** panel renders
these. `step` is a stable key (`turn` opens each turn, then `intent` / `assemble` / `lore` /
`files` /
`plan` / `speaker` / `prose` / `thinking` / `relationship` / `action` / `dialogue` /
`context` / `stat` / `relationship_change` / `branch` / `commit` / `reflection`); `n` orders
within one turn. Trace frames stay **out of the story-event stream** (not story events, not in
`story_event_adapter`), and the streaming flag defaults **off** so the default stream and
the story-event contract are unchanged — but they are now **persisted** to the `turn_traces`
table on **every** turn (independent of the flag) so a reopened scene's graph/RAG/reasoning
activity survives for review and export (`GET …/sessions/{id}` history + `…/export`). A
character's `internal_thought` is surfaced here as a `thinking` trace step **and** streams as
a `private_to_user` story event (the inline thinking line). Clients ignore `trace` frames for
the transcript. The green **Graph** steps name what was written: `commit`'s `detail` lists
each durable change (`data.changes[]` — the `Consequence` summaries), and the first-turn
`relationships` seed step's `detail` lists the seeded edges (`data.edges[]`).

**`plan` step — the end-of-turn marker.** Exactly one `plan` step per turn carries
**`data.end === true`**: the step that stops the beat loop, whatever stopped it (the planner
called `end`, the POV backstop fired, the scenario's `maxTurns` was reached, or the runaway
beat backstop tripped). Its `title`/`detail` differ by cause and are prose that will drift —
`data.end` is the stable signal, and the story player's **turn-status strip** reads it to say
"the turn is ending" rather than matching on the title.

**`context` step — exact context-window usage.** After a character generation, the engine
emits a `context` trace step carrying the LLM-reported **`data.promptTokens`** — the exact
`usage.prompt_tokens` for that call (the real size of everything sent: output contract +
World Primer + stat guidance + RAG lore + transcript), the honest "context window used"
figure. It is emitted only when the endpoint reports usage (omitted otherwise) and, like
every step, is **persisted**, so the story player seeds its context dial from the resumed
session's last `context` step and updates it live each turn. The frontend falls back to a
char/4 estimate only until a real `promptTokens` is known. The same step carries **`data.cachedTokens`** when the endpoint reports `usage.prompt_tokens_details.cached_tokens` — how many of this call's prompt tokens the server served from its KV cache instead of re-processing. It is **omitted, not zeroed**, when the endpoint reports nothing, so "no data" stays distinguishable from "nothing was reused". A hit rate that collapses as a scene lengthens is what a prompt-cache regression looks like before it becomes visible as creeping latency.

The step also carries **`data.reusablePrefixChars`** and **`data.promptChars`** — how much of this prompt was byte-identical to the previous character call in the same session, measured locally. `cachedTokens` alone cannot be trusted as an alarm: vLLM omits `prompt_tokens_details` entirely when the hit is zero, so a total cache loss reports as *missing data* rather than as a zero. The local figure is always present, and it measures the thing the prompt layout actually controls (see `character_turn_agent._build_user_prompt`). Both are omitted when unavailable, and `promptTokens` is omitted when the endpoint reports no usage — so the step can appear carrying only the local figures.

### Rules

- `seq` is monotonic per session (DB-authoritative: `max(seq)+1`, guarded by a
  `(session_id, seq)` unique constraint) so the client can detect gaps and reorder.
- Chunked/delta text sets `done: false` until the final chunk sets `done: true`.
- **Deltas are live.** `narration`, `character_dialogue` and `internal_thought` are emitted as the model writes them (`services/llm.chat_complete_stream`), not sliced up after the completion is whole. The persisted row still holds the finished text with `done: true`, so a resumed session replays through the same reducers. On an endpoint that refuses `stream: true` the whole beat arrives as a single terminal delta — same shape, different timing.
- `character_action` is delivered whole even on the live path: the client folds it into the speaker's open bubble, and that fold only works while the bubble has no spoken text yet.
- **A character beat is one `character_prose` event** — a single first-person passage carrying what the character notices, does and says, with the spoken words in double quotes inline. It delta-streams like any prose event, and the client renders it as plain body text with the quoted runs bolded. The emission format is **untagged prose**: the model writes the passage directly, and may append `<type:state_update>` / `<type:relationship_update>` / `<type:presence_change>` JSON blocks after it. **Only those three tags are honoured** — a `<type:...>` naming a prose kind is scrubbed and the passage continues, because models still emit stray `</type:character_dialogue>` from the old contract and each one used to *open a new segment*: a completion that repeated itself became several byte-identical persisted events (one live turn produced four). `character_dialogue`, `character_action` and `internal_thought` remain on the event union so sessions recorded in the older three-fragment shape replay unchanged. A `<thinking>` block, if a model still emits one, is kept as a private `internal_thought` rather than folded into the passage — deliberation must not reach the visible prose. **A passage is bounded generously** — `character_turn_agent._VOICE_PROSE_TOKENS` (2048, ~1,300 words), several long paragraphs and about four times the longest beat ever measured. That is the *prose* allowance: the request's `max_tokens` is the thinking budget **plus** it, because thinking and answer are paid out of one budget upstream — setting the request budget to the allowance alone starved a live turn, which spent the whole thing deliberating and returned no prose. The bound is operational rather than editorial: nothing in the contract tells a character to be brief, and what it actually stops is the operator's **global** `maxTokens` — one number shared with world building and storyline generation, 48,000 on the install where this was found — being spent on a single spoken beat. Uncapped output was measured twice on the live endpoint and made the writing *worse*: beats averaged 8,228 then 10,184 characters of drift, prompt guidance did not bind it, and every beat that read well was produced with a ceiling in place. Set the constant to `None` to restore unbounded length. **A beat is exactly one `character_prose` event**, whatever the model does: once a passage has opened, no tag closes it and no later text starts a second one. A stray `<thinking>` used to close it in either direction, so a model looping back to the top of its own emission was split faithfully into one event per loop — a single live beat produced five byte-identical rows that read as five beats by the same character. A `<thinking>` block only becomes an `internal_thought` when it arrives *before* the passage; a later one is part of that loop and is dropped by both parsers. Likewise a `</type:state_update>` closing the block that is currently open now ends it instead of opening another, so trailing prose after a JSON body is not a second `state_update`. **One failed beat no longer takes the turn with it.** A single character call can come back with nothing in it — most often *"the model spent its whole budget thinking and never answered"*, which appears on the SECOND beat of a turn where the transcript is longer and the deliberation runs past its advisory budget. That failure is traced as `prose` with `data.skipped` and the scene carries on with whoever else is in the room, wherever in the turn it lands — a live run lost a whole turn to its very first beat under an earlier rule that only salvaged later ones. The terminal `error` frame is reserved for a turn where **every** attempt failed, including the silent-turn backstop's, which is what a dead or misconfigured endpoint looks like and what a one-off starved generation does not. A beat that did not come back is also not counted as played, so the exchange guard and the backstop are not told the player has been answered when they have not.

**A passage's opening is withheld until it proves itself.** Two live beats were persisted and rendered as a character's prose while being the model briefing itself — the output contract read back (*"then main passage then optional structured blocks each opening tag own line JSON…"*) and third-person planning about the character it was supposed to *be*. Both are well-formed language, so the degeneration guard passes them. The engine therefore holds the first 400 characters of a passage before streaming any of it, releasing early — usually inside the first sentence — as soon as a first-person pronoun proves it is a character speaking (`emission.in_the_scene`). If instead the opening carries production vocabulary *and* no first-person pronoun (`emission.looks_like_scratchpad`), or simply begins on a lowercase letter — which the contract's "start in the scene, on your first word" rules out, and which caught a live 62-character fragment of the model's own notes that the vocabulary test missed (`emission.starts_mid_sentence`) — or repeats the opening of a beat that already played this turn (`_echoes_a_beat`) — two characters returning byte-identical passages is not a parser fault but two calls whose prompts differ only by a name and a role, and a live five-turn run produced three such pairs — the passage is discarded before the reader sees a word, and the speaker regenerates **once**, traced as `prose` with `data.scratchpad`; a second leak drops the beat (`data.dropped`) and the turn carries on. Nothing was shown or persisted, which is what makes the retry safe. What is bounded instead is *degeneration, repetition, and runaway*. A hard stop cuts any beat past `_VOICE_PROSE_TOKENS × 4` characters (8,192 today) whatever it is writing — the passage allowance expressed in characters, derived from it rather than chosen separately, because `max_tokens` alone does not bound the prose: thinking and answer share it, so a beat that deliberates briefly can spend the rest on writing (one run produced an 11,998-character beat well inside its token budget, and long beats then feed on themselves through the transcript — prompt tokens went 1,069 → 11,606 across five turns) — an operational backstop, not an editorial one: a live run produced a single 48,000-token generation over 684 seconds, which was well-formed non-repeating prose the whole way (so both quality guards passed it) and left the relay's upstream marked failed, 400-ing the next three turns. With the sampler fixed a passage averages 674 characters, so the stop sits roughly six times past the worst honest case. Below it, once a beat passes 2,000 characters the engine watches its tail, and a stretch that has stopped being language cuts the stream — either almost no distinct words (a token loop) or no punctuation at all in seventy (a drift into a word list, where variety stays high but sentence structure is gone) — or that repeats two hundred characters it has already written, which is what the one-passage rule makes visible (`emission.looks_degenerate` / `emission.repeats_itself`, traced as `prose` with `data.degenerate`). Live runs produced 29,660- and 48,167-character beats that opened as prose and ended in `Rex Rex Rex` / `AT AT AT AAAA`; detecting that is what lets the length stay unbounded.
- **A prose beat enters `turn_beats` whole**, interiority included — the next speaker reads the passage as written. That is a deliberate change from `internal_thought`, which was `private_to_user` and withheld from other characters.
- **Every character beat streams its prose**, including later speakers. The continuity guard that used to hold a later beat back for a complete-line verdict has been retired; nothing now waits on a finished line before showing it.
- `internal_thought` streams with `visibility: private_to_user` (the inline thinking line, folded into the speaker's beat) but is kept out of other characters' context. It **delta-streams**: because the emission format is think→speak, the thought is normally the first thing a turn can show, completing while the spoken line is still being written.
- The validator runs `parse → validate (incl. stat clamping) → repair/retry` before anything reaches the stream.

## Shared Contracts Location

TypeScript types for events and API payloads are hand-maintained in `web/frontend/lib/events.ts` and `web/frontend/lib/types.ts`, kept in sync with `web/backend/app/events/envelope.py` by hand. `web/shared/contracts/` holds only a `.gitkeep` — it is a reserved-but-empty seam, not where the mirror actually lives today. When an endpoint, event, or stat shape changes, update: the Pydantic schema, the frontend type mirror, and this document.
