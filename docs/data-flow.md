# Mytheca — Data Flow

How data originates and moves through Mytheca. The streaming/event path is first-class.

> **Current implementation.** The **Library** is now backend-backed: it reads from and writes to the FastAPI CRUD API via `web/frontend/lib/api.ts` (hand-rolled fetch, await-then-apply), so storylines/characters/settings/scenarios **persist** in Postgres. The backend is seeded with the Embergate world (`web/backend/app/core/seed.py`) so the app looks the same. The **Story player** streams live turns over the backend and **persists every play-through**: each turn's events (incl. hidden thoughts) and the diagnostic trace are saved, so reopening a scenario **resumes its most recent session** with the full history and continues forward (see *Scene Persistence, Resume & Export* below). The seed data (`web/frontend/features/story-player/scene-data.ts`) is now only the fallback opening for a never-played scene. (TanStack Query is still deferred; the hand-rolled client suffices for this CRUD surface.)

## Sources

| Source | Examples | Where it lives |
| --- | --- | --- |
| PostgreSQL (core state) | storylines, characters, settings, scenarios, stat definitions, character stats, events, play sessions, turn traces, context documents (+ links), app settings, graph type definitions | `web/backend/app/models/` |
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
Story player (useScenePlay) → lib/api.postTurn → POST /play/{scenarioId}/turn  {text, directedAt?, sessionId?, povCharacterId?, guidance?, taggedDocIds?, overrides?}
  → routes/play (pre-flight: scenario exists, text present, session valid)
  → turn_engine.run_turn:
      turn_settings.resolve(scenario, req.overrides) → TurnSettings: the scene's play
        controls with THIS TURN's overrides on top (max_turns · suggestions_count ·
        beat_length · planner · register), resolved ONCE before anything reads one.
        The register's provenance now has TWO sources — turn_settings.pitch() decides
        between the player's pin and the planner's read at every beat-producing site, and
        the winner is reported on the `speaker` trace step as `registerSource`. Never written back to the
        Scenario row; withheld from every agent; recorded on the user_turn row for audit
      assembler.assemble_context (Band-1, read-only): ordered cast + clamped stats + loaded
        stat guidance + recent buffer (Redis, best-effort) + scenario subgraph (Neo4j,
        best-effort) + cacheable stable prefix (style guide → World Primer → stat
        guidance, widest sharing scope first) + GATED RAG (retrieval_gate: a cheap
        model-free skip-or-fetch — off-roster entity / world-history question; on fetch,
        _common.rag_block retrieves + injects a fenced RETRIEVED LORE block, best-effort)
        + @-TAGGED FILES (taggedDocIds → assembler._tagged_notes: storyline-checked,
        bounded, framed as reference — see below)
      resolve Player POV member (povCharacterId → a PRESENT cast member, else None)
      events_store: resolve/create PlaySession · record user_turn (seq 0, Postgres; data.pov = POV id | null;
        data.overrides = the non-null override map, absent when nothing was overridden)
      memory.buffer.push_turn (POV → the line as the character's own beat w/ characterId;
        else the plain player line → recent-turn buffer, best-effort)
      intent_agent.interpret: classify the player's line — narrate / address / puppet /
        whole-group — and, for a puppet, which cast member is directed; the same call
        also breaks a DIRECTING line into direction requirements
      scene direction: guidance (POV, its own direction_agent.parse call) else the
        player's own line (Playwright mode, from the intent call above) → an ordered list
        of requirements, each rebound to the narrator if its owner is absent/POV
      puppet beats (if any): the directed character performs it in-voice, up front,
        carrying their own requirements
      ReAct loop — planner_agent.plan_beats decides up to N beats per call, bounded by
        scenario.max_turns (hard per-scene ceiling on every emitted beat) and a runaway
        backstop max(TURN_MAX_BEATS, 2*cast+6); only `present` cast members are
        selectable and the POV character is locked out of the AI roster. The planner
        sees what the direction still owes + the beats left; once what is owed would
        fill them, direction_agent.schedule picks the beat instead:
          decision.action == "speak" →
            graph_reader.relationship_context + offscene_ties (via beat_runner.relationship_note,
              scoped by settings.ties: addressed | scene (default) | world) →
            character_turn_agent.stream_line (prompt ordered stable → transcript →
              volatile for prefix-cache reuse; relationship note folded into the tail)
              → services.llm.chat_complete_stream
            emission.parse_emission: thin <speaker:N>/<type:…> tags → typed segments
              (name→id; out-of-roster drop)
            validator: parse → validate (incl. stat clamping) → repair/retry
            _Emitter: assign per-session seq · persist (Postgres) · push buffer
              · internal_thought → private_to_user (NOT pushed to turn_beats, so later
                speakers never see it) · yield visible events
          decision.action == "narrate" → narrator_agent interstitial, same emit path
          decision.action in ("exit", "end") → loop stops
      follow-up suggestions: director_agent.propose_pov_lines (POV mode) or
        propose_branches (otherwise), emitted as branch_choices
      cold path (post-stream / background): turn_writer.write_turn persists the turn's
        graph-relevant facts to Neo4j
  → StreamingResponse NDJSON ──▶ client
  → read-time: reflection.dispatch_reflection updates cast disposition; on a session's
    first turn, relationships.ensure_seeded seeds graph edges from cast bios
```

On the client, `useScenePlay` (via the generic `useEventStream` hook + `postTurn`) consumes
the stream: **delta-streamed prose** (`narration`, `character_dialogue`, `internal_thought`)
accumulates by event `id` (incremental `text` chunks, `done` flips true last). Those deltas
are produced **live** — `llm.chat_complete_stream` feeds the model's tokens through
`emission.EmissionAccumulator` as they arrive, so a segment reaches the wire the moment the
parser recognises it. The thought therefore completes while the spoken line is still being
written. A `thought` accumulates against `thoughtId` and **never claims the
beat's `id`**, which belongs to the beat's prose — the dialogue if the speaker speaks, the
action if they only act. That is a correctness property, not bookkeeping: the beat's `id` is
what every record control points at, and while a thought could take it, a character who
thought and acted but never spoke handed **Edit** the private thought to rewrite (silently)
and got a 422 from **Re-roll** (`internal_thought` is not re-runnable). A beat that is *only*
a thought therefore has no id and offers no controls, which is the honest answer — a private
aside is not a beat of the story record.

One trace step also reaches the transcript: `speaker` opens the chosen character's beat
**before any words exist** (`pending: true`), so the wait has a place to live and the
thought → speech sequence fills one stable spot instead of pushing the page around. The
status strip stands down for character phases once that beat is open, keeping only the
pre-generation ones (gathering / reading / planning) that no beat can show. A placeholder
that never receives content — a withheld beat, a failed generation, an aborted turn — is
cleared by `dropPendingBeats` when the stream settles. A speaker's `internal_thought`,
`character_action`, and `character_dialogue` **all fold into one `char` beat** (the thought
opens it, action + dialogue merge in as they arrive — `mergeFrame`/`isOpenCharBeat`), so a
message reads as one moment: the character's name, then **one bubble** holding their muted
**thinking** line and the spoken line at the **same text size** (`QuotedText` bolds any quoted
run, keeping the quotes). `state_update` / `branch_choices` drive the side panels. A scene seeds
**narrator-only** (no character speaks before the player acts); selecting a follow-up suggestion
**writes its text into the composer** (focused, for review/editing) rather than auto-sending —
the player edits and sends it as an ordinary turn. A **scene-config menu** (`SceneConfigMenu`, a
popover now rendered by the **composer's bottom-left controls row**, opening upward) sets three
per-scene controls — Max turns, Suggestions, and **Number of beats** (the context-window depth,
5–100). Its token readout is **content-real**: `lib/contextBudget.beatsTokensFromTexts` sums the
actual last-N transcript beats (fed down as `beatTexts`), falling back to the flat
`estimateBeatsTokens` average only before a scene has beats. Persisted on the scenario
(`updateScenario` PATCH); four suggestions render as a **2×2 grid**.

**Player POV.** A `povCharacterId` (the *Speaking as* select in the composer, to the right of
the Config button) makes the player's line **that character's line**. Server-side: the line is
seeded into `turn_beats` and the recent buffer as a **`character`** beat (so later speakers
react to it as "Mei said X"), persisted on the `user_turn` row as `data.pov`, but the visible
`character_dialogue` event is **withheld** (the client already shows the line — see below). The
POV character is dropped from the planner *and* puppet rosters (`locked_id`) so the AI never
voices a second beat for them; a defensive backstop coerces any stray `speak(<pov>)` to `end`.
The POV character still **reflects** at end-of-turn (it is marked already-acted) so its interior
stays current for when the AI takes it back over. Client-side: `useScenePlay` holds `pov`
(default `null`, reset when the chosen character is no longer present), the optimistic bubble
becomes a right-aligned **player-authored character beat** (`SceneMessage.fromPlayer`, rendered
by `TranscriptBeat`'s `PlayerAsCharacterMessage` with the character's monogram/name/color), and
on resume the current POV is derived from the most recent `user_turn.data.pov`;
`rehydrateFromHistory` turns a `user_turn` row with `pov` set into that same right-side
character beat (without `pov` it stays a left-side player beat).

**Scene direction.** The player directs the scene, and the turn is held to it. The **direction
row is always rendered** (`components/feature/DirectionRow.tsx`); what changes between modes is
its *role*, never whether it exists. In Playwright mode it is a one-line labelled strip — the
message box below already carries the direction, so there is still exactly one text input. Under
Player POV the message box holds the character's line instead, so the same row expands into the
direction textarea (`guidance`). Until the row was unconditional the whole direction concept was
invisible to any player who had not happened to pick a POV character. The panel
grows upward as it fills, capped then scrolling, so it lifts the transcript rather than covering
it. `useScenePlay` clears the box on send (the direction applies to that turn only) but **not** when
POV is dropped — the direction is a scene-level intent, not a POV artefact, and with the row in
both modes clearing it would silently discard what was written. Server-side the direction becomes an ordered list of `direction_agent`
requirements — parsed on its own call for POV guidance, or lifted off the intent call that
already read the player's line in Playwright mode — and the turn engine schedules them across the
scene's `maxTurns` budget: the planner paces them while there is room, and once what is owed
would fill every remaining beat the engine takes over (`direction_agent.schedule`), collapsing
the last beat to narration when several characters are still owed. Each beat's prompt states
only *its* requirements, as outcomes rather than lines, so the speaker reaches them in their own
voice. Progress is visible in the Inspector as `direction` trace steps.

**Attempted is not delivered.** A requirement used to be marked satisfied the moment it was
put *into* a prompt — a promise, not an outcome. A beat that came back empty, was withheld as
a scratchpad leak, failed against the endpoint, or simply talked about something else still
ticked it off permanently; it is the single largest reason a direction gets "forgotten".
(Observed live: a trace reading *"The narrator delivered 1 part(s) of your direction"* on a
turn where zero beats were persisted.) Delivery is now two steps:

- `direction_runtime.attempted(...)` **before** the beat — marks `attempted`, bumps
  `attempts`, traces *"N part(s) of your direction ride on X's beat"*;
- `direction_runtime.confirm(...)` **after** it, with the prose the beat actually emitted
  (read off `turn_beats`, where every emitting path already records what it wrote). A beat
  that produced nothing confirms nothing and the requirement simply stays owed — that alone
  fixes the failure cases with no heuristic. For a beat that *did* write, the lexical check in
  `services/direction_check.py` decides: the fraction of the requirement's content words the
  prose contains, against `DIRECTION_COVERAGE_THRESHOLD` (0.34 — roughly one in three, because prose paraphrases a requirement's verbs and keeps its concrete nouns), with the bound actor's own
  name excluded (a requirement reads "Mei snaps back" while Mei's own in-voice beat never says
  "Mei"). It is deliberately crude and costs no LLM call — it runs after every beat — and it is
  used only to *withhold* confirmation: an unconfirmed requirement is retried up to
  `DIRECTION_MAX_ATTEMPTS` (2), so a false negative costs one extra beat while a false positive
  would silently drop what the player asked for.

The closing trace therefore reports **three** counts, not two: delivered, `unconfirmed`
(attempted, out of attempts, never confirmed) and `never` (the turn ran out of beats first).
The client's checklist mirrors those three states — `✓`, `◐` "the scene may not have reached
this", `○` — distinguished by glyph and words, not colour alone.

**The player can name the target.** The direction box is read **per line** on send
(`mentions.splitDirectives`): each line is one thing the turn owes, and an `@` cast mention on
that line aims it at that character, sent as `TurnRequest.directives`. When those are present
the engine builds the requirements from them **verbatim and spends no LLM call** — there is
nothing left to infer. A line with no cast mention is the narrator's to place, and a box with
no cast mention *anywhere* sends no directives at all and is parsed server-side exactly as it
is today (otherwise "Mei storms out and Aldous grabs her wrist" would arrive as one
requirement instead of two).

A target the player set is **pinned**, and `rebind()` never re-owns a pinned requirement. Two
cases, and neither is a rebind: if the character is present (including when they are the POV
character) it stays theirs — the AI not voicing them does not mean the requirement cannot be
met, and silently re-owning it is what made "everything you aim at your own character" vanish;
if the character is absent it is marked **blocked**, reported on its own trace row ("Mei is not
in the scene — this part is waiting"), excluded from scheduling, and carried over. An *inferred*
target keeps the old narrator rescue, because a guess deserves one and an instruction does not.

**The direction outlives the turn.** Whatever is not delivered is written back to
`play_sessions.standing_direction` and re-owed on the next turn, **ahead of** whatever is asked
then (oldest debt first — it is the part most at risk of never landing, and the player asked for
it first). Duplicate text collapses onto the standing entry, so restating a direction does not
double the debt, and the merged list is capped at `MAX_REQUIREMENTS`. A resumed scene reads it
from `SessionHistory.standingDirection`, and the player can cancel any of it via
`POST …/sessions/{id}/standing-direction` — a debt that cannot be cancelled would be a bug, not
a feature. The column is **stored, not derived**: it could be replayed from the `direction`
trace rows, but that would make the turn loop's correctness depend on diagnostics being
retained, and traces are the first thing an operator prunes.

**One-tap verbs.** The direction row carries a grouped verb bar (`lib/sceneVerbs.ts` +
`SceneVerbBar`): Pace · Tone · Event · Exit. Two rules make it worth reading, both aimed at the
old flat row's problem of being ignored. Each verb owns a **phrasing distinct from its label** —
tapping *Escalate* writes "Something makes this worse — push the moment past where it was going"
into the direction target for the player to edit, because a verb exists to hand them a sentence
to argue with rather than a command to fire. And **a verb that cannot mean anything is not
offered**: *Someone arrives* only when the storyline has cast outside the scene (and it expands
into a submenu naming them, which raises a Phase 9 request rather than an arrival), *Move the
scene* only when the storyline has more than one setting, *Wrap this up* / *End the scene* only
once the player has taken `MID_SCENE_TURNS` (3) turns. The insertion target follows the row's
own two modes: the direction box under POV, the **message box** in Playwright mode. The inserted
text is *selected*, so one keystroke replaces it, and it is added as a **new line** — each line
of the direction box is one requirement (see `directives` above), so appending to the sentence in
progress would merge two into one. A scene may add up to 8 of its own verbs
(`scenarios.direction_verbs`), appended to their group after the built-ins and never gated —
the author knows this scene better than a generic condition does.

**Pacing.** How many requirements ride on one beat is `direction_runtime.pace(owed, remaining)`
= `ceil(len(owed) / remaining)`: one per beat while there is room, more only when the budget
forces it. The old code used a fixed `[:1]` slice at the per-beat sites and an all-or-one
switch at the opening, which is how the tail of a long direction went missing. `guidance` **is** persisted, on the
`user_turn` row, and restored into the box on resume (`turn-stream.latestGuidance`), so reopening
a scene does not silently drop what the player asked it to do.

A turn may be **direction only** — `guidance` with an empty `text`. Under POV that is the only
way to steer without also making the character speak, so the send guard is "a message **or** a
direction", not "a message". Such a turn writes its `user_turn` row with `text: ""` (keeping its
trace grouping and its place in the export) and pushes nothing into the recent-turn buffer,
exactly like a *Continue* — but it is not silent, and the differences are deliberate: the `turn`
trace reads *"You directed the scene"* with the direction as its detail (`data.directionOnly`),
the export renders `_(direction only)_`, the tray falls back to the direction for its label when
no spoken line exists yet, and the transcript shows a quiet centred **aside** rather than a
speech bubble — nobody in the story heard it. On reload the same row replays as that aside
(`rehydrateFromHistory`), while a text-less, direction-less *Continue* row replays as nothing at
all.

**Type-while-streaming:** the composer's `sendDisabled` prop (renamed from `disabled`) blocks
only the Send button and Enter key while a turn is in-flight (which is also disabled when both
the message and direction boxes are empty — there is nothing to send) — the `<textarea>` remains editable
so the player can compose their next message while characters respond. `useScenePlay.send`/`submit`
still guard against concurrent submissions. A mid-stream failure surfaces the terminal `error`
frame.

**Context-usage path (exact, with an estimate fallback).** `useScenePlay` fetches
`getLlmContextWindow()` once on mount (best-effort; the dial is hidden on failure). The denominator
is the `maxContextTokens` field from `GET /options/llm/context-window` (`source: "detected"` when
the engine was probed, `source: "configured"` for the stored fallback). The numerator is the
**exact** figure: after each character generation the turn engine emits a persisted `context`
trace step carrying the LLM's reported `usage.prompt_tokens` (`llm.chat_complete_usage` →
`character_turn_agent.generate_line_with_usage` → `_generate_speaker`). `useScenePlay` sets
`liveContextTokens` from that live `context` frame and seeds it on resume via
`turn-stream.latestContextTokens(history.traces)`; it exposes `usedTokens = liveContextTokens ??`
the char/4 estimate (`estimateUsedTokens` over the whole transcript — the client no longer holds a window depth to slice by) plus `usedTokensExact`.
This drives `ContextUsageDial` in the composer's bottom row — a small circular **button** whose
visual-only ring colour-codes green < 50 %, gold 50–75 %, danger ≥ 75 %. The count is not printed
in the ring; it surfaces on hover/focus in a tooltip (`8.3K of 16K tokens · 56% · exact`, via
`fmtTokensK`), which is also the button's `aria-label`. The estimate is shown only until a real
turn (or a resumed session's trace) supplies the exact count; an endpoint that reports no `usage`
keeps the estimate.

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

**Turn status — who is up (live-only).** Alongside the per-character map, `turn-stream.applyTurnStatus`
folds the same frames into the scene's **single** current focus: `{ phase, characterId?, name? }`,
where `phase` is `idle | thinking | speaking | acting | narrating | ending`. A `speaker` trace step
opens `thinking` (and carries the name the trace reports); `internal_thought`/`character_action`/
`character_dialogue` move it through the character phases; `narration` sets `narrating`; and a `plan`
trace step with **`data.end === true`** sets `ending` — the structured end-of-beat-loop marker the
engine stamps (see `api-contract.md`), so no client has to match on the step's prose title. `ending`
is sticky, since the turn's trailing `branch_choices`/`commit`/`reflection` frames are not beats. The
reducer returns the **same reference** when nothing changes, so a delta chunk cannot re-render the
consumer per token. `useScenePlay` holds it as `turnStatus`, resets it to idle in `submit`'s
`.finally` (so a stream that dies before the end-of-turn trace cannot leave anyone stuck "about to
speak"), and `StoryPlayerView` renders it as the `TurnStatusStrip` at the foot of the transcript —
the only speaker signal below the `lg` breakpoint, where the cast rail is hidden.

**Model output is sanitized centrally.** Reasoning models inline their chain-of-thought and
harmony-style channel tokens (`<|channel|>…`, `<think>…</think>`, `*Check:*`/`*Revised:*`) in
`message.content`. `services.llm.chat_complete` — the one generation call every agent shares —
runs each reply through `_common.strip_reasoning` (drop `<think>` blocks, keep only the text
after the last channel marker, scrub residual control tokens) before returning it. So the
**narrator** prose, the **character emission** (parsed downstream by `emission.parse_emission`),
and the **authoring JSON** agents all receive only the model's final answer; the scrub keeps
the app's own `<speaker:>`/`<type:>`/`<thinking>` markers intact.

**The output budget is fitted to the model's context window.** Options' *Max tokens* is an
**output** budget, but an OpenAI-compatible server counts prompt + completion against one
window — so a saved value at or near the model's context length 400s on every generation
regardless of prompt size (this surfaced as a blanket 502 on `POST /api/characters/draft`).
`services.llm.chat_complete` reads the window out of that 400 (`maximum context length is N
tokens`), caches it per endpoint+model, clamps `max_tokens` to `N − estimated prompt − 512`,
and retries **once**; later calls to the same endpoint are clamped before sending. A prompt
that leaves under 256 tokens of room raises a plain "prompt is too long for this model's
N-token context window" instead of a raw upstream 400, and non-context 400s are untouched.

The hot path is **read-only** — all mutation (durable consequences, edges) defers to the
cold-path turn-writer (a later phase); stat changes are clamped during validation.

### @-tagged context files (the `@` command)

The player types `@` in either composer box and picks from **one namespace holding two
kinds** — the present cast, and the storyline's context documents — because they type one `@`
and do not think about which subsystem a name belongs to. The menu separates them into two
labelled `role="group"` sections, and `kind` splits the ids back apart on send, since what they
do is opposite: **a character aims the line** (`directedAt`, from the first cast mention in the
*message* box — one named in the *direction* box is the subject of the direction, not the
addressee), while **a file grounds it** (`taggedDocIds`, injected into **this turn only**). The
roving highlight addresses a flat index across both groups, so the composer's keyboard handling
is unchanged. Within each match tier, cast is ordered before docs, so a typed `@M` reaches Mei
before `maerin.md`; tier still beats kind, so a file whose name *starts* with the query wins over
a character who merely contains it.

`useScenePlay` builds the combined list itself (`mentionOptions`) rather than taking it from the
view, because who is present is the hook's own state.

```
Composer (@ menu over useScenePlay.mentionOptions = present cast + useSceneData.contextDocs)
  → useScenePlay.send: stripMentions(message) + stripMentions(direction)
      → the `@` sigil is dropped and the NAME KEPT ("read @maerin.md" → "read maerin.md")
        + the ids still present in the text
  → POST …/turn { text, guidance?, taggedDocIds }
  → assembler._tagged_notes(db, storyline_id, ids):
      reject any doc from another storyline · dedupe · cap (5 docs / 6 000 ch each / 12 000 total)
      → TurnContext.tagged_notes  (a slot SEPARATE from retrieved_lore)
  → character_turn_agent: prompt MIDDLE, after retrieved_lore, BEFORE the direction line
  → narrator_agent:      before the direction cue
  → `files` trace step → the Inspector's Files row
```

**Why it cannot redirect the story.** This is the constraint to preserve when changing the
turn loop. Tagged text is deliberately withheld from `intent_agent` and `direction_agent`
(so it can never become a schedulable `DirectionRequirement`) and from `planner_agent` (so it
can never change whose beat is next) — it reaches only the two agents that write prose. Its
prompt position is equally deliberate: the character prompt's TAIL is the act-now region, so
the block sits in the MIDDLE and *above* the player's direction, which keeps the recency
advantage. The block's own wording states the precedence: the notes keep facts straight in
what a character or the narrator says; the beats and the direction decide what happens; on
conflict the scene wins.

**The sigil goes; the name stays.** `stripMentions` used to delete the whole `@<name>` token,
so `"Hey @Mei"` was sent as `"Hey"` and `"read @maerin.md"` as `"read"`. That is wrong twice
over: it reads as a visual glitch as the chip appears, and it removes the one noun the sentence
was about, so the intent and direction agents never see who or what the player meant. Only the
sigil is dropped now, and the name survives with the player's own casing. Untagging — the chip's
"×" — is therefore a *different* operation and has its own function, `removeMention`, which
deletes the whole token plus one trailing space. The ids are still re-derived from the final
text, so hand-deleting an `@name` still untags it; the bare name left behind by stripping is not
a tag, because only the `@` makes one.

Tagging is independent of `includeRag` — a file excluded from retrieval is still taggable,
which is the point: `retrieval_gate` skips most turns and `rag_block` truncates each hit to
600 characters, so the passage the player actually wanted routinely never arrived.

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

- **A scenario holds many play-throughs.** `PlaySession` also carries `name` (the player's own
  label), plus `parent_session_id` + `fork_seq`, which are set together on a play-through forked
  from another and record where it diverged. `POST /play/{id}/sessions` opens a fresh, empty one
  **without touching the existing sessions**; `PATCH …/sessions/{sid}` relabels; `DELETE
  …/sessions/{sid}` removes it with its `events` and `turn_traces` (deleted explicitly rather than
  via the FK cascade, so Postgres and the SQLite test/dev database behave identically). All three
  live in `routes/play_record.py`, separate from `routes/play.py`, which carries the turn stream.
  The story player's play-through tray is the surface over them.

- **History mutation goes through one module.** `services/session_state.py` is the only place a
  play-through's record changes after the fact — rewind, branch, edit and re-roll are four faces
  of the same three operations, and four separate implementations would drift silently. It gives
  `truncate_session` (cut rows after a seq, then re-derive), `copy_history` (fresh ids, **same
  seqs**, so ordering and `UNIQUE (session_id, seq)` both hold in the new session),
  `rebuild_buffer`, `replay_stats`, `prune_graph_events`, `turn_boundary` (a rewind cuts at a
  **turn boundary**, because `turn_traces` are keyed by the turn's opening seq) and
  `require_expected_seq` (optimistic concurrency — a stale precondition 409s, where a `busy`
  column could be left set by a client abort and wedge the session).

  Per store: **Postgres** is canonical and everything else is re-derived from it; the **Redis
  recent-turn buffer** is rebuilt, never patched; **Redis interior state** is *cleared*, not
  rebuilt (see below); the session's **outstanding direction** is pruned to what surviving turns
  raised; **Neo4j** `:Event` nodes are pruned by their deterministic id, though relationship
  *edges* written by cut turns are not rolled back (no per-turn provenance — recorded in
  `docs/checklist.md`); **session stats** are cleared and replayed from the surviving
  `state_update` rows; **presence** re-derives for free from the surviving
  `character_status_change` rows. **Qdrant is not involved** — nothing on the play path indexes
  transcript text, so an edited beat has no stale embedding.

- **What a rewind actually makes the scene forget.** Cutting the rows is the easy half; the
  state *derived* from them is what decides whether the scene behaves as though the cut turns
  happened. Two of those were missed until they were measured
  ([`EXP-2026-08-014`](research/experiments/EXP-2026-08-014-record-controls/)), and both are
  things a row-oriented cut cannot see:

  - **Per-character interior state** (`memory/interior.py`, `interior:{session}:{character}`) is
    each character's current stance and retrospective, written by `services/reflection.py` after
    every turn and read straight into the prompt by `assembler._build_cast`. It is **cleared**
    (`interior.clear_session`) rather than rebuilt — there is no surviving row to re-derive a
    stance from, and there is only ever one record per character, so a survivor would always be
    a stance formed partly from beats that no longer exist. The next turn's reflection writes a
    fresh one. Over-clearing costs one recomputation the turn performs anyway.
  - **`PlaySession.standing_direction`** carries what a turn could not deliver so the next turn
    re-owes it. `session_state.standing_through` keeps only the rows whose `fromTurn` (the
    raising turn's `Event.seq`) is at or below the cut. A row with no usable `fromTurn` is kept:
    an un-cancelled requirement costs a beat and is reported as outstanding, while a
    wrongly-cancelled one silently loses what the player asked for.

  The same `standing_through` is what a **branch** uses to carry the parent's debt to the fork.
  A fork inherits the direction (it is what the player asked for and has not been given) and
  does **not** inherit the rolling summary (it is a derived record that would go stale the
  moment the branch diverged, with no seq to notice by).

- **A re-roll's window stops where its beats do.** `turn_setup.context_for_replay` takes a
  `through_seq` — the beat before the target — and passes it to `assemble_context`, which trims
  that many entries off the **tail** of the transcript window before `_build_cast` reads it for
  voice anchors. Without it the window came straight off the Redis buffer, which still holds the
  beat being replaced and everything after it, so the model was asked for another version of a
  line it could see and continued from it instead. `through_seq=None` — every ordinary turn —
  leaves the window byte-identical, which a test asserts.

- **Stat values are scoped to a play-through.** `session_character_stats` holds what a stat is
  worth *inside one story*; `character_stats` holds the character's **authored** starting value.
  Play reads and writes the session scope (`services/session_stats.py` — `resolve` / `apply`,
  reached from `validator`, `turn_effects` and `assembler`); the Library and world population read
  and write the baseline (`services/stats.py`, `routes/stats.py`). Resolution when play reads a
  stat is: the play-through's row → the character's authored value → the definition's `default`.
  `StatDefinition.carry_over` works the other way: on `close_session`, a stat marked to carry
  writes its value back onto the character so the **next** scene opens where this one left off.
  Owner decision D-1 — before it every value was character-global, so two play-throughs of one
  scenario shared a health value and a rewind could only reconcile to whichever session was open.
  The story player needs no change for this: it already paints from the character baseline and
  replays the session's `state_update` events on top, which is exactly the new semantics.

- **The turn's own inputs are persisted.** The `user_turn` row's `data` carries `guidance` (the
  scene direction) and `taggedDocIds` alongside `text`, `directedAt` and `pov`. Both were
  previously request-only and died with the turn, which meant a reload could not restore the
  direction into the composer and an export could not show what the player asked for against what
  the turn delivered. Rows written before this carry neither key.

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
  → Validator confirms the stat exists and clamps the result to [min, max]
  → session_stats.apply writes it to THIS play-through (session_character_stats), never to
    the character's authored row — a branch or a rewind of another play-through is untouched
  → emitted as a state_update event, with visibility="hidden" when the StatDefinition says so
  → event streamed to the UI (carries the change's characterId, key, clamped value, reason)
    — UNLESS hidden, in which case the row is persisted and simply not yielded, and
    rehydrateFromHistory skips it too so a reload agrees with the live stream
  → Director rail's Scene-state chips update (flat, global) AND the per-character store
    (`statsByChar`, keyed by characterId) updates
  → narrator may reference the new state next turn
```

**Where a value lives, and what survives the scene** (owner decision D-1). Play writes
`session_character_stats`; `character_stats` holds the character's **authored** starting
value and is what every new play-through begins from. `StatDefinition.carry_over` decides
whether a play-through's ending value writes back onto the character at session close
(`session_stats.carry_forward`) — the default is `false`, so a stat is scoped to the
play-through it moved in unless it says otherwise. That write **overwrites the authored
value in place**, which is why `character_stats.baseline` captures it once, the first time it
would be destroyed, and `POST /characters/{id}/stats/reset` restores from it.

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

The event schema's live TypeScript mirror is hand-maintained in `web/frontend/lib/events.ts` and
`web/frontend/lib/types.ts`, kept in sync with `web/backend/app/events/envelope.py` by hand, and
documented in `docs/api-contract.md`. `web/shared/contracts/` is a reserved-but-empty seam (only a
`.gitkeep`) — not where the mirror actually lives today. Keep the backend schema, the frontend
mirror, and the docs in sync.

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
  → Story player, on mount: GET /api/options/scene-presets (best-effort — a failure leaves
      the picker unrendered and every underlying control exactly where it was)
      → picking one is a single PATCH /api/scenarios/{id} carrying maxTurns +
        suggestionsCount + beatLength + scenePreset. The controls stay authoritative;
        scenePreset records INTENT, so moving one afterwards reads as "modified" and the
        reset re-applies the named values.
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
  → director_agent     reads ctx.prompts["director.who_is_up"] / "director.rerank" / "director.branch" / "director.pov_branch"
  → planner_agent      reads ctx.prompts["planner.system"]
  (each falls back to prompt_registry.default(key) when the key is absent from ctx.prompts)
```

**`director.who_is_up` and `director.rerank` are inert on the live turn path**: `director_agent.who_is_up`
and `director_agent.rerank` are dead code, called only from `utils/tests/backend/agents/test_director_agent.py` —
the per-beat decision on a real turn is made by `planner_agent.next_beat`. The keys that actually affect a
live turn are `director.branch`, `director.pov_branch`, and `planner.system`.

The **prompt registry** (`web/backend/app/agents/prompt_registry.py`) is the single source of
truth for the four writing agents' system prompts. It defines `PromptSpec` (key, agent, label,
description, default) and `PROMPT_REGISTRY` with exactly eight keys. `resolve_prompts(*layers)`
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

### Why the long generations stream keep-alives

Every LLM-backed authoring call holds a connection open with **nothing on it** for the
whole generation. Measured on this checkout:

| Path | Time to first byte | During generation |
| --- | --- | --- |
| `POST /storylines/agent/create/stream` | 4–16 ms | headers, then **0 bytes for 24 489 ms**, then the body in one burst |
| `POST /storylines/primer` (blocking) | **7 112 ms = the total** | **no bytes at all** until done |

`core.converse` runs its LLM call to completion before the first `yield`, so streaming
alone does not put anything on the wire. Idle sockets get reaped, and because the
blocking endpoints have not sent headers yet, the browser reports that as a rejected
`fetch()` — *"Could not reach the server."* — while the model is still generating.

`events/stream.with_keepalive` fixes this for the agent streams: the source runs on a
daemon worker thread feeding a queue while the request thread emits an `AgentStatusFrame`
every 10 idle seconds. On the client, `lib/api.ts` retries a connect-time failure once on
a fresh connection for the calls that write nothing, and reports a post-headers drop as
`connection_lost` rather than as an unreachable server.

**Still open:** the blocking generation POSTs (`/storylines/primer`, `/storylines/draft`,
`/storylines/triage`, and the character/setting/scenario draft + art endpoints) have no
keep-alive because they are not streams. The retry covers a sporadic drop; a hard idle
timeout shorter than the generation would need them converted to NDJSON streams, mirroring
the existing `/triage` + `/triage/stream` pair. See `docs/checklist.md`.

### Context files → the storyline assistant

The New / Edit Storyline page carries the same `docsOverview` grounding into the
**conversational** storyline agent, so the files the author uploaded shape every
generated field — not just the primer:

```
TriagePanel (right sidebar)                 StorylineCreatorView
  drop .txt/.md → useStorylineCreator.docs     ↓
  per-doc Draft toggle + bulk De-select All  useStorylineAgent.getDocsOverview()
      ↓ (docs.filter(useDraft) → concatDocs)     ↓ read PER TURN
  → POST /api/storylines/agent/create/stream  {scope, messages, fields, docsOverview?}
    POST /api/storylines/{id}/agent/edit/stream
      → routes/storylines → agents/storyline_edit/{creation,editor} → core.converse
          → _common.docs_block(docs_overview)  [capped at DOCS_CAP]
          → folded into the system prompt beside world_context + rag_block
```

A dropped file is **Draft-on by default** (`toCreatorDoc`), so uploaded material
grounds the assistant without per-row toggling; the panel's **De-select All /
Re-select All** strip clears or restores the whole selection in one click, and the
`ContextBudgetMeter` shows the cost live. The grounding is read **per turn**, so a
file dropped mid-conversation applies from the next message onward. This is transient
prompt context only — the corpus is persisted separately by `commitWorld` through
`…/context-docs/bulk` (see *Context Document Flow* below).

## World Population Flow (create → populate → redirect)

Creating a world used to stop at the container: the storyline, its stats, and its
corpus were persisted and the author was redirected into a Library with empty
Characters and Settings columns. **Create World** now finishes the job.

```
StorylineCreatorView → Create World
  → BuildWorldModal  {enabled, withArtwork}   ← asked, with artwork pre-checked only
    (probes POST /api/options/comfy/status)      when a ComfyUI server answers
  → useStorylineCreator.createAndBuild
       storylineCreator.commitWorld
         1. POST /api/storylines                        (the world)
         2. POST /api/storylines/{id}/stats             (its stat schema)
         3. POST /api/storylines/{id}/context-docs/bulk (the triaged corpus)
       storylineCreator.runPopulate  (re-attaches from lastSeq if the socket drops)
         4. POST /api/storylines/{id}/populate/stream {docsOverview, source, withArtwork, fromSeq}
              → routes/storylines → services/world_populate_runs (background run + frame log)
                   → services/world_populate.populate_world
                   → THE AUTHOR'S FILES FIRST:
                       character/setting docs → agents/extract_agent.extract_entities
                         → one entity per NAMED subject, drafted from its own paragraph
                         → crud.add_document_link (provenance back to the file)
                       other docs → lore grounding only, never entities
                   → only if there are none (or source="invent"):
                       agents/roster_agent.propose_roster    (names + one-line seeds)
                   → per character: draft_character → crud.create_character
                                    → propose_voice_samples  → update
                                    → propose_starting_stats → services/stats
                                    → [artwork] services/portraits
                   → per setting:   draft_setting  → crud.create_setting
                                    → [artwork] services/scene_art
              ← NDJSON: status · plan (the named roster) · entity (per persisted row)
                        · error · done — every frame sequenced
              → foldPopulateFrame → BuildState → rendered live in the dialog
  → only on `done`: router.push(`/{id}`) → LibraryView loads GET …/characters + …/settings
```

The dialog **is** the progress report: it asks whose people to build (its counts come
from the author's classified files), names the roster before drafting starts, lists each
character and place as it lands (with its portrait once painted), and cannot be dismissed
by backdrop or Escape while building — Stop is the only exit. The run itself lives on the
server, so a dropped connection is only a lost view: the client re-attaches from the last
frame it saw and the build never restarts or double-builds. The author is
taken into the new world only when the run finishes; a failed, stopped, or truncated run
leaves the dialog up with what was built and an explicit way in.

Population runs **last, against the persisted world**, so the roster is grounded in
the saved storyline and corpus and each entity is written straight into it (picking up
the usual graph + RAG sync through `crud`). Two failure postures: the roster is fatal
(nothing to build), every entity is not — one failed draft, proposal, or render emits an
`error` frame, the run continues, and the world is never rolled back. The world's id is
held by the hook throughout, so a failed build is always a world that exists and can be
entered — never a lost create.

## Character Authoring Flow (creation-time agent + portrait)

```
Character modal (CharacterModal) → lib/api.ts
  → POST /api/characters/draft            {seed, docsOverview?, storylineId?}
        → {name, role, traits, speech, goal, secret, appearance, background, personality, color}
  → POST /api/characters/portrait-prompts {name, appearance, traits, species?, artStyle?, ...} → {positive, negative}
  → POST /api/characters/portrait         {positive, negative, artStyle?}  → {portrait: "/media/portraits/<id>.webp"}
        → routes/characters → agents/character_agent (draft/prompts/voice/stats; same
          settings_store + services/llm.chat_complete as the storyline agent)
        → routes/characters → services/portraits → services/comfyui.generate
          (art-styled pipeline) → PNG → Pillow → WebP saved under MEDIA_DIR, served at /media
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

The `voiceSamples` then feed the runtime turn loop, and they are the **highest-salience
block in the generation prompt** — concrete proof of how this person sounds, which the
model imitates far more readily than it follows any abstract instruction to adapt. Each
pair therefore carries a **`moment`** tag (`light` · `neutral` · `tense` · `grave`, or
empty for "any moment"), authored in `VoiceSamplesEditor` and proposed by
`character_agent.propose_voice_samples`, which is required to cover the range — at least
one pair must show the character with their habitual manner stripped away.

`assembler._build_cast` carries the pairs **raw** on `CastMember.voice_sample_rows`
(selection is per beat, assembly is per turn) alongside the pre-rendered all-samples
`voice_samples` block that `director_agent` reads. `character_turn_agent` then renders
only the pairs matching the beat's register, plus untagged ones, into the prompt HEAD —
so on a grave beat the character is shown itself in a grave moment rather than its
at-rest banter. `assembler.select_voice_samples` falls back to the **whole** profile
when the register is absent or nothing matches, so a world authored before the field
never loses its voice profile.

Same **creation-time, no-RAG** rules as storyline authoring. Everything produced
is a character's **own base identity** (§1 node properties) — no graph structure
is built here. Portrait generation is an explicit, opt-in step (it spends GPU
time on the local ComfyUI server); starting stats are **proposal-only** until the
author saves them. **"Draft with Mytheca" fires on a seed sentence, a Draft-tagged
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
the local ComfyUI server). As with characters, **"Draft with Mytheca" accepts a
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

## In-Narrative Scene Image Flow (the player's Create image action)

```
Story player → CreateImageBar "Go" → useScenePlay.createImage → lib/api.postSceneMoment
  → POST /api/play/{scenarioId}/moment/stream   {sessionId, beats?}
        → routes/play.play_moment
            services/scene_moment.prepare_moment  (BEFORE the 200 opens)
              scenario + session + ComfyUI base + LLM connection resolved
              last N visible beats (default 8, clamped 2-40) from the session's events
              in-frame cast = present characters active in that window
                              (falls back to the present cast for pure narration)
            then services/scene_moment.generate_moment, wrapped in with_keepalive:
              frame: {type: moment_stage, stage: "prompt"}
              → agents/moment_agent.write_moment_prompt (world + place + beats + cast look)
                  → services/llm.chat_complete → {positive, negative, caption}
                  → strip_names() rewrites any leaked name as that character's visual tag
              frame: {type: moment_stage, stage: "render", positive, caption}
              → services/comfyui.generate at 1216x832 (landscape, fresh random seed)
                  → PNG → services/media.save_webp → MEDIA_DIR/moments
              → build_event("scene_image", ...) at next_seq → events_store.persist_story_event
              frame: the scene_image story event  (terminal)
  → turn-stream.mergeFrame appends a `kind: "image"` beat → SceneImageBeat (centered,
    clickable) → SceneImageModal on click
```

The **only story event a player triggers directly**, and the only one not produced by the
turn loop. Because it is a persisted event and not a column, it replays through the same
`mergeFrame` reducer on reload, appears in the session history, and exports as a Markdown
image line — no separate rehydration path.

Three properties are enforced by the server, not by the prompt writer's goodwill: the frame
is **pinned landscape** (1216x832 in `scene_moment.py`, not the Options defaults, which
are tuned for portraits), the **art style** is applied at the render boundary rather than
trusted to the prompt (see below), and no character **name** may reach the image model — the system
prompt forbids it and `strip_names` rewrites any that survive into that character's own
appearance phrases, because an image model cannot resolve a name into a face. The keep-alive
heartbeat re-emits the stage that is *actually* running, so a long prompt write never
reports itself as a render.

## Art Style Resolution (every image path)

```
any image request  ─ artStyle? ─┐
                                ▼
   settings_store.resolve_art_style(db, artStyle)
        artStyle ?? comfy.artStyle (the operator's default)  → art_styles.get(…)
        ∪ comfy.styleLoras[id]                               → ResolvedStyle
                                ▼
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
  the prompt WRITER                              the RENDERER
  agents/_style.resolve_style →                  art_styles.apply_style(…, surface)
  model_hint + <surface>_tags into               drop other styles' tags → append this one's
  the agent's system prompt                      comfyui.generate(lora_name, lora_strength,
                                                                  lora_enabled)
                                                   enabled → patch node 72
                                                   disabled → _bypass_node routes around it
```

`resolve_art_style` is the **single** answer to "what look, and with which LoRA?", and both
halves must agree: prompts *written* for one style and *painted* in another produce a
muddle. Unknown ids fall back to the default rather than raising — an image request must
never fail because a stale client named a retired style.

`apply_style` **drops** competing style tags before appending its own, which is what makes a
switch actually switch: a prompt stored while painted still ends in `watercolor portrait,
soft washes`, and `painted`/`anime` both push `photorealistic` away — a negative that would
flatly contradict a `photoreal` render. It is also the only place the look can land on a
**hand-written** prompt (`SceneImageModal`'s repaint), which no agent ever sees.

The three render services (`portraits` · `scene_art` · `scene_moment`) are the only places
bytes are requested from ComfyUI, which is why applying the style there covers every image
in the product. The **world build** (`services/world_populate.py`, the New Storyline page's
build step) calls the first two directly, and threads one `art_style` — chosen once in
`BuildWorldModal` and carried on `POST /storylines/{id}/populate/stream` — through every
render in the run, so a generated world's cast and places share a look.

## Orphaned-Media Cleanup Flow (maintenance)

```
Options → About tab → Maintenance section → lib/api.ts
  → GET  /api/options/media/orphans?min_age_hours=24   (dry-run scan)
        → routes/options → services/media_cleanup.scan_orphans
            referenced = {basenames of Character.portrait} ∪ {Setting.image} ∪ {Scenario.image}
                         ∪ {url of every persisted scene_image event}
            for *.webp in MEDIA_DIR/portraits + MEDIA_DIR/scenes + MEDIA_DIR/moments:
              orphan   = basename ∉ referenced
              eligible = orphan AND mtime older than min_age_hours (grace period)
        → {portraits, scenes, moments, orphanCount, eligibleCount, totalBytes, eligibleBytes, minAgeHours}
  → author reviews counts, confirms, then
  → POST /api/options/media/cleanup?min_age_hours=24   (delete eligible only)
        → services/media_cleanup.delete_orphans (re-scans; unlinks eligible orphans)
        → {deletedCount, freedBytes, skippedRecentCount}
```

A WebP is written to disk the moment ComfyUI renders it — before the entity is
saved — so a cancelled draft or a deleted Character/Setting leaves an unreferenced
file behind. Cleanup cross-references disk against the three media columns **and** the
`scene_image` event log. The
**grace period** (`min_age_hours`, default 24) is the safety valve: a just-generated
file from an in-flight draft counts as an orphan but is *not eligible*, so an
author mid-creation never loses their pending image. Deletion is doubly guarded
(unreferenced AND grace-expired), `.webp`-only, and scoped to the three media subdirs.
In-play scene images are referenced by an **event row**, not a column — without that
lookup the sweep would delete every picture a player captured one day later.

## Agentic Storyline Editing Flow (conversational, scope-aware editor)

Replaces the old one-shot **"Build the whole world"** orchestration. The author sets a
**write scope** — which of the storyline's own six fields (`title`/`genre`/`tagline`/
`premise`/`worldPrimer`/`statistics`) the agent may write — converses with it, reviews a
proposed **plan**, and only then approves. The **scope object is the single source of
truth shared by client and server**: the same `ScopeState` is rendered as the panel's
checkbox/pill list *and* sent with every request so the server builds a matching response
schema, prompt, and guard from it.

```
StorylineAgentPanel (segmented [Assistant|Context] right pane of StorylineCreatorView)
  → useStorylineAgent.send(instruction)
      appends {role:"user", content} to the CLIENT-SESSION messages[] (React state —
        no persisted conversation table; "New chat" clears it + any pending plan)
  → POST /api/storylines/agent/create/stream            (create mode)
    POST /api/storylines/{id}/agent/edit/stream          (edit mode)
      body: { scope: ScopeState, messages: AgentMessage[], fields: <current values> }
  → routes/storylines → agents/storyline_edit/{creation,editor}.storyline_*_agent
      → core.converse:
          1. assemble READ-SCOPED context — the request's `fields` snapshot restricted
             to readable_keys(scope), plus (edit only) world_context + best-effort
             rag_block grounding over the storyline's own corpus
          2. build the DYNAMIC response schema (agents/storyline_edit/scope.
             response_schema_for(scope)) — an object schema whose properties are
             EXACTLY the writable fields — and a system prompt naming them, instructing
             the model to leave every other field untouched and only return a plan when
             a change is requested
          3. services/llm.chat_complete(reasoning=DEFAULT_AUTHORING_EFFORT, low temp,
             extra_body={"guided_json": schema} IFF llm_backend.detect_backend == vLLM)
             — guided_json is a best-effort layer (only vLLM supports constrained
             decoding); the schema-shaped prompt is the layer that always applies
          4. parse the reply (_common.extract_json) → {assistant_message, plan?}
          5. when a plan is present: diff_guard(plan, scope) recomputes the changed-field
             set and rejects (surfaces as an in-band error frame) anything outside
             writable_keys(scope) — the LOAD-BEARING enforcement layer, since the stack
             has no constrained decoding outside the vLLM guided_json seam
      → yields frames: message (chunked via events.stream.chunk_text) then, when a plan
        survives the guard, a terminal plan frame (edit mode also carries baseVersion —
        a content hash of the writable fields the plan was generated against)
  → StreamingResponse NDJSON ──▶ client
      → useStorylineAgent folds frames (foldAgentEvent): message deltas accumulate into
        the streaming bubble; a plan frame becomes pendingPlan
```

Nothing is written until the human clicks **Approve**:

```
Create mode: approve(pendingPlan)
  → useStorylineAgent.approve → applyToForm(pendingPlan)
      fills the on-screen form's field setters (setTitle/setGenre/…/setStats) — the
      author still commits via the existing "Create World" path, unchanged

Edit mode: approve(pendingPlan)
  → POST /api/storylines/{id}/agent/apply   body: { scope, plan, baseVersion }
  → routes/storylines → services/storyline_apply.apply_plan (ONE transaction):
      1. diff_guard(plan, scope) AGAIN — backstop at implement time, in case a
         hand-crafted request skipped the client and the schema/guided_json layers
      2. content_hash(current DB row's writable fields) vs. baseVersion — a MISMATCH
         (a concurrent manual edit landed between plan and approve) → 409
         stale_storyline, rejected rather than silently overwritten
      3. apply text/primer FieldChanges via the normal storyline write path; apply
         StatChanges via the existing CLAMPED stat-definition services
         (create_stat_definition / update_stat_definition / delete_stat_definition —
         same range re-clamp + character-value pruning as the by-hand Stats editor)
      4. any failure ROLLS BACK the whole plan (never a half-edited storyline)
  → { storyline: StorylineRead, applied: string[] } — the author sees the refreshed fields
```

This is a **one-time, per-approval** cost (like the old build), not a per-turn one, and
**persists nothing before Approve**. The agent owns only the storyline's own fields —
cast, settings, and scenarios keep their existing per-entity "Draft with Mytheca" flows
untouched. **No new DB column:** the stale-read check is a content hash recomputed from
the current row on read, not a `version`/`updated_at` column on `Storyline`.

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
Characters with no triage. **Extract is a legacy per-doc toggle** from the retired
"Build the whole world" flow — still settable (like Draft/RAG), still persisted, but no
longer consumed by any agent. **Triage** sweeps only what's still **Uncategorized**,
leaving the manual buckets alone. Triage runs **per file** (one LLM call each) so the
panel sorts documents in front of the author; the batched `POST /storylines/triage`
remains for back-compat. A per-doc failure falls back to `other`/RAG-on without
aborting the run.

The **context budget** (the inline grounding cap + the meter on the page) is **32000
characters** (`_common.DOCS_CAP` / `readDocs.DOCS_CHAR_CAP`; ~8000 tokens), raised from
the original 8K so larger lore/corpus batches can ground generation.

**Post-creation document manager (`/storylines/[id]/documents`).** Once a world exists,
its whole corpus is managed on a dedicated route (`features/documents/DocumentsView` +
`useDocuments` + `components/feature/DocumentsTable`), reached from the Library's
storyline switcher (`StorylineMenu`'s per-row **Documents** action). It lists **every**
context doc (`listContextDocuments(id)` with no scope — storyline-level *and*
entity-owned) with search/filter/group-by-category, and edits go straight through the
existing endpoints: toggle Draft/RAG/Extract or change category (`updateContextDocument`),
delete (`deleteContextDocument`), or drop new `.txt`/`.md` files (`bulkCreateContextDocuments`).
Each row shows its scope (storyline-level vs. entity-owned) and the entities it is
**provenance** for.

**Doc→entity provenance links.** A `ContextDocumentLink` many-to-many layer
(`context_document_links` table) records which documents were used as context **for**
which character/setting — distinct from a doc's own single `entity_type`/`entity_id`
ownership scope (a link leaves the doc a storyline-level corpus member; one doc may link
to several entities). Links are created **manually** — the Character/Setting editor's
**Source documents** section (`SourceDocumentsPanel`, self-fetching) lists the entity's
linked docs (`?linkedEntityType=&linkedEntityId=`) with unlink, plus a picker to link any
corpus doc (`addDocumentLink`/`removeDocumentLink`). (An earlier **build-lineage** auto-link
path — where the retired "Build the whole world" flow stamped each proposed entity's
`sourceDocNames` and the commit resolved them to links — was removed with the build.)
Deleting a doc cascades its links;
deleting a linked entity drops the dangling links but keeps the doc. Links carry **no**
RAG/retrieval effect (pure provenance).

This is the **persistence seam** for retrieval: the documents are durably stored
per storyline and survive reload. The **Hybrid RAG** (see `docs/rag.md`) now reads
`content` at runtime — `includeRag` docs are embedded on save and retrieved by the
authoring agents. `includeDraft` docs additionally ground the creation-time
generation inline (not retrieved, capped at 32K characters). `includeExtract` is a
**legacy** flag from the retired "Build the whole world" flow — still persisted for
back-compat, but has no runtime/retrieval effect (no agent mines context docs for
new characters/settings anymore).

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

**The graph reaches the LLM prompt, but not via `ctx.subgraph`.** Band-1 assembly builds
`TurnContext.subgraph` (the scenario read above) every turn, but its only consumer is
`turn_engine.py`'s trace step, which reads `ctx.subgraph.get("available")` as a boolean for
diagnostics — `character_turn_agent.py` never references `ctx.subgraph` at all. What actually
conditions a character's generation is `graph_reader.relationship_context(speaker_id, other_ids)`
(direct char↔char edges + 2-hop indirect links), called from `turn_engine._relationship_note()`
and folded into the character's prompt as a plain-language relationship note (see the Reactive
Turn Director section below).

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
(`reflection.refresh_dispositions`, width scaled to impact). All best-effort (Redis/LLM down →
the turn still runs). A within-turn **continuity guard** used to check each later line against the
established beats before it streamed; it was retired after EXP-2026-08-005 measured it at 11 % of
turn time (~10 s per later speaker) and identified it as the sole reason later beats could not
stream their prose.

**Reactive Turn Director (Produce band overhaul).** The player's line is first **interpreted**
(`agents/intent_agent`) into narrate / address / **puppet** / whole-group intent; a puppeted
character then *performs* the direction in its own voice (not a bystander answering the player).
A **ReAct planner** (`agents/planner_agent.plan_beats`) drives the turn — it decides up to `TURN_PLANNER_LOOKAHEAD` beats per call and the engine executes them, re-planning when the queue empties or a beat goes stale (a character exits, presence changes, the direction takes the schedule over) — after each
beat it re-decides the next (a character speaks/acts, the narrator sets context, or the turn ends).
The back-and-forth is bounded by the scenario's **`max_turns`** (a hard per-scene ceiling on
**every emitted beat — character replies AND narrator beats** — for one player message, default
**5** — the loop ends there even if the planner would continue; the narrated open and puppet
performances count too; `TURN_MAX_BEATS`/`2*cast+6` remains a secondary runaway backstop). The
planner leans on **narration to PROGRESS the scene** to the next beat (especially in action) —
narrating what the characters are *doing* and carrying an action through to its consequence — and a
character **speaks only after** the scene has moved and has a genuine point-of-view reaction, so
characters stop over-talking; a **cold scene open** with no directed character is narrator-led. Each
character always **`<thinking>`**s (a real in-voice deliberation — **one or two sentences** in their
own terminology, streamed `private_to_user` and kept out of `turn_beats`). That block is the turn's
**only** deliberation: the character call runs at effort **NONE**, so the model does not also fill a
hidden reasoning channel before it. Thinking the same beat through twice cost the player both waits
and showed only the second (EXP-2026-08-006 measured the beat at ~35 s to its thought). But a
spoken line is **optional** — in an action moment they act or simply think with no forced dialogue.
**Situational voice adaptation** is driven by a **per-beat register**, not by asking the speaker to
work the moment out for itself. `planner_agent.next_beat` returns `register` (`light` · `neutral` ·
`tense` · `grave`) and `stakes` (the concrete thing at risk) **alongside every action** — it already
runs once per beat, so this costs no extra LLM call — and the turn engine threads both into the
character prompt's recency TAIL, where a per-register directive states the situation as fact
(`grave` explicitly revokes the habitual act: no wit, no cocky deflection). The register also
**selects which voice samples** are injected (above) and **tunes `top_p`**: it narrows as the
moment gets graver (`grave` = `0.85`, `tense` = `0.88`, `neutral` = `0.92`, `light` = `0.95`,
register-less = `0.92`), so a grave beat stays on the obvious, sincere word while a light one
can reach for the unexpected one. The **frequency and presence penalties are 0.0 on every
register.** They used to rise with lightness (up to `0.45 / 0.35`) to push the model toward
tokens it had not used yet, but a penalty falls on *every* token and the tokens prose is made
of are its most repeated ones — the full stop, the comma, the double quote, `I`, `the`.
EXP-2026-08-007 measured the shipped `0.40 / 0.30` against `0.00 / 0.00` across three
interleaved arms with every other field identical: **1.32 ± 1.16 vs 11.42 ± 3.96 sentences per
100 words, 80 % vs 100 % of passages containing speech, no overlap between the arms on the
primary metric.** The penalised arm wrote 180-word sentences with no full stop. The column is
kept in `_REGISTER_SAMPLER` so a future measurement can put something back in it. The trade is
recorded rather than made quietly: the penalties were originally added against in-character
drift, and that experiment does not measure drift. The register is always
optional: a planner fallback, a puppet beat, or a directly-constructed `TurnContext` yields
`register=None`, and the TAIL then falls back to the generic "read the moment" cue. The
`<thinking>` step still appraises the moment first, and the output contract's manner-adaptation rule
still makes personality **constant** while manner **adapts**. The between-turn **`disposition`**
carries the resulting emotional/situational state (shaken, grieving, afraid, relieved) forward, so an
adapted manner persists rather than snapping back to the default next beat. It is 2–3 sentences —
how the moment left them, what they want, and what they can no longer keep up — and it rides in the
prompt's recency **TAIL** beside the register (not the HEAD, where the voice-sample block outweighed
it), stated as the condition the character is already in with explicit license to break their
habitual manner because of it. Reflection effort stays **LOW**: `dispatch_reflection` runs inline by
default and a crowd reflects universally, so a higher budget would land on the turn tail.

**How much the character says** is the per-scene **`beat_length`**, set from the scene config
menu and carried on `TurnContext`: `short` 1–2 paragraphs, `medium` 2–4 (the default, and the
closest match to the behaviour before the control existed), `long` 5–6 — each paragraph at
most 3–4 sentences, with quoted dialogue explicitly **not** counting toward that, so the
instruction never trades a spoken line against description. It rides in the recency **TAIL**
beside the register, never in the stable head, because it is per-scenario and a per-scenario
value in the head would change the byte-stable prefix the prompt cache matches on. Narration
is untouched: it has its own sentence spec, and the control is about what a *character* says.

The count is stated in **paragraphs and never in words**, which is a measured choice rather
than a stylistic one. EXP-2026-08-007 recorded a countable "usually 80–200 words" target
moving the average passage *up* — a model cannot count words while writing, so a numeric
target reads as a description of a register and it obliges. Paragraphs name an axis the model
is already controlling deliberately (`paragraph_breaks` 3.89 ± 1.29 in EXP-2026-08-009).
Behind the directive sits a per-tier prose allowance (`_PROSE_TOKENS_BY_LENGTH`: 700 / 1400 /
2048 tokens) and a matching runaway stop, both about four times what their tier could honestly
need — a **backstop**, not the mechanism, because a token cap shapes prose by cutting it off
mid-sentence. The allowance is added **on top of** the thinking budget, never shared with it;
`long` keeps the 2,048 that shipped before the control existed. The output contract no longer
names a paragraph count of its own — it owns the *form* (blank lines between paragraphs, never
one block), the tail owns the *amount* — because two counts disagreeing inside one prompt is
how a setting comes to look as though it does nothing.

The authored `Setting.atmosphere` is **not** a live mood signal — it is written once at world
creation and never rewritten during play, so the prompt presents it as the description of the place
and never as "the scene right now". The
character conditions on the scene's most-recent beats, **at a depth the app fits to the model's real
context window** (`services/context_budget`) rather than one the player picks. The old per-scene
"Number of beats" slider is gone: the right depth is whatever the model can actually hold, and the
app knows the model's window while the player does not. A scene can still opt out with
`context_policy: "fixed"`, which restores the old `context_beats` behaviour verbatim; `assembler`
fetches the resulting depth from the Redis buffer, which retains up to `turn_buffer_size` = 160.
`transcript_budget` also caps the transcript at `TURN_CONTEXT_MAX_FRACTION` (0.5) of the whole
window even when more is free — filling a context window with transcript is not using it well,
since the character prompt's tail is the act-now region.

That window is **block-anchored**, not sliding: `buffer.anchored_turns` quantises its *start* to a
multiple of `turn_transcript_anchor_block` (20), so it holds between the fitted depth and that depth
plus one block, and its first line only moves once every 20 beats. A window that dropped its oldest
beat every turn would change the transcript's first token every turn, and a prefix cache matches
from the first token — the whole conversation would be re-read each turn even though it only grew at
the end. **A dynamic depth is a direct threat to exactly that**, which is why `fit_window` quantises
the depth it computes down to the same block and applies hysteresis: the window can only move in
steps the anchoring already tolerates. `character_turn_agent._transcript` deliberately allows one
anchor block above the fitted depth for the same reason — re-trimming to exactly that depth would
undo the anchoring.

### History compaction (the scene's memory)

Dropping the oldest beats is honest — it is what every context-limited system does — but it is
also how a scene forgets that someone already confessed, already left, already promised. With
`TURN_CONTEXT_COMPACTION` on, `services/history_compaction.maybe_compact` folds the dropped
beats into a **rolling per-session summary** (`agents/recap_agent`, `ReasoningEffort.LOW`) held
on `play_sessions.summary_text` / `summary_through_seq` / `summary_updated_at`.

Three constraints shape it.

**Cost.** Summarisation is incremental — each call folds only the newly-dropped beats into the
previous summary rather than re-reading the scene — and is bounded to **whole anchor blocks**,
so a long session costs one cheap call roughly every twenty beats instead of a growing
re-summarisation every turn. The beats to fold are read from the **event log**, not the Redis
buffer: the beats that need folding are by definition the ones falling off the buffer's far
end, which it may no longer hold.

**Cache.** The summary renders at the **head of the append-only region**, immediately above
`Recent beats:`, in both the character and narrator prompts. That placement is load-bearing:
the summary only changes when compaction fires, which is also exactly when the anchored window
re-anchors — so the two invalidate the prompt-cache prefix *together*, on one turn, rather than
on two different ones. `test_prompt_cache_prefix.py` pins it.

**Truth.** A summary is a claim about what happened, so it is **invalidatable**.
`invalidate_after(db, session_id, seq)` clears any summary covering `seq` or later, and is
called from every path that rewrites history — rewind (`truncate_session`), beat edit
(`edit_beat`), and both re-roll paths (`beat_rerun`). It lives beside the Redis buffer rebuild
in each of those, because both answer "history changed under us" and splitting them across
different call sites is how one gets forgotten. A stale summary would be *worse* than none:
the cast would confidently remember the beats the player just removed. A **branch** starts with
no memory of its own — copying the parent's summary would be nearly right and then go stale the
moment the branch diverged, with no seq to notice by.

Nothing here can break a turn: the setting off, no Redis, no configured model, a raising agent
or an empty reply each leave the previous summary standing and report a reason on the
`compaction` trace step. It **ships off** pending the measurement in Phase 12 — nothing may
claim compaction is free until it has been compared against the writing it replaces.

**"Tell me what happened", on demand.** `POST …/sessions/{id}/recap` runs the *same* agent, over
the events up to a requested seq, reusing the stored summary as its starting point when the
range begins above the boundary. It is the same call on purpose: two summarisers would drift
apart in tone and in what each counts as a fact, and the recap a player reads would then
disagree with the memory the cast reads. It never fails a page — no model, an unreachable one,
or an empty scene all return an empty recap.

What the fit decided is **reported, not configured**: the `window` trace step
("The scene reached back N beat(s)") carries `windowBeats`, `windowSource`
(`detected`/`configured`/`fallback`/`fixed`), `droppedBeats` and `budgetTokens`. When the window is
smaller than the history the oldest beats are simply dropped — compaction is a separate, off-by-
default feature (`TURN_CONTEXT_COMPACTION`). At the **end of
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

**Guests, and the approval gate.** The cast the engine assembles is the authored roster **plus
anyone carrying a presence event on this session** — so a scene can gain someone it never cast.
The scenario row is never mutated: a guest belongs to the *play-through*, and the same scenario
started fresh has its original cast. `POST /play/{id}/presence` accordingly accepts any character
of the scenario's **storyline** (one from a different storyline is still a 404), and `CastRail`
gained an **"Elsewhere in the World"** section offering exactly those people.

**The AI never brings anyone in.** There is deliberately no planner action that introduces a
character. The engine's only move is to *ask*: when the player themselves named an absent
storyline character — a pinned directive whose actor is away (Phase 8's `blocked` state), or a
plain longest-first name match of the direction text — `direction_runtime.cast_requests` emits a
`cast_request` event before any beat, and it changes nothing. `CastRequestBeat` renders it as a
question with two answers and no default; both answers go through the ordinary manual presence
path. **Declining writes `departed` with `reason: "declined"`** rather than merely dismissing the
card, because a `character_status_change` on the session is precisely what stops the same ask
being raised again on the next turn that mentions the name. Building the ask as an *event* rather
than as a planner action is what makes the rule structural instead of merely intended: the scene
can raise a question, and only the player can answer it.

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


## Narrative style guide — where it comes from and where it goes

**Authoring.** `POST /storylines/style` (`agents/style_agent.draft_style_guide`) reads the
same seed + premise + dropped-doc overview `/primer` reads, and answers one of two ways: the
id of an existing preset that fits, or a freshly written six-block guide. A chosen preset is
resolved to its **text** in the route, so the client never learns which path ran and the
author edits their own copy — nothing stores a preset reference, and editing a preset later
cannot rewrite a world that already shipped with it. Every failure (unreachable model,
unparseable reply, hallucinated preset id, no premise yet) resolves to `{}`, because an
optional feature must not be able to fail world creation. A drafted block containing a
**length count** is dropped before it is stored.

**Runtime.** `services/style_guide.resolve_for(storyline, scenario)` runs once per turn in
`assembler.assemble_context` and rides on `TurnContext.style`. From there:

| block | reaches the model via |
| --- | --- |
| attention · voice · texture · never | the head of `ctx.stable_prefix` → every prose agent's system message, between the output contract and `WORLD:` |
| pacing (+ never) | `planner_agent._planner_system`, appended after the operator-overridable planner prompt |
| signature | `character_turn_agent._build_user_prompt`, fused into the act-now cue in the volatile tail |

The split is a cache decision. The four prose blocks are constant for a whole scene, so they
sit where the system message is byte-identical across every speaker and beat and are paid for
once; only the one-clause signature is re-read per beat, buying the recency position the
cached prefix cannot reach — a position `EXP-2026-08-019` could not show is worth its
per-beat cost.
