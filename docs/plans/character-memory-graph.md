# Character Memory — episodic recall across scenarios

## 1. Introduction

Today a character carries exactly one thing across a scenario boundary: a relationship
edge in Neo4j (`resents`, weight `0.7`). Everything that *explains* it is either written
and never read (`:Consequence` nodes, `:Event` nodes), or written to a Redis key with a
one-day TTL (`memory/interior.py`). The result is a cast that carries feelings forward
with no idea where they came from — and, worse, invents replacement reasons on the spot,
contradicting scenes the player actually played.

This plan adds an **episodic memory layer**: per-character records of specific moments,
each holding a verbatim quote, written by the reflection pass that already runs after
every turn, stored canonically in Postgres, mirrored into Neo4j for traversal, and
recalled by a **deterministic** scorer that runs **once per turn** rather than once per
beat. No model call is added to the path between the player pressing send and prose
appearing. Judgement lives in the write (off the hot path, in a call that already
happens); the read is arithmetic you can step through in a debugger.

The feature is validated by one thing that is not a matter of taste: **did a beat quote a
prior recorded line verbatim?** That is a substring check against `events.data`, and it
is zero today by construction.

---

## 2. Decisions Already Taken

Answered by the owner before this plan was written; they are settled, not open.

| Decision | Choice | Consequence |
| --- | --- | --- |
| Storage | **Postgres canonical + Neo4j mirror** | Memory is not best-effort. It works and is fully testable with no Docker; the graph adds traversal only. |
| Branch scope | **Lineage-scoped** | Recall walks `PlaySession.parent_session_id` / `fork_seq`. A branch never recalls the timeline it walked away from. |
| Source panel | **Memory only, player-facing** | Shows the memory, the quote, a jump-back link, and a contradiction flag. Engine internals stay in `TurnInspectorPanel`. |
| Write path | **Extend `reflection_agent`** | Zero new model calls. Phase 3 ends in an explicit checkpoint; the fallback to a dedicated agent is pre-scoped in §Gap G1. |
| Cross-world | **Out of scope** | Memory never leaves its storyline. A `Character` row belongs to one storyline and there is no identity above it. |

Scope note: "between storylines" in the originating conversation meant **between scenarios
within one storyline**. Nothing here crosses a `storyline_id`.

---

## 3. Gaps & Unanswered Questions

### G1 — Reflection quality under a doubled workload *(assumption stated; checkpoint planned)*

`reflection_agent` currently returns `disposition` + `retrospective` + `branches`. Adding a
`memory` object grows both the instruction and the output. A model asked for two different
things in one JSON object may do both worse. **Assumption:** it holds, because the two
tasks share the same input and the same POV. Phase 3 ends with a mandatory checkpoint
against real output (`utils/scripts/memory_smoke.py`); if memories come back vague or
repetitive, Phase 3b splits `agents/memory_agent.py` out as a second concurrent call in
the same interlude. That split is pre-scoped so discovering it is cheap.

### G2 — Which play-through of a prior scenario counts as history? **Human intervention is needed to answer this question.**

Lineage solves branching *within* a scenario. It does not answer what happens when the
player plays Scenario 1 twice, in two separate sessions, with different outcomes, and then
plays Scenario 4. Both sets of memories exist under the same `storyline_id` and describe
incompatible pasts.

**Interim assumption used by this plan:** for each prior scenario, only the **most recently
updated session** contributes memories; within the *current* scenario, branch lineage
applies. This is deterministic and one query, and it matches the intuition that the last
time you played a scene is what happened. It is nevertheless a product decision — an
explicit "this play-through is canon" marker on `PlaySession` is the obvious alternative
and would be a small addition. Recorded in `docs/checklist.md` at Phase 2.

### G3 — Memory recall under the free-text engine *(assumption stated)*

`services/freetext_turn` shares `turn_finalize`, so memories are **written** in both
engines with no extra work. Recall is the problem: free-text writes the whole room in one
generation, so handing it several characters' private and contradictory memories invites
the model to reconcile them into one account — the same structural failure that makes
contradiction a `voiced`-mode property (§Phase 5). **Assumption:** under `freetext`, only
`quotable` memories for characters actually present are passed, capped at two total for the
whole passage, and `private` memories are withheld entirely. Revisit if free-text becomes
the default.

### G4 — Contradiction when a character is caught out *(assumption stated)*

Nothing in this plan tells Dell what to do when Mara denies his version. **Assumption:** it
is left to the model, but the prompt carries a derived **certainty** clause — a memory with
high salience and several reinforcements reads "you are certain of this"; a low-salience,
never-reinforced, second-hand one reads "you may be misremembering." That is one derived
string, not machinery. Whether characters need an explicit concede/dig-in policy is left
open in `docs/checklist.md`.

### G5 — Retention *(assumption stated)*

No hard per-character cap in v1. Growth is bounded by the salience floor at write time and
by reinforce-instead-of-duplicate. **Assumption:** a storyline played hard produces low
hundreds of memories per character, which the Phase 4 recall query handles by loading a
salience-ordered slice. If real play disproves it, a retention pass (fold the faded floor
into a single "long ago you…" summary) is the fix; recorded in `docs/checklist.md`.

### G6 — No backfill *(assumption stated)*

Existing play-throughs gain no memories retroactively. Memory begins the first time a turn
runs on the new code. Backfilling would mean an LLM pass over historical `events` rows, and
the quotes it produced would be unverifiable against what the cast was actually thinking at
the time.

### G7 — Authoring surface *(assumption stated)*

Memories are engine state, not authored content. There is no editor, no dossier tab, and
no options toggle in this plan beyond the kill switch in Phase 4. Surfacing "what Mara
remembers about you" in `CharacterDossier` is a natural follow-on and is recorded in
`docs/checklist.md`, not built here.

---

## 4. Hierarchical Step-by-Step Instructions

### Phase 1 — Relationship provenance, and per-turn edge provenance

Independently correct and shippable alone. Nothing below depends on it, but every beat gets
better the moment it lands.

- **Locations:** `web/backend/app/services/turn_writer.py`
  (`_write_consequence`, `_append_event`), `web/backend/app/services/graph_writer.py`
  (`upsert_edge`), `web/backend/app/services/session_state.py` (the rewind prune),
  `utils/tests/backend/services/test_turn_writer.py`.
- **Rationale:** `_write_consequence` writes edge metadata `{"via", "weight"}` and drops
  `cons.reason` on the floor, so every relationship formed *during play* reaches the next
  scene with no explanation and the model invents one. The reason is already computed. This
  is a bug fix, not a feature.

1. Carry `reason` (falling back to `summary`) into the edge metadata written by
   `_write_consequence`, matching the shape `relationships.ensure_seeded` already writes at
   seed time so `graph_reader.relationship_context` renders both identically.
2. Stamp `session_id` and `turn_seq` on every edge written by `graph_writer.upsert_edge`,
   and add a `remove_edges_after(session_id, seq)` helper.
3. Call that helper from `session_state.truncate_session`, beside the existing
   `graph_writer.remove_node(f"evt_{session_id}_{turn_seq}")` prune. This closes the leak
   documented in `docs/checklist.md` — *"Graph edges from a rewound turn are not rolled
   back"* — which is currently the last known way a rewound scene knows something the
   transcript does not. Delete that bullet in the same change.
4. Write `involved` edges from the turn's `:Event` node to each present character in
   `_append_event`. The edge type is already in `content/graph_registry.py` and has never
   been written; without it an event is reachable only from its *setting*, so "what has
   happened between these two people" has no path to walk.
5. Update `docs/story-graph-neo4j.md` (edge metadata now carries reason + turn provenance;
   `involved` is now written) and `docs/checklist.md`.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services`.
> Once green, commit locally: `Character Memory (1/8) Complete: Relationship edges written
> during play now carry their reason and turn provenance, events link to the people in
> them, and a rewind rolls its edges back.` Do not push or open a PR unless the user asks.*

---

### Phase 2 — The memory record

Storage only. Nothing writes it and nothing reads it yet — deliberately, so the schema and
its lineage rules can be tested in isolation.

- **Locations:** `web/backend/app/models/character_memory.py` (new),
  `web/backend/app/models/__init__.py`, `web/backend/alembic/versions/<date>_character_memories.py`,
  `web/backend/app/schemas/memory.py` (new), `web/backend/app/services/memory_store.py` (new),
  `web/backend/app/services/session_state.py`, `web/backend/app/core/ids.py`,
  `utils/tests/backend/data/test_character_memory_model.py`,
  `utils/tests/backend/services/test_memory_store.py`.
- **Rationale:** Postgres is canonical (§2), so the table must exist and its deletion
  semantics must be correct before anything writes to it. Getting rewind and lineage wrong
  after there is data is a migration; getting it wrong now is a test.

1. `CharacterMemory` model. Columns: `id` (`cm_` prefix), `storyline_id`, `character_id`,
   `session_id`, `scenario_id`, `turn_seq`, `event_id` (nullable — the beat to jump back
   to), `gloss`, `quote`, `quote_speaker_id`, `valence`, `salience` (float),
   `participants` (JSON list), `subjects` (JSON list), `reinforcements` (int),
   `last_recalled_seq`, `last_recalled_session_id`, `created_at`. Index
   `(storyline_id, character_id)` and `(session_id, turn_seq)`.
2. Alembic migration, following the existing `versions/` naming. Register the model in
   `models/__init__.py` so `create_all` and the additive reconciler both see it. Note the
   dev-database caveat: the reconciler runs at backend startup, so a running server needs a
   restart before the column exists.
3. `services/memory_store.py` — the one owner of memory persistence. Functions:
   `write(...)` (with the reinforce-or-insert rule), `reinforce(memory_id, seq)`,
   `visible_for(db, storyline_id, session, character_ids)` (the lineage query),
   `mark_recalled(ids, session_id, seq)`, `delete_after(db, session_id, after_seq)`.
4. **Lineage**, the load-bearing part. `visible_for` resolves, in this order:
   - memories from the **current session** with `turn_seq <= now`;
   - memories from each **ancestor session**, walking `parent_session_id`, capped at that
     child's `fork_seq`;
   - memories from **other scenarios** in the same storyline, restricted to the most
     recently updated session per scenario (§Gap G2 — flag this in the docstring as an
     interim rule, not a settled one).
   It returns rows ordered by `salience` desc with a bounded limit, so the caller always
   loads a slice rather than a history.
5. Hook `delete_after` into `session_state.truncate_session` beside the existing bulk
   deletes, so a rewind forgets memories transactionally rather than best-effort.
6. Update `docs/structure.md` (new model + service), `docs/architecture.md` (memory is
   canonical in Postgres, mirrored to the graph), `docs/documentation.md` (14 tables → 15),
   and add G2 + G5 to `docs/checklist.md`.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/data
> utils/tests/backend/services`. Once green, commit locally: `Character Memory (2/8)
> Complete: Added the character_memories table, its store, lineage-scoped visibility, and
> transactional deletion on rewind.`*

---

### Phase 3 — Writing memories, and the checkpoint

- **Locations:** `web/backend/app/agents/reflection_agent.py` (`_SYSTEM`, the parse),
  `web/backend/app/memory/interior.py` (`InteriorRecord`),
  `web/backend/app/services/reflection.py` (`reflect_and_store`),
  `web/backend/app/services/memory_store.py`, `web/backend/app/services/graph_writer.py`,
  `utils/scripts/memory_smoke.py` (new),
  `utils/tests/backend/agents/test_reflection_memory.py`,
  `utils/tests/backend/services/test_memory_write.py`.
- **Rationale:** reflection already runs per character, per turn, concurrently, after the
  stream has closed, with the full transcript. It already produces a private retrospective
  and throws it away 24 hours later. This is the cheapest possible write path and it adds
  no player-visible latency.

1. Extend the reflection JSON with an optional `memory` object: `gloss`, `quote`,
   `quote_speaker`, `salience`, `valence`, `subjects`. Instruct that `quote` must be
   **copied verbatim from the transcript**, never composed, and omitted when nothing was
   worth keeping. Add the fields to `InteriorRecord` so the existing Redis path is
   unchanged and the memory rides alongside.
2. **Verify the quote before persisting.** `memory_store.write` accepts a memory only if
   `quote` is a substring of a real `events.data` text for that session. A quote that fails
   the check is dropped and the memory stored without one. This is the guard that stops a
   character quoting a line nobody said, and it is a pure function over rows.
3. **Subjects — deterministic union first.** Every memory's `subjects` is the union of: the
   ids of characters present, the setting id, any existing graph node label appearing in the
   beat text (lexical, exact), and the model's proposed tags normalised to lowercase kebab.
   Only the last of those involves judgement.
4. **The write filter.** Reject below a salience floor (constant, one place, tunable). Then
   reinforce-or-insert: if a candidate's `subjects` overlap and its `gloss` closely matches
   an existing memory for the same character within the same scenario, call `reinforce`
   instead of inserting. Dell gets one hot memory of the tunnel, not forty lukewarm ones.
5. **Session safety.** `reflect_and_store` is deliberately free of any request-bound
   `Session` so it can run on a background thread. It must therefore open its **own**
   session via `core.db.SessionLocal` for the memory write, and close it in a `finally`.
   Do not thread the request session into the background job.
6. **Neo4j mirror**, best-effort and after the Postgres commit: `(:Character)-[:remembers
   {id, gloss, salience, seq}]->(:Event)` on the turn's existing event node. A graph outage
   loses the mirror, never the memory.
7. `utils/scripts/memory_smoke.py`, modelled on `utils/scripts/scene_smoke.py`: build a
   throwaway world, play several turns against the real model, and print every memory
   written with its character, salience, subjects and quote — plus whether the quote passed
   verification. **This is a harness, not an experiment** (n=1, no arms), the same
   distinction `scene_smoke.py` carries.
8. **Checkpoint (mandatory before Phase 4).** Run the smoke harness over two scenes and
   read the output. Continue if memories are specific, differ between characters, and carry
   verified quotes. If they are vague, near-duplicate across the cast, or quote-less, stop
   and do Phase 3b: split `agents/memory_agent.py` out as a second concurrent call inside
   the same interlude, dispatched from `services/reflection.py`, with the write path from
   steps 2–6 unchanged. Record the decision and what was observed in `docs/checklist.md`
   either way — a checkpoint that passes silently is indistinguishable from one that was
   skipped.
9. Update `docs/data-flow.md` (the post-turn interlude now writes durable memory),
   `docs/workflow.md` (the new script) and `docs/story-graph-neo4j.md` (the mirror edge).

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/agents
> utils/tests/backend/services`. Then run `uv run python utils/scripts/memory_smoke.py` and
> record the checkpoint outcome. Once green, commit locally: `Character Memory (3/8)
> Complete: Reflection now writes verified, deduplicated episodic memories to Postgres and
> mirrors them into the graph.`*

---

### Phase 4 — Recall I: who is in the room

The tunnel case works at the end of this phase. The ogre case does not yet.

- **Locations:** `web/backend/app/services/memory_recall.py` (new),
  `web/backend/app/services/turn_setup.py` (`prepare_turn`),
  `web/backend/app/services/assembler.py` (`TurnContext`),
  `web/backend/app/services/beat_runner.py` (beside `relationship_note`),
  `web/backend/app/core/config.py` (kill switch),
  `utils/tests/backend/services/test_memory_recall.py`.
- **Rationale:** this is the phase where the latency decision is made, and it is made once.
  Recall runs **per turn, not per beat**, which is only possible because the turn is planned
  once up front and the plan is binding — so every speaker is known before the first beat.

1. `memory_recall.recall_for_turn(db, ctx, speaker_ids, cues)` — **one** `visible_for`
   query covering every planned speaker, then pure-Python scoring. No per-beat database
   access. On the planner's fallback path (endpoint unreachable, reply unparseable) the
   speaker list degrades to the present cast: one slightly larger query, still one query.
2. The scorer is a **pure function** with named weight constants in one module:
   `salience × fade(turns since reinforced) × (1 + reinforcement bonus)`, plus a bonus for a
   participant being present, minus a **cooldown** penalty for anything surfaced in the last
   K beats. Cooldown is not optional — without it the tunnel wins every beat and Dell
   becomes a man who can only say one thing.
3. `fade` finally gives the `half_life_turns: 40` declared on every feeling edge in
   `content/graph_registry.py` an actual computation; it has been inert data since it was
   written. Keep the constant in one place and reference the registry value.
4. Store the result on `TurnContext` as a per-speaker shortlist, populated in
   `prepare_turn` alongside the existing gate work.
5. Render in `beat_runner`, next to `relationship_note`, into the **volatile tail** — never
   `stable_prefix`, which is byte-identical per scene and cached. At most **two** lines, and
   at most **one** quotable quote per beat: hand a model two verbatim callbacks and it will
   use both. Include the §G4 certainty clause, derived from salience and reinforcements.
6. Call `mark_recalled` for whatever was actually rendered, so cooldown and reinforcement
   have something to read.
7. One env-gated kill switch (`MEMORY_RECALL_ENABLED`, default on) documented in
   `.env.example` and `docs/deployment.md`, so a bad recall can be turned off without a
   deploy. Recall being off must produce prompts byte-identical to today's.
8. Update `docs/data-flow.md` with the once-per-turn recall step.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services`,
> including a test that pins recall to one query per turn and a test that the kill switch
> reproduces today's prompt exactly. Once green, commit locally: `Character Memory (4/8)
> Complete: Deterministic once-per-turn recall by participants, with fade, reinforcement
> and cooldown, rendered into the volatile prompt tail.`*

---

### Phase 5 — Recall II: subjects, the lexicon, and what can be said aloud

The ogre case works at the end of this phase. So does the thing that stops it leaking.

- **Locations:** `web/backend/app/services/memory_cues.py` (new),
  `web/backend/app/services/memory_recall.py`, `web/backend/app/services/beat_runner.py`,
  `utils/tests/backend/services/test_memory_cues.py`.
- **Rationale:** participant matching cannot reach a memory whose participants are dead,
  absent, or never existed as characters. Dell watched an ogre kill Sera; Sera is in no
  further scene, so his defining memory is permanently unreachable by Phase 4 alone.

1. **The lexicon.** Every distinct `subjects` string in the storyline — a few hundred
   entries — cached in-process against a cheap version counter, invalidated on write. The
   insight that makes this deterministic: *you do not need to identify everything in the
   scene, only the things you already hold memories about.* This is the same model-free,
   lexical posture `services/retrieval_gate.py` already uses.
2. **The scan.** Match the lexicon against the setting text, the recent beats and the
   player's text. A dictionary intersection, microseconds, no model. When the narration says
   *"an ogre steps out of the treeline"*, `ogre` is in the lexicon because Dell's memory put
   it there, and the memory becomes a candidate with no living participant and three
   scenarios of distance.
3. Feed cue hits into the Phase 4 scorer as an additive term (capped, so a memory tagged
   with everything cannot dominate).
4. **Disclosure class, derived per listener** — a set comparison, no judgement:
   - everyone present was also in the source event → `quotable` (may be said, may be quoted
     verbatim);
   - some present, some not → `shared` (may be alluded to, not quoted);
   - nobody present was there → `private` (shapes behaviour, must not be stated as
     something the room knows).
   The same memory is `quotable` to Mara for the tunnel and `private` with respect to Mara
   for Sera's death: the class is a property of the memory *and the room*, not the memory.
5. Render each class with its own wording, and make `private` explicit —
   *"Mara does not know this. Do not tell it. Let it show."* Getting this wrong is worse
   than no recall at all: it silently teaches characters things they were never told.
6. **Memory follows presence.** A character receives a memory only for beats they were
   present at (`presence.py` already tracks this). Being *told* later is a different event
   with its own, weaker, second-hand memory. Pin this with a test — it is the rule that
   prevents the most immersion-breaking failure this system can produce, and it gives
   rumour and distortion for free.
7. Apply the §G3 free-text restriction: under `sceneMode: freetext`, pass only `quotable`
   memories, capped at two for the whole passage.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services`,
> including a test that a `private` memory never reaches a prompt as shared knowledge and a
> test that a character absent from a beat gets no memory of it. Once green, commit locally:
> `Character Memory (5/8) Complete: Subject cues reach memories with no one present, and
> disclosure classes govern what a character may say aloud.`*

---

### Phase 6 — Recall III: meaning, and promoting tags to nodes

- **Locations:** `web/backend/app/rag/entries.py`, `web/backend/app/rag/indexer.py`,
  `web/backend/app/services/memory_recall.py`, `web/backend/app/services/memory_cues.py`,
  `utils/tests/backend/rag/test_memory_entries.py`.
- **Rationale:** the lexicon is exact and therefore brittle — it misses *"the big one from
  the ridge"* and *"we're not going up there again."* The hybrid retriever already exists
  and has never been pointed at anything that happened during play; it only ever sees
  material authored before the story started.

1. A `LoreEntry` adapter for a memory, and an `indexer.sync_memory` beside the existing
   `sync_character` / `sync_setting`. Storyline-scoped like everything else in the corpus.
2. **Gate it, and run it once per turn.** This is the only channel with real cost (an
   embedding plus a vector search). Reuse the `retrieval_gate` posture: it fires only when
   there is reason to think the lexical scan missed. On most turns it does not run.
3. Fuse the semantic ranking with the Phase 4/5 graph ranking by **RRF**, not by adding
   scores — the two are on incomparable scales, which is exactly why `rag/retriever.py`
   already fuses by rank.
4. **Tag → node promotion**, arithmetic and not judgement: a subject appearing in three or
   more memories, or across two or more scenarios, is promoted to a graph node with
   `about` edges from the memories that carry it. `ogres` becomes a node in your world
   precisely because ogres kept mattering. Without the threshold, every noun anyone mentions
   becomes a permanent node and traversal gets slower for nothing.
5. Promotion runs on the cold path, never in `prepare_turn`.
6. Update `docs/rag.md` (played memories are now part of the corpus) and
   `docs/story-graph-neo4j.md` (promoted subject nodes).

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/rag
> utils/tests/backend/services`, including a test that the semantic channel is skipped when
> the gate does not fire. Once green, commit locally: `Character Memory (6/8) Complete:
> Memories join the hybrid corpus behind a gate, fused by RRF, and recurring subjects are
> promoted to graph nodes.`*

---

### Phase 7 — "Where did this come from?"

- **Locations:** `web/backend/app/services/beat_stream.py` (stamp recalled ids on
  `events.data`), `web/backend/app/routes/play.py` (one read endpoint),
  `web/backend/app/schemas/memory.py`, `web/frontend/lib/types.ts`,
  `web/frontend/lib/api.ts`, `web/frontend/components/feature/MemorySource.tsx` (new) +
  co-located `MemorySource.test.tsx`,
  `web/frontend/components/feature/TranscriptBeat.tsx`,
  `web/frontend/components/feature/BeatControls.tsx`,
  `utils/tests/backend/api/test_memory_provenance.py`.
- **Rationale:** subjective memory without a provenance surface generates a steady stream of
  "the AI contradicted itself" reports, and every one of them will be the system working
  correctly. This is also the debugging surface for Phases 4–6, so earlier is better.

1. Stamp the recalled memory ids onto the beat's `events.data` when it is persisted.
   `Event.data` is already a JSON column, so this needs no migration and no new table.
2. `GET /api/play/sessions/{session_id}/beats/{event_id}/memory` → the memories behind that
   beat: gloss, verbatim quote and its speaker, the originating scenario and turn, the
   `event_id` to jump back to, and a **contradiction flag** set when another character holds
   a memory of the same source event with a materially different gloss. Returns an empty
   list rather than 404 for a beat with no memory.
3. `MemorySource` — a read-only control and panel. Because it *reads* rather than *changes*
   the record, it sits opposite the `BeatControls` cluster (Edit / Re-roll / Branch /
   Rewind), keeping a mis-click away from the destructive group. `BeatControls` is a
   `role="toolbar"` with a roving tabindex; do not add this control inside it — a separate
   single tab stop preserves the "one tab stop per beat" property that cluster was built for.
4. Panel contents, player-facing and in-fiction: the recalled moment, the quote, *"jump to
   it"*, and *"Mara remembers this differently"* when the flag is set. No weights, no
   scores, no engine internals — that is what `TurnInspectorPanel` is for.
5. Below `lg` it opens as a `Drawer` bottom sheet mounting the same content component with
   the same props, matching how `CastRail` / `DirectorRail` / `CharacterDossier` already
   work. No reduced mobile copy.
6. Update `docs/api-contract.md`, `docs/routes.md` (no new route, but the endpoint is
   documented), `docs/component-map.md` and `docs/data-flow.md`.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api`,
> `npm test` in `web/frontend`, `npm run typecheck && npm run lint`, plus an accessibility +
> responsive pass (keyboard operability, visible focus, AA contrast, live-region behaviour,
> and layout at 320 / 375 / 768 / 1024). Once green, commit locally: `Character Memory (7/8)
> Complete: A per-beat source control shows the memory behind a line, its verbatim quote,
> and whether anyone remembers it differently.`*

---

### Phase 8 — Measurement

- **Locations:** `docs/research/experiments/EXP-<id>-character-memory/`
  (`manifest.yaml`, `RESULTS.md`), scaffolded with `make new-experiment`.
- **Rationale:** "does the story feel more continuous?" cannot be answered honestly. This
  repository already has the cautionary case on file: `EXP-2026-08-018` reported a prose
  effect and `EXP-2026-08-019` moved the same unchanged baseline by more than the effect.
  Do not repeat it.

1. **Primary metric — verbatim callback rate:** the proportion of beats containing a string
   that exactly matches a prior recorded beat in the play-through's lineage. Deterministic,
   no judge model, and **zero today by construction**, which makes it a real baseline rather
   than a comparison against noise.
2. **Secondary — quote verification failure rate:** how often the model proposed a quote
   that was not in the transcript. This measures how much the Phase 3 guard is actually
   catching, and it is the number that tells you whether confabulated quotes were ever a
   real risk.
3. **Secondary — recall precision by channel:** how often a surfaced memory came from
   participants, cues, or meaning. If the semantic channel never wins, Phase 6 can be
   turned off and the gate cost reclaimed.
4. Arms: recall off (the kill switch) versus recall on, same seeds, same scenes. Report
   per-run rows. **Never aggregate over survivors of a partially-failed run** —
   `EXP-2026-08-001` is the worked example of getting that wrong.
5. Record every number in `manifest.yaml` and `RESULTS.md`, and add the claim to
   `docs/research/CLAIMS.md`. Never report a metric in chat or a commit message without
   writing it here first.

> *Action: Run the validation for this phase — `make validate-research`, then
> `uv run pytest` and `npm test` for a full-suite green. Once green, commit locally:
> `Character Memory (8/8) Complete: Recorded the verbatim-callback baseline and the
> recall-on/recall-off comparison.`*

---

## 5. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Edge provenance | Play-written edges carry reason + session/turn; rewind rolls them back | `web/backend/app/services/turn_writer.py`, `services/graph_writer.py`, `services/session_state.py` |
| `involved` edges | Events link to the characters in them | `web/backend/app/services/turn_writer.py` |
| `CharacterMemory` model | The canonical memory row | `web/backend/app/models/character_memory.py` |
| Migration | `character_memories` table | `web/backend/alembic/versions/<date>_character_memories.py` |
| Memory schemas | Pydantic mirrors + API shapes | `web/backend/app/schemas/memory.py` |
| Memory store | Write, reinforce, lineage-scoped read, delete-after | `web/backend/app/services/memory_store.py` |
| Reflection extension | `memory` object + verbatim-quote verification | `web/backend/app/agents/reflection_agent.py`, `app/memory/interior.py`, `services/reflection.py` |
| Graph mirror | `(:Character)-[:remembers]->(:Event)` | `web/backend/app/services/graph_writer.py` |
| Recall | One query per turn, pure-function scoring, cooldown | `web/backend/app/services/memory_recall.py`, `services/turn_setup.py`, `services/beat_runner.py` |
| Cues + disclosure | Lexicon scan, quotable / shared / private | `web/backend/app/services/memory_cues.py` |
| Semantic channel | Memories in the hybrid corpus, gated, RRF-fused | `web/backend/app/rag/entries.py`, `rag/indexer.py` |
| Provenance endpoint | The memories behind one beat | `web/backend/app/routes/play.py` |
| Source control + panel | Player-facing "where did this come from?" | `web/frontend/components/feature/MemorySource.tsx` |
| Beat wiring | Control placement opposite the mutate cluster | `web/frontend/components/feature/TranscriptBeat.tsx`, `BeatControls.tsx` |
| TS mirror | Hand-maintained contract | `web/frontend/lib/types.ts`, `lib/api.ts` |
| Smoke harness | Prints memories written, with quote verification | `utils/scripts/memory_smoke.py` |
| Backend tests | Model, store, lineage, write, recall, cues, API | `utils/tests/backend/{data,services,agents,rag,api}/` |
| Frontend test | Source panel, co-located | `web/frontend/components/feature/MemorySource.test.tsx` |
| Experiment | Verbatim-callback baseline + recall on/off | `docs/research/experiments/EXP-<id>-character-memory/` |
| Docs | Behaviour updated in the same change as the code | `docs/{data-flow,api-contract,architecture,structure,documentation,story-graph-neo4j,rag,workflow,deployment,component-map,checklist}.md`, `CLAUDE.md` |

## 6. Sequencing Notes

Phase 1 is independent and can ship alone. Phases 2 → 3 → 4 are the spine; **stop at the
Phase 3 checkpoint** rather than building recall on memories that turn out to be mush.
Phase 5 is where the feature stops being "relationship notes with extra steps." Phase 6 is
the long tail and is the first candidate to cut if the cue channel proves sufficient.
Phase 7 can move earlier — it is the best debugging surface for Phases 4–6, and the only
reason it sits late is that it needs recalled ids to exist. Phase 8 is not optional: no
number about this feature may be reported anywhere until it is written there.
