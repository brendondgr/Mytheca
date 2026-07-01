# Velora — Reactive Turn Director (ReAct planning + graph-aware characters)

> Overhauls the runtime turn loop's **Produce** band. The P1–P11 loop stands up transport,
> per-character generation, stats, cold-path, and reflection — but the *director* is a
> one-shot pick capped at 3 speakers, the player's line is an opaque blob (no attribution),
> the narrator never fires, and the story graph is read but never used or populated with
> relationships. This plan replaces the fixed director with a **ReAct planner** and wires the
> **knowledge graph** into character responses. Companion to `docs/plans/turn-loop-runtime.md`.

## 1. Problem (grounded in the code)

- **Speaker cap = 3, static.** `director_agent._MAX_SPEAKERS = 3`; "everyone introduces
  themselves" is impossible. Order is a single up-front pick (+ a bolt-on rerank/cascade).
- **No input attribution.** The player line is `{role: "player"}` verbatim; the engine never
  detects "Beth tells Mei 'I hate you'" — so *Mei responds to the player*, or a random
  character does, instead of **Beth performing it and Mei reacting**.
- **Narrator is dead code** in normal play (`mode` defaults `pov`; the frontend never sends
  `narrator`). No context/transitions between speakers.
- **Graph unused + empty of relationships.** `ctx.subgraph` is fetched but never enters a
  prompt; no character↔character edges are ever written (edge types exist in
  `content/graph_registry.py`, but nothing calls `upsert_edge` for them), and there is no
  targeted A↔B / N-hop reader.

## 2. Decisions (locked with the user)

- **D1 — Puppeting → in-voice.** When the player directs a character ("Beth says X to Mei"),
  the engine detects Beth as the **actor**, has Beth's agent **perform it in her own voice**
  (the player's words are a *direction*, not the final line), then the addressed/affected
  characters react. Never: a character answering the player's narration as if the player spoke.
- **D2 — No speaker limit.** The loop runs until the player's direction is **satisfied**
  ("everyone introduces themselves" → every cast member acts, 2 or 20). A high `TURN_MAX_BEATS`
  safety backstop guards against a runaway loop only; it is not a feature cap (logged if hit).
- **D3 — ReAct planning.** After **each** beat the planner re-decides the next beat (which
  character acts, whether the narrator sets context, or the turn ends) from the transcript so
  far — a reason→act→observe loop, not a static order. Subsumes the P5/P10 `who_is_up` +
  `rerank` + `cascade`.
- **D4 — Relationships: seed from bios + evolve in play.** Initial edges are extracted from
  the authored character bios/secrets (best-effort, off the hot path) into the graph; play
  then accrues/updates edges via a relational consequence. Character responses read the
  speaker's relationship to whom they address + a 2-hop neighborhood.
- **Best-effort throughout** (mirrors the existing loop): every new LLM/graph step degrades to
  the prior behavior on failure, never blocks the turn. Tests offline-mock the LLM + graph.
- **Out of scope:** RAG triggering (the user owns that); a manual relationship-authoring UI.

## 3. Phases (commit-per-phase; `[Reactive Turn Director] (n/6) Complete: …`)

### P1 — Input intent + puppet performance (attribution fix)
- **Locations:** `web/backend/app/agents/intent_agent.py` (new — `interpret(db, ctx, text) →
  TurnIntent{kind, directed_actors[], addressed[], scope, directive}`; LLM, roster-constrained,
  best-effort → `freeform`); `web/backend/app/agents/character_turn_agent.py` (add a
  `directive` param → a "you are doing/saying this, perform it in your voice" block);
  `web/backend/app/services/turn_engine.py` (compute intent; a puppet beat has the directed
  character perform first, in-voice; the addressed character becomes the reactor); `stream.py`
  trace `intent` step.
- **Tests:** `agents/test_intent_agent.py` (puppet/direct/broadcast/narration/freeform parse,
  roster-constrained, best-effort fallback); `api/test_play_turn.py` (puppet → the directed
  character performs in-voice then the target reacts; the player's words are not answered as-is).
- **Commit:** `(1/6) Complete: input intent interpreter + in-voice puppet performance (attribution fix).`

### P2 — ReAct turn planner (dynamic, uncapped, narrator beats)
- **Locations:** `web/backend/app/agents/planner_agent.py` (new — `next_beat(db, ctx, intent,
  turn_beats, acted) → BeatDecision{action: speak|act|narrate|end, actorId, addressingId,
  reason}`; roster-constrained; best-effort); `web/backend/app/services/turn_engine.py`
  (replace `who_is_up` + the fixed while-loop + `rerank`/`cascade` with the ReAct loop:
  interpret → repeat{plan next beat → run it → observe} until `end`/`TURN_MAX_BEATS`; narrator
  becomes a planner-chosen beat that works in POV); retire `director_agent.who_is_up`/`rerank`
  (keep `propose_branches`); `core/config.py` `turn_max_beats`; `stream.py` trace `plan` step.
- **Tests:** `agents/test_planner_agent.py` (next-beat parse, roster-constrained, end signal);
  `api/test_play_turn.py` (rewrite P5/P10 cases: "everyone" → all cast act in sequence; puppet
  → performer then reactor; normal → provoked responder then end; narrator interstitial appears
  in POV; safety cap). Update/retire the old `who_is_up`/`rerank`/`cascade` tests.
- **Commit:** `(2/6) Complete: ReAct turn planner — dynamic, unlimited speakers, narrator beats.`

### P3 — Relationship seeding from bios (populate the graph)
- **Locations:** `web/backend/app/agents/relationship_agent.py` (new — `extract(db, cast) →
  [RelationshipEdge{sourceId, type, targetId, reason}]` over the registry's character→character
  edge types, from bios/secret/background); `web/backend/app/services/relationships.py` (new —
  `ensure_seeded(db, scenario)`: if the cast has no relationship edges in Neo4j, extract + write
  via `graph_writer.upsert_edge`; best-effort, idempotent); `turn_engine.py` (run `ensure_seeded`
  **off the hot path** on the first turn of a session, alongside reflection); `stream.py` trace
  `relationships` step.
- **Tests:** `agents/test_relationship_agent.py` (extraction parse, type-constrained, dedupe);
  `services/test_relationships.py` (edges written via a recording fake Neo4j session; no-op when
  edges already exist / graph disabled).
- **Commit:** `(3/6) Complete: seed character relationships from bios into the story graph.`

### P4 — Relationship query + graph-aware character responses
- **Locations:** `web/backend/app/services/graph_reader.py` (new `relationship_context(db,
  character_id, other_ids, hops=2)` → the speaker's direct edges to the others + a 2-hop
  neighborhood, best-effort → empty); `web/backend/app/agents/character_turn_agent.py` (fold the
  speaker's relationship to the beat's `addressing` target + 2-hop into the prompt HEAD/MIDDLE);
  `turn_engine.py` (resolve the relationship context per beat and pass it through); `stream.py`
  trace `relationship` step.
- **Tests:** `services/test_graph_reader.py` (relationship-context query shape via a recording
  fake session; empty when disabled); `agents/test_character_turn_agent.py` (relationship
  context reaches the prompt).
- **Commit:** `(4/6) Complete: 2-hop relationship read woven into character responses.`

### P5 — Relationship evolution in play (close the cold-path edge gap)
- **Locations:** `web/backend/app/services/emission.py` + `character_turn_agent.py` contract (a
  `<type:relationship_update>` block: `{target, type, direction}`); `web/backend/app/services/
  validator.py` (`validate_relationship` → confirm target in roster + type in the registry);
  `turn_engine.py` (a validated relationship becomes a `Consequence` with `target_id` +
  `edge_type` → `turn_writer` writes/updates the edge); `stream.py` trace `relationship_change`.
- **Tests:** `services/test_validator.py` (relationship validate/drop); `services/test_turn_writer.py`
  (relational consequence → edge written); `api/test_play_turn.py` (a relationship_update beat →
  a graph edge consequence).
- **Commit:** `(5/6) Complete: relationship changes during play write graph edges (evolve).`

### P6 — Frontend polish (Inspector + real relationships)
- **Locations:** `web/frontend/components/feature/TurnInspectorPanel.tsx` (STEP_META for
  `intent` / `plan` / `relationship` / `relationships` / `relationship_change`);
  `web/backend/app/routes` + `graph_reader` (a `GET` for a scenario's relationship edges) +
  `web/frontend/features/story-player` (DirectorRail shows **real** graph relationships,
  replacing seed data — best-effort, falls back to seed when the graph is empty).
- **Tests:** FE `TurnInspectorPanel.test.tsx` (new step tags render); relationships fetch/render
  test; backend route test.
- **Commit:** `(6/6) Complete: Inspector step polish + live relationships in the Director rail.`

## 4. Validation

Backend `uv run pytest utils/tests/backend` + ruff/mypy on touched files per phase; frontend
`npm test` / `typecheck` / `lint` / `next build` for P6. Merge to `main` (`--no-ff`, local, no
push) after P6, re-verifying green.
