# Mytheca — Checklist

**Genuinely open work only.** Completed work is not tracked here — every shipped feature has a plan under `docs/plans/` and a commit series in git history. This file was previously a 742-line append-only log whose "next steps" section had gone stale enough to contradict its own completed entries (it still listed the NDJSON stream, the validator, and the vector DB as unbuilt long after all three shipped). It is now kept short on purpose.

Verified against the code on 2026-08-04.

## Undesigned decisions

| Decision | State |
| --- | --- |
| **Auth mechanism** | Completely undesigned. There is no `User` model, no auth routes, and no session or token handling anywhere in `web/backend/app/`. JWT-vs-cookie, provider, and whether the app becomes multi-tenant at all are open. Everything downstream — protected routes, per-user libraries, admin surfaces — is blocked on this. |
| ~~**Stat lifecycle across scenarios**~~ | **Decided 2026-08-21 (owner decision D-1): reset, with an opt-in carry.** Stat *values* are scoped to a play-through (`session_character_stats`); `character_stats` holds the character's **authored** starting value and is what every new play-through begins from. `StatDefinition.carry_over` decides whether a play-through's ending value writes back onto the character when the session closes — so a stat carries between scenes only when it says so. Two play-throughs of one scenario no longer share a value, which is what makes branch and rewind correct. **`hidden` visibility is now implemented** (`depth-for-players.md` Phase 11): a hidden stat's `state_update` is persisted, traced and exported but **not streamed**, and `rehydrateFromHistory` skips it so a reload agrees with the live stream. The values were already excluded from the rails — `StatSchema` renders only `public` defs — so the gap was the changes, not the display. |
| **Deployment target** | Undecided: containerized full-stack on one host vs. split hosting. Nothing is configured. |

## Owed refactors

- **`services/llm.py` is at 800 of 800 lines and the next addition fails the gate.**
  `test_no_backend_module_exceeds_the_line_ceiling` caught it at 801 on 2026-08-31, after
  the merge of `claude/coding-session-process-4cf348` added the `restart` field and its
  stream handling. It was brought back to 800 by deleting one blank comment separator —
  which is not a fix, it is a stay of execution. The test says what is actually owed:
  *"Split them into their own phase rather than raising this number."*

  The seams are visible: the module holds the blocking path, the streaming path, the
  reasoning splitter plumbing, engine detection and the stop-sequence safety logic. The
  streaming half is the obvious extraction — it is the part the provider adapters already
  reach into, and `llm_backend.py` shows the pattern. **Do not raise `MAX_LINES`.**

## Unbuilt capabilities

- **Only ONE of the four LLM providers is verified against a live endpoint.**
  `openai-compatible` is exercised constantly — it is what this install runs on, its adapter
  was verified byte-identical to the previous implementation (key order included) by a parity
  harness, and a full `scene_smoke` turn plays through it with 0 problems. `anthropic`,
  `gemini` and `ollama` are verified only against their reference documentation, an
  adversarial review, and 46 contract tests. **None of the three has ever made a real
  request.** Everything most likely to be wrong in them is invisible offline: whether a body
  is accepted, whether a stream frames the way the docs say, whether usage fields carry the
  names claimed. Treat them as "written carefully, unproven", and expect the first live call
  of each to find something.
- **Nothing has ever streamed from Anthropic, Gemini or Ollama.** The code exists as of
  2026-08-31: `llm.chat_complete_stream` reads a stream entirely through the active adapter
  (`stream_media_types` for the media check, `parse_stream_line` for framing, then
  `stream_delta` / `stream_reasoning` / `stream_usage` / `stream_finish_reason` for the
  contents), `llm.stop_is_safe` consults the adapter instead of hardcoding llama.cpp's
  behaviour, and all four adapters declare `streaming_dispatched = True`. The blocking path
  was half-wired the same way and is fixed in the same change: it built the URL and body
  through the adapter and then sent a hardcoded `Authorization: Bearer` header and read
  `choices[0].message.content` itself, so on Anthropic and Gemini a successful call parsed
  as an empty completion. Thirteen dialect tests live in
  `utils/tests/backend/services/test_llm_stream_dispatch.py`.

  **That is not the same as working.** Those tests are fakes written from the same reference
  documents as the code, so they cannot catch the code and the test being wrong together,
  and the failure modes here are the silent kind: a media type answered differently in
  practice falls back to the blocking path and logs nothing, and usage carried on an event
  this reader does not ask blanks the player's context dial with no error. Expect the first
  live stream of each to find something.

  Two known gaps behind the same wall, both invisible offline. Anthropic **multi-turn
  thinking is unsupported by construction** — the seam types a message as `dict[str, str]`,
  so the `thinking` blocks the reference requires be replayed unmodified are already gone
  before the adapter sees them; turn one succeeds and turn two is a 400. And Ollama reports
  no prefix-cache figure at all, so the context dial reads "unknown" rather than a number on
  every Ollama turn.
- **Per-role model routing is still not possible.** "Cheap model for the planner, strong model
  for prose" is the main practical reason to hold several providers at once, and the seam does
  not deliver it: one global model id still serves ~25 agent call sites via the positional
  `LlmConn` four-tuple. Doing it means making `LlmConn` a dataclass and deciding a product
  question — how the engine should spend money and latency — that is the owner's, not an
  implementation detail. **Human decision needed.**

- **The library shell's 2026-08-31 rebuild was verified by tests and a production build, not
  by eye.** Everything else in that change set was checked live at 320 / 390 / 1280 in a real
  browser; the library half was not, because the agent's browser pane stopped rendering the app
  partway through the session — every route shows the `app/loading.tsx` fallback while the real
  tree sits in a `hidden` container.

  **The mechanism, measured, so nobody re-debugs the app for it.** The pane loads external
  `<script src>` bundles but does not execute inline `<script>` elements. Next streams the RSC
  payload as inline `self.__next_f.push(...)` calls: in that pane the seven such scripts are
  present in the DOM and `self.__next_f` is **0 chunks, 0 bytes**. So React hydrates the shell
  from the external chunks (`__reactFiber$` is on the tree) and then waits forever for a route
  segment payload that will never arrive. **This is the tooling, not the app.** Two controls
  confirm it: the pre-session commit `af6a9f0` reproduces it exactly, and so does
  `next build` + `next start`, since both stream RSC the same way. A real browser is unaffected.
  What was still verified: 1510 co-located tests including new ones pinning each structural
  change, `tsc`, ESLint, the contrast and CSS gates, a clean production build, and real
  measured geometry at 390px taken by un-hiding the SSR tree (header controls 44x44, the
  wordmark folded, the duplicate column heading `display: none`, the tab bar's three tabs plus
  its add button inside 390px, zero horizontal overflow). What was NOT: the scroll-snap hero
  under an actual finger, and the vertical rhythm of the page as a whole. **Swipe the hero and
  scroll the library on a real phone before trusting either.**
- **The story player's mount-time long frames are unexplained.** Under 4x CPU throttle the player
  produces a ~240ms long animation frame (~190ms blocking) at `scrollY 0`, plus 11-12 frames over
  1.5x the 16.7ms median and 9-12% dropped frames. Phase 3 of the website overhaul removed two real
  redundant forced layouts (`Composer.resize` and `BeatEditor` each read `scrollHeight` again after
  writing `height`) and **measured no change** — 241ms -> 247ms, dropped 8.82% -> 11.76%, n=1 per arm
  headless, i.e. noise. Those are keystroke paths and nothing types during a scroll pass, so the cost
  is mount/hydration work instead. Needs a profile, not a guess; `--headful` first, since headless
  under-reports jank.
- **At least eight frontend tests are flaky under full-suite load**, all timing-sensitive with
  real timers. Two were known: `ToastProvider.test.tsx` "holds the auto-dismiss timer while the
  pointer is over the toast" and `CharacterModal.test.tsx` "drafts a full character from a seed
  into the form". Running the suite on 2026-08-31 while a production `next start` shared the
  machine took six more down with it — in `ScenarioCard`, `ScenarioCarousel`, `CreateImageBar`
  and `PortraitModal` — at 5-16 seconds each, against sub-second times in isolation. Every one
  passed both in isolation and on a re-run with the server stopped.

  The number is a symptom, not the finding: **these tests measure the machine, not the code.**
  Any of them can fail on a busy CI runner, and a suite that fails for a reason unrelated to
  the change under test teaches people to re-run rather than to read. The fix is fake timers,
  not longer deadlines.
- **`viewport-fit=cover` and safe-area insets are not adopted.** `app/layout.tsx` declares
  the viewport but deliberately omits `viewportFit: "cover"`, because that and
  `env(safe-area-inset-*)` are all-or-nothing: opting in makes every fixed/sticky element —
  both header bars, the composer, every `Drawer` — responsible for insetting
  itself, and landscape moves the insets to left/right. Without it the browser letterboxes
  into the safe area automatically (safe, with visible bars). Adopt both together or neither.
- **`/storylines/new` and `/storylines/[id]/edit` render no header bar at all**, so there is
  no in-app way back except browser back. Every other route now shares the `HeaderBar`
  chassis at one height. Deliberate for a full-screen editor, but it means the skip link on
  those routes skips nothing.
- **`app/not-found.tsx` is reachable only for genuinely unmatched paths.** `/<anything>`
  matches the `[storylineId]` dynamic segment first, so an unknown storyline renders the
  storyline route rather than the 404. Pre-existing routing behaviour, recorded because the
  new not-found page makes it look like it should have caught that case.

- **Nothing measures free-text mode against the structured one.** `sceneMode: "freetext"`
  (`docs/plans/free-text-mode.md`) ships on the owner's judgement — preference-driven and
  deliberately so — and the honest statement of its trade is that it **sells per-character
  prompt isolation**: every voice sample sits in one prompt, which will pull the cast together
  and will pull hardest on the weakest models. Nothing in the repo says whether that shows up
  in the writing, or whether the continuity it buys outweighs it. This is recorded because a
  future reader will otherwise assume a default was measured; it is not a request to run one.
- **The free-text passage allowance is chosen, not measured.** `freetext_agent.PROSE_TOKENS`
  is 6,000 (~24,000 characters, about eight times the longest honest beat ever measured here).
  It is an endpoint-protection stop, not an editorial one — the 48,000-token generation that
  timed out the relay's health probe three times is why any ceiling exists — but where exactly
  it sits was a judgement call, and the owner set it.
- **A free-text turn is one beat, so the record controls apply to the whole passage.**
  Re-roll and re-roll-the-turn collapse into the same action, and beat-level editing has
  nothing smaller than the turn to edit. `beat_rerun` has not been exercised against a
  `scene_prose` row. The alternative — exempting free-text turns from beat-level controls
  entirely — was left open rather than decided.
- **`cast_request` does not exist in free-text mode.** It is produced by `intent_agent`, which
  that engine deliberately does not call, so naming an absent character has no effect there.


- **Re-running world population on an existing world.** `POST /storylines/{id}/populate/stream` is only wired to the create flow (`BuildWorldModal` → `commitWorld`). A world created before the feature, or one whose population partly failed, has no in-app way to top up its cast — the author adds the rest by hand. The endpoint itself is id-scoped and would work; it needs a Library-side entry point (and a decision about whether it appends to, or dedupes against, the existing roster).
- **Population never proposes scenarios.** It writes characters and settings only (each character whole — draft, voice profile, starting stats, portrait); the first scenario is still authored by hand.
- **World-build runs are in-process and non-durable.** `services/world_populate_runs.py` keeps a run's frame log in memory, keyed by storyline. A backend restart ends the run (the client is told, and never silently rebuilds), and a multi-process deployment would not share the registry. Durable runs (a table + a worker) are unbuilt.
- **A stopped build leaves a partly-built world.** *Stop* aborts the stream but does not roll back the rows already committed, and there is no in-app way to resume the run — the author finishes the cast by hand. Tied to the missing re-run entry point above.
- **The delivery check is lexical, and its threshold is unmeasured.** A requirement is no
  longer ticked off for merely entering a prompt — `services/direction_check.py` scores the
  prose the beat actually emitted (2026-08-22). But the score is word overlap, not meaning:
  `DIRECTION_COVERAGE_THRESHOLD` (0.34) and the stopword classes were chosen from an argument
  about how prose works — writing paraphrases a requirement's verbs and keeps its concrete
  nouns — plus two live cases that misfired before them. **No sweep has been run.** The
  failure mode is stated and deliberately one-sided (an unconfirmed requirement is *retried*
  and reported as unconfirmed, never dropped), so a false negative costs a beat while a false
  positive would lose what the player asked for. An LLM "did that happen?" check is still
  rejected — it would roughly double the turn's call count. What is missing is a measurement;
  see `docs/research/OPEN_QUESTIONS.md`.
- **`contextBeats` survives as an API-only setting.** The player control is gone — the window
  fits itself to the model's real context budget — but `contextBeats` is still honoured under
  `contextPolicy: "fixed"` and still validated (5–100). It has no UI, and the only things that
  set it are the three research harnesses, which need a fixed depth rather than a moving
  target. It is a deliberate API-only escape hatch, not an oversight; delete it only when no
  experiment needs a pinned window.
- **Compaction was measured, came out against itself, and stays off.**
  `TURN_CONTEXT_COMPACTION` defaults to `false`.
  [`EXP-2026-08-011`](research/experiments/EXP-2026-08-011-context-compaction/) ran on
  2026-08-22 and the compacted arm **lost the planted fact the control kept** (3 of 9 content
  tokens against 6; the summary had reduced *"owes the harbourmaster four hundred crowns, brass
  key sewn into his collar"* to *"owes 400 crowns"*), while rewriting the summary **16 times**
  against a predicted 4 and halving the reusable prompt prefix (80.3 % → 44.6 %). Claim
  **C-013** stays `unsupported`. n = 1 scene per arm, so this is an existence proof against
  compaction and not a rate — it does not make the claim `refuted` either. Nothing may describe
  compaction as free, or default it on, on this evidence.
- **Blocking product question: should the `world` tie scope be offered at all?** At that
  stop a speaker is given their ties to characters who are **not in the scene**, marked as
  *"Elsewhere: …, who is not in this scene."* The intended effect is a character who carries
  their life with them. The risk is the same mechanism read badly: a character mentioning
  somebody the player has never met, in a scene that has no way to introduce them, which is
  indistinguishable from the model inventing a person. The prompt marker is a mitigation, not
  a proof — nothing measures whether the cast honours it.

  Shipped **non-default** (`scene` is the default and `NULL` reads as it), behind an explicit
  control whose copy states the consequence in as many words. **This needs a human decision**,
  not an experiment: whether that is a feature of a living world or a bug in a scene is a
  question about what the product is for. If the answer is no, the stop is one entry removed
  from `TIE_OPTIONS` and one branch removed from `beat_runner.relationship_note`; the query
  and its tests can stay.
- **The looseness step size is chosen, not measured.** A character's `looseness` moves the
  register's `top_p` by **±0.03 per notch** (`character_turn_agent._LOOSENESS_STEP`), clamped
  to `[0.70, 0.98]`. That number was picked so a single notch is at most one register row's
  worth — it is not the output of any experiment. A known consequence, recorded rather than
  hidden: the full ±2 range spans 0.12 against a register span of 0.10, so a `+2` character
  on a **grave** beat samples looser than `tense`. Whether that reads as character or as the
  dial overriding the moment is exactly what is untested.

  Protocol sketch: a blinded matched-scene comparison at `-2 / 0 / +2` on the deployed model,
  **interleaved in one session** (day-apart comparisons on this endpoint are worthless — see
  above). The judgement is a preference between matched beats, so it needs a reader who has
  not seen the arms labelled, or it is not answered at all.
- **The looseness dial must never be extended to the penalty columns.** `frequency_penalty`
  and `presence_penalty` are held at `0.0` at every register × looseness combination, and a
  test asserts it at every combination precisely because a "looseness" control is the change
  most likely to reach for them next. EXP-2026-08-007 measured those penalties degrading the
  sentence structure of character prose — they fall on the punctuation and function words
  prose is made of, and the arms did not overlap. **Before any such extension, the drift eval
  this file already names has to run**: repetition of a character's own phrasings across a
  long session, or blinded speaker attribution, with the penalties off and on. EXP-2026-08-007
  measured *structure*, not drift, and it ran on **one model**.
- **Scene presets are built-in only.** The four in `content/scene_presets.py` are authored
  code, deliberately (a preset is part of how the app reads, not data an operator edits in a
  row — the same reasoning as the graph type registry). A **storyline-authored** preset is a
  real want and is not built: it would need a table, a schema, an authoring surface, and a
  decision about whether a world's presets replace or extend the built-ins.
- **Looseness cannot be edited from the dossier.** `CharacterDossier` shows a character's
  word-choice setting read-only during play; changing it means going back to the Library.
  Deliberate for now — editing a character mid-scene is a different decision from reading
  one, and it raises "does this apply to the beat already streaming".
- **The scene-config popover is up to seven controls.** `depth-for-players.md` took it from
  three to seven (preset · max turns · suggestions · beat length · planning · ties ·
  register), and at 320×720 it measured **1004px tall with its top edge at -386px** — the
  first three controls were off-screen and unreachable, and the panel was not scrollable.
  Fixed in Phase 12 by bounding it to the viewport (`max-h-[calc(100dvh-140px)]` +
  `overflow-y-auto`), which is now what keeps the *next* control reachable rather than
  silently lost off the top. **The pressure itself is not fixed**: a seventh control in a
  popover is close to the limit of what a player will read, and the honest next move is
  grouping or a second surface, not an eighth row.
- **`StatDefinition.carry_over` was unreachable until 2026-08-22, so nothing had ever
  carried.** Found while implementing `depth-for-players.md` Phase 11. The column existed on
  the model and `session_stats.carry_forward` read it, but the field was absent from
  `StatDefinitionBase` / `Update` / `Read`, absent from `create_stat_definition`'s insert, and
  had no UI — so it could only ever be `False`, and `carry_forward` was dead in the same way
  `secret_reachability` is. Owner decision D-1's "reset, with an opt-in carry" had a reset and
  **no way to opt in**. The field is now on the schema and the create path, so the mechanism
  is reachable; **it still has no authoring UI**, which is the remaining half.
- **`CharacterStat.baseline` is defensive, and the risk it defends against is real but not
  yet live.** `carry_forward` overwrites the authored value in place, so a character who had
  been played once would no longer remember what they were written with, with no way back.
  Because `carry_over` could never be true (above), that had never actually happened on any
  world — which is exactly why it was worth fixing *before* enabling the flag rather than
  after. `POST /characters/{id}/stats/reset` restores it; a stat that never carried has no
  captured baseline and resets to itself.
- **"Start this scene fresh" was NOT built, deliberately.** `depth-for-players.md` Phase 11
  specifies a Begin-scene checkbox that resets the cast. With nothing carrying (above) it
  would be a control that silently does nothing, which the same plan forbids elsewhere. The
  reset endpoint it needs exists and is tested; the checkbox belongs with the carry-over
  authoring UI, and both should land together or not at all.
- **Planning off is unmeasured, in both directions.** `plannerMode: "off"` /
  `overrides.planner: "off"` replaces the ReAct planner with `services/beat_order`. The
  saving is *inferred* from EXP-2026-08-005's 41 %-of-turn-time figure for the planner, and
  the quality cost is *argued* from what the mode structurally cannot do (no register, no
  stakes, no mid-turn narration, no exits). **Neither has been run.** The control's copy
  states the cost, which is the honest position while it is unmeasured, but nothing may claim
  a speed-up figure until it is.

  Protocol sketch: an **interleaved A/B inside one process run**, per this file's own rule
  that day-apart comparisons on this endpoint are worthless — the same scripted lines against
  the same generated world, alternating `planner` / `off` scene by scene. Report seconds per
  turn and beats per turn as counts, and treat any prose-quality claim as needing a blinded
  read or not being made at all (`EXP-2026-08-011` §H3 is the worked example of choosing "not
  measured" over a rubric invented afterwards). Per-run rows and no aggregate if any scene
  fails.
- **`maybe_compact`'s trigger is wrong, and the experiment found it.** The gate tests
  `fit.dropped_beats < block` — beats dropped *in total*, not beats dropped *since the last
  summary* — so once one anchor block has ever fallen out of the window it never closes again
  and the summary is rewritten nearly every turn. That is the whole of the prefix-reuse loss
  above, and it means the bounded design the code's own comment describes **has never been
  run**. The fix is a condition on `len(fresh)`, plus a unit test that fails on the current
  one; it is deliberately not applied inside the completed experiment's change, because the
  recorded numbers describe the code at `code.commit`.
  → `research/experiments/EXP-2026-08-011-context-compaction/ISSUES.md` §6
- **The memory edge is accurate to within a beat or two.** `MemoryEdge` marks where verbatim
  recall stops by counting back `windowBeats` rendered transcript messages — but messages and
  buffer beats are not exactly 1:1 (an internal thought folds into its speaker's beat), so the
  line can sit a beat or two off. It is enough for the marker's job (telling the player there
  IS an edge, and roughly where), and the exact figures are in the scene-memory panel, which
  reads them from the engine rather than counting rendered messages. Making it exact would mean
  carrying a per-message buffer-beat count through the transcript.
- **A standing direction never expires on its own.** What a turn could not deliver is carried
  forward indefinitely until it lands or the player dismisses it
  (`play_sessions.standing_direction`). A direction the scene has quietly moved past will keep
  being re-owed, and the remedies are the dismiss control and a rewind past the turn that raised
  it (`session_state.standing_through` drops rows whose `fromTurn` is above the cut). A
  turn-count or relevance-based expiry was not designed.
- **`@` mentions have no inline chip.** The composer's tagged row shows what a turn will
  carry, but inside the textarea an `@name` is plain text — there is no styled token, because
  a `<textarea>` cannot hold one. Doing it properly means a contenteditable or an overlay, and
  both were judged too large for `docs/plans/steering-the-scene.md`.
- **Graph edges from a rewound turn are not rolled back — now the last thing a rewind fails to
  forget.** `session_state.truncate_session` prunes the `:Event` node each cut turn wrote
  (deterministic id `evt_{session_id}_{turn_seq}`), but the relationship **edges** and
  `:Consequence` nodes those turns wrote stay. The graph is a best-effort accumulator with no
  per-turn provenance index, and adding one was out of scope for
  `docs/plans/control-over-the-record.md`. The effect is that a rewound scene can leave a
  relationship the transcript no longer explains, and `graph_reader.relationship_context()` puts
  it in the next prompt. Fixing it means recording the turn seq on every edge write in
  `graph_writer` and deleting by it.

  **Measured, not assumed:** [`EXP-2026-08-014`](research/experiments/EXP-2026-08-014-record-controls/)
  records `graph_edges_before` / `graph_edges_after` on a live rewind. As of that run the other
  two leaks it found — interior state and the standing direction — are closed, so this is the
  only known channel by which a rewound scene can still know something the transcript does not.
  n = 1 scene, so the *size* of the leak is not established; its existence is.

- **A turn can write the same narration more than once.** Observed live on 2026-08-22
  ([`EXP-2026-08-014`](research/experiments/EXP-2026-08-014-record-controls/) `ISSUES.md`
  O-1): one turn produced three distinct `narration` event rows holding **byte-identical**
  text. Three rows in Postgres, not a streaming artefact. Nothing in the beat loop dedupes a
  narrator interstitial against what the narrator already said this turn. n = 1 scene, so the
  rate is unknown; the existence is not. Uninvestigated — it surfaced inside a run scoped to
  the record operations.
- **Emission scaffolding can reach the transcript as prose.** Same run, same scene: a
  `narration` row began `] ... 'Is this how you greet a business associate?' I ask."). *` —
  a fragment of the emission format, persisted and rendered as narration. `services/emission.py`
  and `services/validator.py` are the places that would have to reject it. Also n = 1, also
  uninvestigated for the same reason.

- **Alternate takes are capped at five.** `beat_rerun.MAX_TAKES` keeps the five most recent
  versions of a beat and drops the oldest. A player who re-rolls a beat six times cannot get
  back to the first wording. Five is enough to compare against and small enough that the row
  stays a row; raising it is a one-constant change if it ever bites.
- **A turn-scope re-roll keeps no takes.** `scope: "turn"` truncates and replays, so the previous
  version of the whole turn is gone. A per-beat pager cannot express "these four lines, or those
  four" — the way to keep both is to branch before re-running a turn. The UI does not currently
  say so.
- **A branch does not copy the Neo4j `:Event` nodes.** `session_state.copy_history` copies the
  Postgres rows and the session's stat values; the graph nodes the parent's turns wrote stay
  attached to the parent alone. The graph is best-effort, so a fork simply has less graph history
  than its parent rather than a wrong one.
- **There is no cross-client lock on the record.** Concurrency is the `expectedSeq` precondition
  only: a stale view gets a 409 and reloads. Two clients editing *different* beats of the same
  play-through at the same moment will both succeed, and the second buffer rebuild wins. Fine for
  a single-player app with no auth; it would not be for a shared one.
- **Rewind cannot restore a stat that only legacy rows touched.** `session_state.replay_stats`
  re-derives from the surviving `state_update` rows, which works for any row ever written. But a
  stat changed *only* by turns that were themselves cut, in a session with no surviving
  `state_update` for that key, returns to the authored baseline rather than to its mid-scene
  value — correct by the model's definition, but worth knowing it is a definition and not an
  accident.
- **Relationship / mood stats** — extend the stat machinery to values with a relational target. Relationships currently live only in the graph.
- **Scenario-level stat additions and range overrides** — described in old docs, never implemented; `Scenario` has no such column.
- **Separate `GET /stream` transport** — the turn POST streams NDJSON directly. A standalone stream endpoint with Redis pub/sub fan-out is a seam, not a plan.
- **Cross-encoder rerank** — `RERANK_MODEL = "BAAI/bge-reranker-v2-m3"` is pinned in `rag/const.py` but nothing calls a reranker.
- **Neo4j KG-edge expansion in retrieval** — walking `related` edges during RAG retrieve.
- **RAG-first ingestion + tool-calling authoring** — plan exists (`docs/plans/rag-first-ingestion.md`), not implemented.
- **Text2Cypher read path** — `type_registry.schema_blob()` is compiled but has no consumer.
- **Register-aware narration.** The per-beat `register`/`stakes` from `planner_agent.next_beat` reaches the *character* prompt but not `narrator_agent` — narration still leans on the authored `Setting.atmosphere` for scenery. A grave beat should narrate differently from a light one; the signal is already on `BeatDecision`, so this is threading, not new machinery.
- **A live scene state.** `Setting.current_state` and `Setting.atmosphere` are written at world creation and **never again during play**. The character prompt no longer misrepresents them as the present moment, but nothing yet maintains a rolling "what this place is like now" line from the transcript.
- **Reflection effort is pinned to `LOW`.** The disposition it produces is now 2–3 sentences and sits in the character prompt's recency tail, so it carries real weight — but `dispatch_reflection` runs **inline** by default (`TURN_ASYNC_FINALIZE` is off) and a crowd (cast > 2) reflects **universally**, so raising `REFLECTION_EFFORT` to `MEDIUM` would put a whole cast's reasoning budget on the turn tail. Revisit together with async finalize, or gate the effort on cast size.
- **Nothing measures whether the register works.** Phases 1–5 of `docs/plans/character-dialogue-flexibility.md` are validated structurally (the register reaches the prompt, the right samples are selected, the sampler moves) — no experiment shows that output quality improved. A grave-beat manner-adaptation eval belongs in `docs/research/experiments/`.

  **The player-pinned register (`overrides.register`) makes that eval materially cheaper to run**: the register becomes an independent variable a harness can set directly on the turn request, instead of a value it has to coax out of the planner by writing scenes it hopes will be read as grave. Nothing about shipping the pin is evidence that pinning improves output — it is a control, and it is still unmeasured. It also widens what an eval must cover: the pin reaches three paths that previously carried no register at all (a puppeted beat, a forced-direction beat, the silent-turn backstop), so a register eval that only exercises planner-chosen beats now tests less than the feature does.
- **The in-voice penalties were removed against a drift risk nobody measured.** `frequency_penalty`/`presence_penalty` are now `0.0` on every register because EXP-2026-08-007 showed they were what destroyed sentence structure (1.32 ± 1.16 vs 11.42 ± 3.96 sentences per 100 words, no arm overlap). They had been added to fight **in-character drift**, and that experiment does not measure drift at all — so the trade was taken on one side of the ledger only. The `_REGISTER_SAMPLER` column is kept at zero rather than deleted so a measurement can put something back. What is needed is a drift eval (repetition of a character's own phrasings across a long session, or blinded speaker-attribution) run with the penalties off and on; until it exists, "removing them costs nothing" is an assumption, not a finding.
- **The sampler finding is one model deep.** EXP-2026-08-007 ran entirely on upstream `qwen38-27B-awq`. The endpoint has since served `gemma4-26B-mtp`, on which only the *shipped* configuration has been observed (EXP-2026-08-008) — the arms have never been re-run there. Reconsidering the penalties on a different model means re-running that experiment, not extrapolating.
- **Composure as a stat, and a tonal redo pass** — the two rejected arms of the same design (ideas 4 and 6). The stat machinery already renders bands to prose; the beat-redo seam that used to live on the continuity guard went with it, so a tonal redo would now need its own. Both are cheap enough to revisit if the register alone proves insufficient.
- **YAML config loaders** in `app/content/` — only the Markdown stat-guidance loader exists. Entities live in Postgres, so this may simply be unnecessary; decide rather than leave it pending.
- **Dice-based resolution** — explicitly dropped (decision D11), not merely deferred. The `CheckCard` renderer was removed. Reopen only as a deliberate reversal.

## Adaptive pacing — what removing the controls left open

`maxTurns` and `beatLength` were removed on 2026-08-24, along with the four scene presets
that were defined entirely in terms of them. What replaced them is a prompt directive with no
number in it and the planner's own judgement about when a turn is done. Four things that
leaves genuinely open:

- **Turn length was the planner's problem, and prompt wording did not fix it — MEASURED, then
  closed structurally (2026-08-26).** With `maxTurns` gone the planner almost never chose
  `end`. The prompt fix (scoping the hand-the-floor rule to ORDER, stating `end` as the
  default) was shipped unmeasured; `EXP-2026-08-016` measured it and it **did not work**:
  turns of 18, 22 and 24 beats, with `_pressure()` escalating to a literal "END IT NOW" from
  the eighth beat and being ignored roughly sixteen times in a row. One player message cost
  **4524 s**.

  The cause was structural, not lexical: the loop re-planned whenever its beat queue emptied
  (`turn_engine`'s `elif not planned:`), so no instruction to stop could bind. The turn is now
  planned **once** and that plan is executed — see `docs/plans/binding-plan-and-execution-arms.md`.
  A live scene that produced 18-24 beat turns now runs 3.

- **OPEN, and a product decision: what may add a beat past the plan?** Two contracts still
  can, and both predate the binding work, so neither was repealed by it:

  1. **The player's direction.** An instruction they typed outranks a plan's length. When a
     plan ends with one undelivered, the plan is discarded and the engine reschedules — which
     re-plans. `EXP-2026-08-017` measured **3 planner calls** on such a turn where every other
     turn used 1.
  2. **The exchange floor.** A room with two people does not answer the player with one line
     (reported failure `ps_c015c506b1`; the owner's word was "back and forth"). A one-beat
     plan on a two-character scene therefore runs two beats — **without re-planning**, pinned
     by `test_bound_plan.py::test_the_exchange_floor_still_outranks_a_one_beat_plan`.

  Subordinating either to the plan is a one-line change that would read as a tidy-up and would
  reintroduce a bug somebody reported, which is why it is written down instead of done. The
  principled alternative is to move both guarantees **into the planner** — tell it every
  present character and every outstanding requirement, and let the plan satisfy them — so the
  floors become fallbacks rather than overrides. That is unmeasured and is the next thing to
  try. `turn_plan.PLAN_DOES_NOT_REPEAL_FLOORS` carries the same note in code.

- **OPEN: `continuous` under-renders a plan it was given.** Same experiment: with one planning
  call and a correct plan, the continuous writer produced **1 beat against 3 planned**, having
  never re-planned. It does not reliably emit a hand-off token per planned beat. Deliberately
  not patched during the run — tuning an arm mid-experiment produces the author's preferred
  answer — so it is carried here as the next thing to look at. Note the default is
  `continuous`, so this affects ordinary play, not just the experiment.
- **`TURN_MAX_BEATS` (24) is a runaway guard, and no longer paces anything.** Turn length is
  the plan's, and a bound plan raises the ceiling to its own length so a long plan is not
  clipped. Re-tune it if a runaway is ever seen again, and record the tuning rather than
  quietly editing the default. Note it guards the **per-speaker loop only**: a scripted
  continuous turn is emitted with no ceiling at all (`EXP-2026-08-016` measured 38 beats from
  one script), which matters more now that `continuous` is the default.
- **The backstop can overshoot by one.** It is checked once per loop iteration and one
  iteration may emit both a narrator beat and a character beat. Harmless — it exists to stop a
  loop and protect the endpoint, and one extra beat costs neither — but if it ever has to be
  exact, the check must move to the emission sites.
- **The `Scenario.max_turns` / `beat_length` columns still exist and are unread.** Dropping
  them was deliberately *not* done: another process may be running against the same dev
  database, and a column drop would 500 it. They can go in a migration whenever that is
  known to be safe. `scene_preset` is in the same position, and `ScenePresetId` currently
  degrades to `str` because `Literal[()]` is not a type.
- **`direction_agent.schedule` is now nearly unreachable.** It takes over when what the
  direction still owes no longer fits the beats that are left; with the budget at 24 rather
  than 5, a direction has to carry a dozen requirements to trigger it. It remains the only
  thing standing between a long direction and a silently dropped requirement, so it stays —
  but it is a safety net that will rarely fire, and its test now has to force the backstop
  down to exercise it at all.

## The two experiments are written and blocked, not missing

`EXP-2026-08-015` (point of view, pre vs post) and `EXP-2026-08-016` (continuous vs voiced)
are **pre-registered and unrun**. Protocols, runners, metrics and — for 015 — a pre-fix
worktree for the baseline arm all exist and were verified up to the point of generation. Each
folder's `ISSUES.md` records the blocked attempt.

What blocks them: the relay's `local` → `gemma-4-26B-it` reported `failed` for a four-hour
watch and there was no `llama-server` process at all. The relay registers endpoints; it does
not own the upstream, so nothing on that side can restart it. ComfyUI's 18 GB was freed and
did not help, which is what established the model was **absent** rather than starved.
`skynet` was not substituted: it is healthy but unsuited to this generation, and a
prose-quality number measured on it would be a fact about `skynet` that somebody would later
quote as a fact about the change.

To run them, with the model healthy:

```bash
uv run python -m utils.scripts.research.run_scene_script \
  --experiment docs/research/experiments/EXP-2026-08-016-continuous-scene-script --turns 6
```

**Until `EXP-2026-08-016` runs, the continuous default rests on judgement, not evidence.** It
is the owner's call and it shipped on their instruction — but nobody has yet read a single
continuous turn, and the experiment is capable of saying the default is wrong.

## Plan mode and continuous prose — shipped, and what is not yet known

- **Continuous scene flow has never been run against a real model.** `sceneFlow:
  "continuous"` is complete, unit-tested and behind a per-scene toggle defaulting to
  `"voiced"` — the path that has always shipped. The plan called for continuous to be the
  default; it is not, because the LLM endpoint was under test when it landed and defaulting an
  unverified generation path on would be reckless. Flipping it is one word once it has been
  read. **Nobody has yet read a single continuous turn.**
- **The bet it makes is still unmeasured.** `character_turn_agent` splits per speaker
  *because* per-character isolation keeps voices distinct; continuous prose puts every voice
  sample in one prompt. The owner's grounds for overriding that is that the isolation is not
  delivering, and `beat_stream.echoes_a_beat` exists because two characters once returned
  byte-identical passages — but that is one anecdote. `EXP-2026-08-016` is what decides it,
  and the metric that matters is voice distinctness against the voiced path.
- **The sampler is a genuine compromise in continuous mode.** A script spans several
  registers and there is one call to set `top_p` on, so it takes the first speaker's
  looseness and the plan's opening register. The voiced path does this properly, per beat.
- **Each hand-off is not gated the way a beat opening is.** `stream_emission` holds a
  passage's opening back and judges it (scratchpad, echo, second person, cross-speaker);
  `stream_script` cannot, because holding several hundred characters at every hand-off would
  turn a continuous scene into a stutter — the one property the mode exists to provide. The
  whole-passage guards still run, and the unscripted fallback catches the case that matters
  most, but a leaked scratchpad *mid-script* would reach the page.
- **Plan mode has never been used on a real turn either**, for the same reason. Its
  behaviour is pinned by tests including the two defects they caught (a plan frame with no
  session id; an approved plan whose cast has all left silently re-planning), but nobody has
  approved a plan and watched it play.
- **An approved plan is not re-validated against the direction.** If a player approves a
  plan and their direction still owes something the plan does not cover, the turn runs the
  plan and the requirement goes to the ordinary outstanding-direction machinery on a later
  turn. That is probably right — they approved it — but it is untested and unstated in the UI.

## Point of view — what the smoke test measures and what it does not

- **The narrator has no gate.** Character beats are held and judged before a word is shown
  (`beat_stream._pass` — scratchpad, echo, second-person, cross-speaker); narration streams
  straight out with nothing checking it. The worst line in the pre-fix baseline was the
  narrator's ("he reaches out to grab your wrist"), and the prompt fix is currently the only
  thing preventing it. A narration gate is defence in depth that has not been built.
- **`utils/scripts/scene_smoke.py` is a smoke test, not an experiment.** n=1, no arms, nothing
  recorded. It is a pass/fail gate for "does the scene still read correctly", and its numbers
  must not be quoted as measurements — anything comparative belongs in
  `docs/research/experiments/` under `AGENT_INSTRUCTIONS.md`. The before/after it produced
  (10 problems → 1; second-person 10 → 0) is an existence proof that the defect was real and
  is gone on that scene, not a rate.
- **It renders nothing until the turn completes.** It collects the whole NDJSON stream and
  then prints, so a long turn shows only its header for minutes. Stdout is line-buffered so a
  killed run keeps what it had, but per-beat progress would need the render to move into the
  frame loop.
- **`cross_speaker_speech` is a lexical check on a closed list of speech verbs.** It catches
  an attribution (`Zoe says, "…"`, `"…," Zoe says`, `Zoe: "…"`) and deliberately not reported
  speech. Its threshold is not measured; the failure direction is chosen (a missed leak costs
  a raised eyebrow, a false positive silently strips good writing), and it is the same
  unmeasured-lexical-rule position `direction_check` is already in.

## Known defects and rough edges

- ~~**The prompt cache is wasted, and it IS worth reclaiming at the configured settings.**~~
  **Reclaimed 2026-08-20.** `_build_user_prompt` put the speaker's current stat values,
  register-selected voice samples and recent lines ahead of the transcript, so one stat
  change invalidated everything after it. Over a real 10-turn scene (EXP-2026-08-005)
  cached tokens sat at **exactly 800** — the static system message — while the prompt grew
  1830 → 4678, hit rate 44 % → 17 %; at 100 / 200 / 400 turns of history the reordered arm
  cut time-to-first-token by **~40 %** and was the only one reporting any reuse at all.
  The prompt is now ordered stable → transcript → volatile, and the transcript window is
  **block-anchored** (`buffer.anchored_turns`) so its first line does not move every turn —
  without that, the reorder would have stopped paying at exactly the scene length it was
  meant to help. `reflection_agent` got the same treatment, since every present character
  reflects on one identical transcript. Pinned by
  `utils/tests/backend/services/test_prompt_cache_prefix.py` and the ordering assertions in
  `test_character_turn_agent.py`. Latency measured in EXP-2026-08-006; the **writing-quality**
  consequence of moving identity from primacy to recency is recorded there too.
- **The narrator and director prompts still lead with volatile text.** Deliberately left:
  both condition on a *six-beat* window that slides every beat, so there is no stable
  prefix to protect and reordering them would be prompt churn for no measurable gain.
  Revisit only if either grows a longer window.
- ~~**The inference endpoint's throughput varies 66× on identical work.**~~ **Withdrawn
  2026-08-20**, the same day it was raised. The probe behind it ran while the intended GPU
  was not connected. Repeated on the right hardware: 1.37–4.22 s over 12 runs
  (mean 1.67 ± 0.78) for byte-identical output — stable. The endpoint is not the bottleneck.
- ~~**The beat planner stalls, and a stall costs the player the full generation timeout.**~~
  Also withdrawn: the two ~300 s turns EXP-2026-08-005 attributed to the planner were on the
  same degraded hardware. No turn on healthy hardware has come near the timeout.
- **The planner is now the largest cost in a turn — 56 % of turn time at ~6.5 s per call.**
  Fixing the character beat promoted it to first place. Whether asking for three beats costs
  more per call than it saves is unsettled; an interleaved 1-vs-3 A/B is implemented
  (`run_conversation_scaling.py --mode plan`) and has not been run to completion. This is the
  next measurement worth taking.
- **Two small character-voice defects, counted on the final run.** `Mei: Rain again.` — a
  speaker prefix leaked into the spoken text (1 of 11 beats). And 2 of 10 private thoughts
  referred to *"the player"* ("The player's question hangs in the damp air"), a fourth-wall
  break invited by the transcript rendering the player's beats as `Player:`. Pre-existing;
  the fix is to give the player an in-fiction label in `_transcript`, which is a design
  decision (there is no player-character name outside POV mode) rather than a rename.
- **A descriptive brevity instruction did nothing; a countable one worked.** Asking the
  character for "one or two sentences" left thoughts at median 460 chars. "At most 2
  sentences and at most 40 words" produced median 214. Worth remembering when writing any
  length constraint into a prompt.
- **Multi-beat planning barely pays at `maxTurns = 5`.** The mechanism works — the model
  returned a well-formed three-beat plan 6/6 when asked (EXP-2026-08-006 `logs/plan.log`) —
  but the median turn is **2 beats**, and each turn needs one final planner call to say
  `end`, so lookahead has almost nothing to save. Planner calls fell only 34 → 27 over ten
  turns. It should pay progressively more as `maxTurns` rises; `TURN_PLANNER_LOOKAHEAD=1`
  restores the old per-beat loop exactly if it ever proves harmful.
- **Reflection is now the largest non-planner step by share** (6 % → 21 % of turn time
  between EXP-2026-08-005 and EXP-2026-08-006, though shares on this endpoint are soft). It
  was deliberately left untouched at the owner's request. `TURN_ASYNC_FINALIZE` already
  exists to move it off the request path if that changes.
- **The prompt reorder has not been checked for writing quality by anything but a read.**
  Identity and voice samples moved from primacy to recency. Ten turns were read and showed
  no obvious regression — n = 1, unblinded, by the author of the change. A blinded
  matched-scene comparison against the old ordering is the experiment that would settle it,
  and it relates directly to C-001, which is itself unsupported.
- **App-side latency work is unmeasurable until that is fixed, and future comparisons must
  be interleaved arms in one run.** EXP-2026-08-006 compared code versions a day apart
  because the prompt reorder is not flag-gated. Given the variance above, day-to-day
  comparison is worthless. Anything measured next needs both arms alternating inside a
  single session.
- **The beat planner is 41 % of all turn time.** It runs once per beat — three to six
  times a turn at ~4 s each — and is the single largest cost in the app, ahead of character
  generation (15 %), inline reflection (13 %) and the continuity guard (11 %, ~10 s each
  time it fired — **retired 2026-08-20**). Of the ~10 s before a player sees any prose,
  roughly 7.5 s is `intent`
  plus the first `plan` call, neither of which produces a word. Reducing the *number* of
  sequential calls is the lever for perceived latency; context size is not.

- ~~**The live reasoning channel is inert on the model the app is configured with.**~~
  **Withdrawn 2026-08-19.** EXP-2026-08-004 recorded `first_reasoning_s` as null on the
  deployed `skynet` route and concluded the model exposed no reasoning channel. It does:
  vLLM spells the field `reasoning`, llama.cpp spells it `reasoning_content`, and the
  parser read only the second. The null result measured the instrument. Fixed in
  `llm._reasoning_field`; the first reasoning token on `skynet` measures at ~0.4 s
  (EXP-2026-08-005). The experiment is amended rather than rewritten.
- ~~**The default Reasoning-visibility setting leaves the longest wait empty.**~~
  **Decided 2026-08-20: the default is now `full`.** The model spends most of a generation
  deliberating before writing its first word — ~17 s of ~20 s on the `local` route
  (EXP-2026-08-003), and on the deployed `skynet` route the first *reasoning* token arrives
  at ~0.4 s while the first *prose* token takes seconds longer (EXP-2026-08-005). The live
  reasoning channel covers that window, and now that it actually works on the deployed
  model the trade was worth taking: a visibly shorter wait against the risk that
  deliberation spoils the line it precedes. `summary` remains one click away in Options and
  the copy there says plainly what it costs.
- ~~**Later speakers do not stream their prose.**~~ **Resolved 2026-08-20.** The
  continuity guard was the sole reason a later beat had to hold its prose for a
  complete-line verdict. EXP-2026-08-005 measured the guard at 11 % of turn time (~10 s
  every time it fired), and it was retired rather than made incremental: every character
  beat now streams as it is written. Reopen only if continuity errors actually show up in
  play — at which point the incremental form (judge the line as it grows, cut the stream
  on a contradiction) is the design to build, not the blocking one.
- **Streamed prose can diverge from the persisted row on a harmony-format endpoint.**
  `strip_reasoning` keeps the text after the *last* `<|channel|>` marker, which cannot be
  known mid-stream. `InlineReasoningSplitter` handles the `<think>` form exactly and
  suppresses harmony control *tokens* as they pass, but a harmony endpoint that emits a
  leading `final`/`analysis` label, or several channel markers, could stream a fragment
  that the finished text then drops. Not reachable on the endpoint in use (it reports
  `reasoning_content` as its own field, so `content` is clean); it would surface on a
  model that inlines harmony channels.

- ~~**Dead code on the turn path.**~~ **Decided 2026-08-22: hidden, not deleted.**
  `director_agent.who_is_up` and `director_agent.rerank` are the superseded one-shot speaker
  picker — nothing in `services/` calls either, and `planner_agent.plan_beats` makes the real
  per-beat decision. Their prompt keys are now **hidden from the Options catalog**
  (`PromptSpec.hidden`), because a prompt an author can edit while nothing reads it teaches
  them that editing prompts does nothing, which costs more than the missing row. The functions
  and their tests stay: they are the **baseline arm of `EXP-2026-08-001`**, and deleting them
  would make that comparison unrepeatable. Hidden is not unresolvable — `keys()`, `default()`
  and `resolve_prompts()` still include them, so a stored override neither vanishes nor raises.
  **Revisit when `EXP-2026-08-001` reaches a verdict**; if the baseline is no longer needed,
  delete both functions, their tests and their registry entries together.
- **Stale module docstrings elsewhere in the tree.** The three worst offenders were corrected on 2026-08-04 (`services/turn_engine.py` described a "P3 single speaker / `_pick_speaker`" design that no longer exists, `main.py` said the brain and event stream were "added in later phases", and `graph_writer.py` called the edge/consequence writer unused machinery). Other modules have not been swept — treat any "this phase…" docstring as suspect until verified.
- **`TurnContext.subgraph` is fetched but unused.** The scenario subgraph is assembled every turn; its only consumer is a boolean `available` flag in the diagnostic trace. The graph reaches the model solely via `graph_reader.relationship_context()` — and, at the `world` tie scope, `graph_reader.offscene_ties()`. Either render the subgraph into the prompt or stop assembling it.

  **`depth-for-players.md` Phase 10 did NOT close this.** The tie-scope control widens the *relationship* read and adds one off-scene query; it gives `subgraph` no job at all. Recorded explicitly because "the graph is now used" is exactly the kind of half-truth that would let this bullet be deleted by someone skimming.
- **Nothing writes `Secret` nodes, so `graph_reader.secret_reachability` can never return a row.** Found 2026-08-22 while surveying the graph for `depth-for-players.md` Phase 10. `Secret` is a built-in node type in `content/graph_registry.py` (with `severity`, `truth_value`, `visibility`) and `_SECRET_REACHABILITY` reads it — but **every** `graph_writer.upsert_node` call site passes a hardcoded `type_name`, and the only three values in the codebase are `Character`, `Setting` and `Event` (`crud.sync_character`/`sync_setting`, `turn_writer._append_event`, `relationships`, `graph_reader.ensure_scenario_materialized`). No agent proposes one either. So this is dead in a stronger sense than "no callers": the query is correct and the data it reads has never existed on any world. Either write `Secret` nodes (the character's `secret` prose field is the obvious source, and the registry already says "often also a Secret node") or delete the query and the type together — but do not cite secret-reachability as a working feature.
- **Unused graph queries.** `graph_reader.presence_casting` and `graph_reader.secret_reachability` have no callers. **Still open after `depth-for-players.md` Phase 10** — that phase added `offscene_ties` and gave neither of these a job. `secret_reachability` is the worse of the two: nothing has ever written a `Secret` node, so it could not return a row even if it were called (see above).
- **`validate_relationship` substring fallback** will mis-bind on nested cast names ("Aldous" vs "Brother Aldous").
- ~~**Two frontend tests are load-flaky.**~~ **Fixed 2026-08-21, and completed 2026-08-22.**
  Every choreography-bound test now carries an explicit **15 s per-test budget** instead of
  Vitest's 5 s default: `CharacterModal`'s two and `SettingModal`'s two. (The 2026-08-21 pass
  fixed one of each pair and left the "shows draft progress / highlights the field being
  written" sibling in both files on the default budget — the same real-time bound, missed
  twice.) `ToastProvider`'s final `waitFor` gets 5 s. The assertions are untouched, and the
  budget is per-test rather than global so the next genuinely-hung test still fails fast.
  A sweep confirmed `useLibraryState` is the only flow that awaits `use-field-reveal`, so
  `StorylineCreatorView` and `ScenarioForm` need no treatment.
  **The remaining constraint is the runner, not the tests:** on a loaded machine the *full* suite
  needs `--maxWorkers=2`. At `--maxWorkers=4` under load ~47 a *different* test timed out on each
  run (`LibraryView.editors`, then `ToastProvider`), which is contention, not a defect — the same
  suite passed 876/876 at `--maxWorkers=2` under identical load.
- ~~**A third: `components/layout/ToastProvider.test.tsx`**~~ **Fixed 2026-08-21.** It was
  not the 3 s auto-dismiss: the dismissal fires under *fake* timers, and what the test then
  waited for was the exit animation completing under *real* ones, against `waitFor`'s
  default 1 s budget. Under CPU contention that is not enough — it failed on every full-suite
  run once this branch added five tests, and passed 850/850 at `--maxWorkers=4`. The final
  `waitFor` now gets 5 s; the assertion is untouched.
- **Ollama is still not *detected*, though it is no longer uncapped.** `LOCAL_LLM_BASE_URL` defaults to `http://localhost:11434` — Ollama's port — and `services/llm_backend.py` probes only vLLM (`GET /version`), llama.cpp (`GET /props`), and relays that name an upstream in `GET /models`. Ollama matches none, so it reports as `unknown`; since 2026-08-19 an unknown endpoint receives **both** engine budget keys, so the thinking budget is at least attempted. Whether Ollama honours either key is unverified — a native probe (`GET /api/tags`) and its own budget key remain unbuilt.
- **`web/shared/contracts/` is empty** while both layers hand-maintain their own copy of the event contract. Either populate it or drop the directory and document the manual mirror as the intended design.
- **An unreproduced connect failure on the storyline Assistant.** Reported as
  "Could not reach the server." on `/storylines/new` → Assistant → Send, on plain
  localhost with nothing in between, while the local LLM was still generating. That
  string can only come from a rejected `fetch()`, i.e. no response headers ever
  arrived — but the agent stream returns headers in 4–16 ms, so the request must be
  failing at connect time. **Ruled out empirically on 2026-08-11:** backend timeouts
  (300 s, never reached), connect failures under load (60 POSTs at load average 5.3 →
  0 failures), the uvicorn keep-alive boundary race (a sweep across 4.3–5.6 s idle →
  0 rejections), and the dev-server reloader (its supervisor holds the listening
  socket, so a restart neither refuses new connects nor killed an in-flight stream in
  testing). Not reproduced locally. `lib/api.ts` now attaches `TransportFailure`
  (`path`, `elapsedMs`, `attempts`, `cause`, `phase`) to the thrown error and logs it
  — `elapsedMs` is the discriminator, since the browser reports every transport
  failure as an opaque `TypeError`. **Next occurrence: capture that console line.**
- **The blocking generation POSTs still hold a silent socket.** `/storylines/primer`,
  `/storylines/draft`, `/storylines/triage`, and the character/setting/scenario draft +
  art endpoints send **no bytes at all** until generation finishes (measured 7.1 s for
  the primer; minutes on a large local model). The agent *streams* got keep-alive frames
  on 2026-08-11 and the client now retries a connect-time failure once, but a hard idle
  timeout shorter than the generation would still kill these. The fix is to convert them
  to NDJSON streams with keep-alives, mirroring the existing `/triage` + `/triage/stream`
  pair. Not started — waiting on confirmation of which control actually fails in the
  field, since the work is a new endpoint plus UI per call site.
- ~~**Core Web Vitals have never been measured.**~~ **Measured 2026-08-22** —
  `EXP-2026-08-012`, the first production bundle this repository has ever built (the fonts
  were self-hosted the same day, which is what removed the blocker). At 4x CPU throttle,
  n=5 cold loads per route: the Library passes all three (CLS 0.0407,
  INP 9.6 ms, LCP 522.4 ms) and the story
  player passes CLS (0) and LCP (1684.8 ms).
  **What is still open: story-player INP is 440 ms against a 200 ms
  threshold.** The run records the controls clicked, and the sequence includes the chat/graph
  view switch, which mounts a force-directed canvas — a lead, not a conclusion. Isolating INP
  per control is a separate experiment and has not been run.
- **Not every async path routes through `AsyncPanel`.** The five-state shell exists and covers
  the Library columns, Documents, GraphView, and the modals; `useLibraryState`'s per-entity
  loads still fail silently to empty collections, so a partial failure is indistinguishable
  from an empty world.
- **`:disabled` was audited on the primitives only.** `components/ui/` all carry the four
  interaction states; the 48 feature components inherit them through the primitives but were
  not individually swept for bespoke `<button>`s that can be disabled. Contrast of the new
  disabled treatments (`opacity-45`/`opacity-60` over existing tokens) is not modelled by
  `check_contrast.py` and was not measured.
- **No LICENSE file.** The repository is all-rights-reserved by default.

## Deferred verification

- **The `VoiceSamplesEditor` Moment select has not been seen in a browser.** Added 2026-08-11. Verified by co-located component tests (native `<select>`, `<label>`-associated, reachable by accessible name, reuses the existing field styling) and by structural review: the row wraps at the 320px floor and the select is `max-w-full min-w-0` so a long option label cannot overflow. A live check was attempted in the worktree on a free port and **failed for an unrelated reason** — at the time `next/font/google` could not reach Google Fonts in this sandbox, so the page never rendered. That cause was removed on 2026-08-22 (the families are self-hosted). Folded into the consolidated pass below.
- **Live in-browser accessibility + responsive pass.** Deferred across a long series of UI
  changes against a persistent environment constraint. **Substantially closed on 2026-08-12**
  by the frontend-polish pass, and **closed again, more broadly, on 2026-08-22** by
  `docs/plans/reach.md` Phase 11 — recorded line by line in
  **`docs/plans/reach-acceptance.md`** (PASS 19 · PARTIAL 3 · FAIL 0 · DEFERRED 1), measured
  live at 320/375/768/1024 on the story player, the Library and `/storylines/new`. That pass
  found and fixed five defects no component suite had caught: no `<main>` landmark anywhere,
  an `h1 → h3` heading tree, an 18px-wide composer control, 57 beat controls in one tab order,
  and WCAG 2.1.4 unmet. The Google-Fonts blocker that shaped this entry is gone — the families
  are self-hosted, so `next build` runs offline and no shim is needed to render the app.
  - **Still not verified live:** screenshots (the browser pane does not composite frames — a
    bare CSS transition sits at `currentTime: 0` indefinitely, verified directly), and
    `:focus-visible` rendering (`document.hasFocus()` is false for the pane's own tab, so the
    selector never matches). Both are verified structurally, against the served stylesheet.
    Seeing the focus ring rendered needs a real browser window and remains genuinely open.
- **ComfyUI end-to-end render.** The generate → edit → save → reopen loop has never been verified against a running ComfyUI server.
- **Graph node/edge click → detail.** Confirmed by unit tests; could not be driven live because synthetic canvas clicks don't reach `react-force-graph-2d`'s internal hit-testing headlessly.

## Known UI limitations

- ~~Rails are hidden below `lg`; mobile drawers are unbuilt.~~ **Built 2026-08-22.** Below
  `lg` both rails open as bottom sheets from rows in the scene menu, and
  they mount the *same* `…Content` components as the desktop asides with the *same* prop
  objects — so per-character stats, presence controls, the turn order, the scene pulse, the
  scene state and the direction checklist are all reachable at every width. `TurnStatusStrip`
  still carries the live who-is-speaking signal in the reading column, which no sheet has to
  be opened to see.
- **The turn-status strip's `ending` phase depends on the engine reaching its end-of-loop
  trace step.** A turn killed by a mid-stream failure jumps straight from its last beat to
  no strip at all (the client's `.finally` reset), so "the turn is ending" is never shown on
  the error path. That is deliberate — the `role="alert"` stream error says more than a
  wind-down label would — but it does mean the phase is not a guaranteed terminal state.
- **The Core Web Vitals runner is bespoke, not Lighthouse.** `EXP-2026-08-012` drives
  `puppeteer-core` against the system Chromium and reads the `web-vitals` package from a
  flag-gated probe. That gives CLS/INP/LCP under a controlled 4× CPU throttle with no network
  dependency, but it is **not** a Lighthouse score and carries none of Lighthouse's other
  audits. Whether to adopt Lighthouse (and accept a heavier devDependency plus a networked
  environment) is open.
- **Story-player INP is 440 ms against a 200 ms threshold**, the one metric that missed in
  `EXP-2026-08-012`. The run records which controls it clicked, and the sequence includes the
  chat⇄graph view switch, which mounts a force-directed canvas — so one interaction very
  likely dominates the number. That is a lead, not a conclusion: `web-vitals` reports the
  worst interaction without attributing it, and isolating INP per control is a separate
  experiment that has not been run.
- **39 controls are under WCAG 2.5.8's 24×24 floor with a *mouse*.** Measured 2026-08-22 on
  `/storylines/new` at 1280 (`docs/plans/reach-acceptance.md`): `TriagePanel`'s Draft/RAG/Extract
  chips (20px tall), the per-doc category selects (23px), and five text-buttons across the
  creator ("New chat", "Generate primer", "Add statistic", "Cancel", "‹ Library" — 15–17px).
  The coarse-pointer floor in `motion.css` covers touch only, deliberately: inflating every
  control to 24px+ on a mouse would obey the rule while breaking the density the design system
  specifies. **Left as-is on purpose**, not overlooked — `docs/plans/reach.md` Phase 11 says to
  report the count rather than silently redesign it. The one exception already fixed: `Remove
  <file>` was 10×24, a destructive control ten pixels wide, and is now 24×24. A real fix would
  be `.touch-target-overlay` (a projected hit area that does not affect layout) applied per
  control, ungated by pointer type.
- **14 controls are under the repo's own 44px floor in *width* on touch.** All are 44px tall
  and all clear 24×24, so this is the house standard rather than WCAG. Same trade-off, same
  reason. Both counts are from `docs/plans/reach-acceptance.md`.
- Graph mode is canvas-only below `lg`; the `sr-only` node/edge table remains the data alternative. Graph node clicks are wired for Character only — other types are hover-tooltip only.
- **An unwanted scene image cannot be removed or replaced.** ~~Nor asked for by subject~~ —
  **the additive half shipped 2026-08-22** (`making-it-legible.md` Phase 11): the enlarged
  view's prompt is editable and *Paint again with this prompt* produces a **new** beat from
  the player's own wording, with names still stripped server-side. What remains is the
  **destructive** half: `DELETE …/beats/{id}` for an image and an in-place replace. Both were
  cut from `control-over-the-record.md` Phase 9 to keep it to the prose seam, and Phase 11
  deliberately did not build them — a second event-mutation path beside the one that plan
  owns is the wrong place to add one. An unwanted picture still stays in the beat log.
  (Note: `making-it-legible.md` Phase 11 was written expecting this entry to be gone by then.
  It was not; the prose-beat machinery landed and the image half did not.)
- **A scene image is not context.** It is persisted as a `scene_image` event, but nothing
  feeds it back into the turn loop; characters have no idea a picture was taken.

## Research record — deliberate gaps

The retrofit landed on 2026-08-06 (`docs/plans/research-record-retrofit.md`). These
are **decisions, not oversights**, recorded here so they are not mistaken for drift.

- **No CI and no pre-commit hook.** The contract's §7.4/§7.5 mandate both; enforcement
  here is `make validate-research` run by hand. Owner decision — Mytheca has never had
  a `.github/` directory. **This is the one acceptance criterion in §10 left unmet**,
  and the contract's own §7 warns that "convention without enforcement decays".
  Revisit if a second experiment lands without the validator having been run.
  (`docs/research/DECISIONS.md` D-005.)
- **EXP-2026-08-001 is recorded `failed`.** The planner-vs-director ablation could not
  run: no OpenAI-compatible endpoint is configured for this checkout, so every agent
  fell back or raised. 0 LLM calls. `C-005` stays `unsupported`. The harness is built
  and the protocol pre-registered — it is a re-run, not a rebuild.
- **EXP-2026-08-002 is a verification, not a comparison.** The in-narrative image
  prompt run (3 runs, one scene, one model) has **no baseline arm**, so `name_leak = 0`
  is observed, not attributed — the ablation with the name guard removed was not run.
  Its follow-ups are in `docs/research/OPEN_QUESTIONS.md`; nothing in `CLAIMS.md` moved.
- **Six of seven claims have no experiment at all.** `docs/research/CLAIMS.md` is the
  backlog; it is meant to look uncomfortable.
- **The audit's P1 study is not started.** 10–14 weeks, critical path 8–11
  (`docs/research/paper/OUTLINE.md`).
- **Degradation mismatch on the turn path.** `director_agent.who_is_up` propagates
  `APIError` where `planner_agent.next_beat` catches it and falls back, though both
  docstrings promise "best-effort; never raises". Found incidentally by the runner,
  not by a test. **Do not delete the dead director code while EXP-2026-08-001 is
  open** — it is the baseline arm.
- **The 2025 Wordplay accepted-paper list is unread.** ~30 papers on exactly this
  topic; the audit names it as the most likely place for a scoop it missed, and both
  remaining novelty claims rest on absence of evidence.

## `@` file tagging — deferred follow-ups

- **No token accounting for tagged text.** `ContextUsageDial` estimates from the beats and
  the model's reported `prompt_tokens`; up to 12 000 characters of tagged text is not in
  the pre-send estimate, so the dial under-reads until the turn's real usage comes back.

## Art styles — deferred follow-ups

- **`anime` and `photoreal` are prompt-only.** Neither ships with a LoRA, because none for
  either is installed in `~/Models/ComfyUI/models/loras/` and the base checkpoint
  (`zit_intorealism_zitV60`) is already realism-leaning. Both are one Options change from
  carrying one — the code path is generic — but the *file* half of that path has only been
  tested against a synthetic graph (`test_comfyui_lora.py`), never a real anime LoRA.
- **No sample for the in-play `moment` surface.** `EXP-2026-08-013` rendered the `portrait`
  and `scene` surfaces in all three styles; `moment` is covered by tests and by the same
  catalog but has no visual sample. Add one when the next scene image is generated anyway.
- **Style separation is untested on hard subjects.** One subject per surface in
  `EXP-2026-08-013`. A non-human species, a crowd, or an abstract place could plausibly
  collapse the three arms toward each other; nobody has looked.
- **A world build in flight keeps the style it started with.** `world_populate_runs`
  attaches to an existing run by storyline, so re-confirming with a different style
  re-attaches rather than restarting. Correct today (a run should not change look
  mid-flight), but it means the second choice is silently ignored rather than refused.

## Housekeeping

- **11 stale git worktrees** under `.claude/worktrees/`, all registered in `git worktree list`, each 25+ days idle with a merged-looking final commit. Prune them along with the ~45 leftover local branches.


## Narrative style guides — open follow-ups

- **The `signature` block is a deletion candidate.** It is the only block paid for on EVERY
  beat, and `EXP-2026-08-019` could not show it does anything: `baseline` 8.01 ± 2.11,
  `prefix` 7.29 ± 1.81, `prefix_signature` 8.18 ± 3.08, all overlapping. The only qualitative
  straw in the wind — the cross-scene texture carry-over — reproduced in the `prefix` arm
  *without* a signature. Keeping an unproven field is not the same as keeping a broken one,
  so it ships; but it should either earn a result or come out.
- **No measurement supports "the style guide improves the prose."** `EXP-2026-08-018` reported
  one; `EXP-2026-08-019` re-ran its *unchanged* baseline on the same prompts and moved it by
  more than the reported effect (5.70 → 8.01). Both experiments are recorded, the second
  amends the first, and every claim in `CLAUDE.md` / `docs/` / the source has been corrected
  to say the placement is justified by **cost**, not by quality. **A useful successor needs a
  different design, not more runs of this one**: many more scenes (the fixed opening anchors
  too much of the passage), a metric that is not a hand-rolled word list, and enough runs to
  state an interval that means something.
- **The Pacing block is unmeasured.** It targets the planner's system message, and neither
  `EXP-2026-08-018` nor `EXP-2026-08-019` makes a planner call. Whether a style guide changes
  *turn shape* — how often the narrator carries a beat, where a turn ends — is untested. It is
  also the block most likely to fight the planner's own "end as soon as the direction is
  delivered" rule, which is a real conflict and not just an unknown.
- **The cache claim is asserted, not measured across a turn loop.** Tests pin that the system
  message is byte-identical across speakers and beats, and that a scenario delta breaks the
  prefix only in its last quarter. Nobody has yet watched `usage_out["reusable_prefix_chars"]`
  over a real multi-turn scene with a guide attached.
- **Scenario-delta conflict is untested on the model.** The override is appended rather than
  substituted, so the model sees the world's block *and* the scene's, with one sentence
  resolving the precedence. That is a deliberate trade for the prompt cache, and whether a
  small model actually honours the precedence line is unmeasured.
- **The no-counts regex is broad.** `agents/style_agent._COUNT` drops any block matching a
  quantity + unit, which will occasionally drop an innocent sentence ("she waits three beats
  before answering" is prose about a character, not an instruction). Dropping one block is
  cheap and the author can rewrite it, but a false positive is silent apart from a log line.
- **Presets are not versioned.** Editing a saved preset does not touch worlds already using
  it — by design — but there is no way to see which worlds were seeded from which preset, or
  to re-apply an updated one.
