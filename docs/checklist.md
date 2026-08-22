# Mytheca — Checklist

**Genuinely open work only.** Completed work is not tracked here — every shipped feature has a plan under `docs/plans/` and a commit series in git history. This file was previously a 742-line append-only log whose "next steps" section had gone stale enough to contradict its own completed entries (it still listed the NDJSON stream, the validator, and the vector DB as unbuilt long after all three shipped). It is now kept short on purpose.

Verified against the code on 2026-08-04.

## Undesigned decisions

| Decision | State |
| --- | --- |
| **Auth mechanism** | Completely undesigned. There is no `User` model, no auth routes, and no session or token handling anywhere in `web/backend/app/`. JWT-vs-cookie, provider, and whether the app becomes multi-tenant at all are open. Everything downstream — protected routes, per-user libraries, admin surfaces — is blocked on this. |
| ~~**Stat lifecycle across scenarios**~~ | **Decided 2026-08-21 (owner decision D-1): reset, with an opt-in carry.** Stat *values* are scoped to a play-through (`session_character_stats`); `character_stats` holds the character's **authored** starting value and is what every new play-through begins from. `StatDefinition.carry_over` decides whether a play-through's ending value writes back onto the character when the session closes — so a stat carries between scenes only when it says so. Two play-throughs of one scenario no longer share a value, which is what makes branch and rewind correct. **Still open:** how a `hidden`-visibility stat should render is untouched by this and remains undecided (see `docs/plans/depth-for-players.md`). |
| **Deployment target** | Undecided: containerized full-stack on one host vs. split hosting. Nothing is configured. |

## Unbuilt capabilities

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
- **A standing direction never expires.** What a turn could not deliver is carried forward
  indefinitely until it lands or the player dismisses it (`play_sessions.standing_direction`).
  A direction the scene has quietly moved past will keep being re-owed, and the only remedy is
  the dismiss control. A turn-count or relevance-based expiry was not designed.
- **`@` mentions have no inline chip.** The composer's tagged row shows what a turn will
  carry, but inside the textarea an `@name` is plain text — there is no styled token, because
  a `<textarea>` cannot hold one. Doing it properly means a contenteditable or an overlay, and
  both were judged too large for `docs/plans/steering-the-scene.md`.
- **Graph edges from a rewound turn are not rolled back.** `session_state.truncate_session`
  prunes the `:Event` node each cut turn wrote (deterministic id `evt_{session_id}_{turn_seq}`),
  but the relationship **edges** and `:Consequence` nodes those turns wrote stay. The graph is a
  best-effort accumulator with no per-turn provenance index, and adding one was out of scope for
  `docs/plans/control-over-the-record.md`. The effect is that a rewound scene can leave a
  relationship the transcript no longer explains. Fixing it means recording the turn seq on every
  edge write in `graph_writer` and deleting by it.

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
- **The in-voice penalties were removed against a drift risk nobody measured.** `frequency_penalty`/`presence_penalty` are now `0.0` on every register because EXP-2026-08-007 showed they were what destroyed sentence structure (1.32 ± 1.16 vs 11.42 ± 3.96 sentences per 100 words, no arm overlap). They had been added to fight **in-character drift**, and that experiment does not measure drift at all — so the trade was taken on one side of the ledger only. The `_REGISTER_SAMPLER` column is kept at zero rather than deleted so a measurement can put something back. What is needed is a drift eval (repetition of a character's own phrasings across a long session, or blinded speaker-attribution) run with the penalties off and on; until it exists, "removing them costs nothing" is an assumption, not a finding.
- **The sampler finding is one model deep.** EXP-2026-08-007 ran entirely on upstream `qwen38-27B-awq`. The endpoint has since served `gemma4-26B-mtp`, on which only the *shipped* configuration has been observed (EXP-2026-08-008) — the arms have never been re-run there. Reconsidering the penalties on a different model means re-running that experiment, not extrapolating.
- **Composure as a stat, and a tonal redo pass** — the two rejected arms of the same design (ideas 4 and 6). The stat machinery already renders bands to prose; the beat-redo seam that used to live on the continuity guard went with it, so a tonal redo would now need its own. Both are cheap enough to revisit if the register alone proves insufficient.
- **YAML config loaders** in `app/content/` — only the Markdown stat-guidance loader exists. Entities live in Postgres, so this may simply be unnecessary; decide rather than leave it pending.
- **Dice-based resolution** — explicitly dropped (decision D11), not merely deferred. The `CheckCard` renderer was removed. Reopen only as a deliberate reversal.

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

- **Dead code on the turn path.** `director_agent.who_is_up` and `director_agent.rerank` are the superseded one-shot speaker picker, called only from `utils/tests/backend/agents/test_director_agent.py`. Their prompt keys (`director.who_is_up`, `director.rerank`) remain editable through Options → Prompts, where they silently do nothing. Decide: delete both, or hide the keys.
- **Stale module docstrings elsewhere in the tree.** The three worst offenders were corrected on 2026-08-04 (`services/turn_engine.py` described a "P3 single speaker / `_pick_speaker`" design that no longer exists, `main.py` said the brain and event stream were "added in later phases", and `graph_writer.py` called the edge/consequence writer unused machinery). Other modules have not been swept — treat any "this phase…" docstring as suspect until verified.
- **`TurnContext.subgraph` is fetched but unused.** The scenario subgraph is assembled every turn; its only consumer is a boolean `available` flag in the diagnostic trace. The graph reaches the model solely via `graph_reader.relationship_context()`. Either render the subgraph into the prompt or stop assembling it.
- **Unused graph queries.** `graph_reader.presence_casting` and `graph_reader.secret_reachability` have no callers.
- **`validate_relationship` substring fallback** will mis-bind on nested cast names ("Aldous" vs "Brother Aldous").
- ~~**Two frontend tests are load-flaky.**~~ **Fixed 2026-08-21.** `CharacterModal` already
  carried a trailing 15 s timeout; the two that did not — `SettingModal` ("drafts a full setting
  from a seed into the form") and `ToastProvider` ("holds the auto-dismiss timer") — now take an
  explicit **15 s per-test budget** instead of Vitest's 5 s default. That is the prescribed fix,
  with the assertions untouched. Both were re-confirmed failing at load average ~47 (an unrelated
  job on the machine) and pass there with the raised budget.
  **The remaining constraint is the runner, not the tests:** on a loaded machine the *full* suite
  needs `--maxWorkers=2`. At `--maxWorkers=4` under load ~47 a *different* test timed out on each
  run (`LibraryView.editors`, then `ToastProvider`), which is contention, not a defect — the same
  suite passed 876/876 at `--maxWorkers=2` under identical load.
- ~~**A third: `components/layout/ToastProvider.test.tsx`**~~ **Fixed 2026-08-21.** It was
  not the 3 s auto-dismiss: the dismissal fires under *fake* timers, and what the test then
  waited for was the exit animation completing under *real* ones, against `waitFor`'s
  default 1 s budget. Under CPU contention that is not enough — it failed on every full-suite
  run once this branch added five tests, and passed 850/850 at `--maxWorkers=4`. The final
  `waitFor` now gets 5 s; the assertion is untouched. **The two library-modal flakes above
  are still open** and want the same treatment.
- **Ollama is still not *detected*, though it is no longer uncapped.** `LOCAL_LLM_BASE_URL` defaults to `http://localhost:11434` — Ollama's port — and `services/llm_backend.py` probes only vLLM (`GET /version`), llama.cpp (`GET /props`), and relays that name an upstream in `GET /models`. Ollama matches none, so it reports as `unknown`; since 2026-08-19 an unknown endpoint receives **both** engine budget keys, so the thinking budget is at least attempted. Whether Ollama honours either key is unverified — a native probe (`GET /api/tags`) and its own budget key remain unbuilt.
- **`web/shared/contracts/` is empty** while both layers hand-maintain their own copy of the event contract. Either populate it or drop the directory and document the manual mirror as the intended design.
- **`sr-only` inside a clipping container is a repo-wide latent bug.** Tailwind's
  `sr-only` is `position: absolute`; with no positioned ancestor its containing block is
  the *initial* containing block, so it is **not** clipped by an `overflow: hidden`
  ancestor and instead grows the **root** scroller. `TriagePanel`'s doc list hit this
  hard (6212px of blank page below the fold for 28 files) and was fixed on 2026-08-11 by
  making the scroller `relative`. **The rest of the tree has not been swept** — any
  `sr-only` (or other absolutely-positioned) element inside a long scrolling list within
  a `h-dvh`/`overflow-hidden` shell can reproduce it. The symptom is
  `documentElement.scrollHeight > clientHeight` while `document.body` is viewport-sized.
- **The context rail is very cramped below `lg`.** With the rails stacked, `TriagePanel`'s
  sticky header (upload target + drop zone + Triage button) consumes almost the whole
  `42dvh` strip, leaving the doc list ~34px of scroll at 320×720 and 375×812 (134px at
  768). Functional — the list scrolls and the page does not overflow — but poor; part of
  the unbuilt mobile-drawer work under *Known UI limitations*.
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
- **Core Web Vitals have never been measured.** `docs/plans/frontend-polish-acceptance.md`
  records this as the one outright **FAIL** against the polish spec's §14. The *causes* of
  layout shift were addressed structurally on 2026-08-12 (space-reserved images via
  `SmartImage`, a reserved error line in `FieldError`, a min-height on the streaming beat,
  skeletons matching real card geometry), but CLS / INP / LCP were not measured — `next build`
  cannot run without network access to Google Fonts, so there is no production bundle to
  profile. Needs one Lighthouse run on a 4× throttled CPU in a networked environment.
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

- **The `VoiceSamplesEditor` Moment select has not been seen in a browser.** Added 2026-08-11. Verified by co-located component tests (native `<select>`, `<label>`-associated, reachable by accessible name, reuses the existing field styling) and by structural review: the row wraps at the 320px floor and the select is `max-w-full min-w-0` so a long option label cannot overflow. A live check was attempted in the worktree on a free port and **failed for an unrelated reason** — `next/font/google` cannot reach Google Fonts in this sandbox, so the page never renders. Folded into the consolidated pass below.
- **Live in-browser accessibility + responsive pass.** Deferred across a long series of UI changes against a persistent environment constraint: a dev server holding 3346, backend CORS pinned to that origin, unreachable Google Fonts, and unreliable screenshot tooling inside worktrees. Each change was instead verified via green component suites, `next build`, and structural review (native controls, AA tokens, reduced-motion fallbacks).
  - **Substantially closed on 2026-08-12** by the frontend-polish pass
    (`docs/plans/frontend-polish-ui.md`). The Google-Fonts blocker was worked
    around by temporarily shimming `lib/fonts.ts` to system families — enough to
    render the app and measure it, reverted before commit. Measured live on
    `/storylines/new` and the story player at **320 / 375 / 768 / 1024**: no
    horizontal page overflow and `documentElement.scrollHeight ==
    clientHeight` at every width (the `sr-only` root-scroll symptom is absent).
    Touch emulation (`pointer: coarse`) found **9 controls under 44px** that no
    per-component sweep had caught; a zero-specificity floor in `motion.css`
    fixes all 9, verified 9 → 0 in the browser. The sticky-bottom transcript was
    confirmed live: scrolling up raises the pill and the position **holds** when
    content grows.
  - **Still not verified live:** screenshots (the browser pane does not
    composite in this environment, so nothing visual was eyeballed), and
    `:focus-visible` rendering (`document.hasFocus()` is false in the pane, so
    the selector never matches). Both were verified structurally instead.
  - *Partially closed on 2026-08-11 for the composer.* The scene-direction box was measured
    live (a throwaway route on a second dev server, so no backend/CORS was involved) at
    320/375/768/1024: no horizontal overflow, no root-scroll growth, the panel grows upward
    with the box capped then scrolling, and tab order reads direction → message → Config →
    Speaking as → dial → Send. **Focus styling could not be seen rendered** — the browser
    pane reports `document.hasFocus() === false` and `visibilityState: "hidden"`, so
    `:focus-visible` never matches and screenshots time out. It was verified by reading the
    served stylesheet instead (`textarea.composer-input:focus-visible` and
    `.focus-within\:border-accent:focus-within` both present and correct).
- **ComfyUI end-to-end render.** The generate → edit → save → reopen loop has never been verified against a running ComfyUI server.
- **Graph node/edge click → detail.** Confirmed by unit tests; could not be driven live because synthetic canvas clicks don't reach `react-force-graph-2d`'s internal hit-testing headlessly.

## Known UI limitations

- Rails are hidden below `lg` (the transcript stays primary); mobile drawers are unbuilt.
  The live **who-is-speaking** signal is no longer lost with them — `TurnStatusStrip` carries
  it in the reading column at every width — but per-character stats, presence controls, and
  the scene-pulse feed are still `lg`-only.
- **The turn-status strip's `ending` phase depends on the engine reaching its end-of-loop
  trace step.** A turn killed by a mid-stream failure jumps straight from its last beat to
  no strip at all (the client's `.finally` reset), so "the turn is ending" is never shown on
  the error path. That is deliberate — the `role="alert"` stream error says more than a
  wind-down label would — but it does mean the phase is not a guaranteed terminal state.
- Graph mode is canvas-only below `lg`; the `sr-only` node/edge table remains the data alternative. Graph node clicks are wired for Character only — other types are hover-tooltip only.
- The storyline switcher is hidden below `md`, so mobile cannot switch worlds.
- **At the 320px floor the scene-header right-hand cluster overflows by 45px.** Measured live
  on 2026-08-22 (viewport 320, cluster right edge 365). It holds, in order: the Chat/Graph
  switch, **Play-throughs**, Export, Theme, Inspector. The page itself does **not** scroll
  horizontally — an `overflow: hidden` ancestor clips it — so the rightmost controls are simply
  unreachable there, the same failure mode as before but larger.
  The budget moved during `docs/plans/control-over-the-record.md`: Phase 2 **reclaimed ~7px** by
  deleting the dead "Narrator active" block, and the same plan then spent it and more by adding
  the Play-throughs tray. `docs/plans/making-it-legible.md` Phase 7 will put a real four-state
  model-health indicator back in the freed slot, so the number will grow again.
  Letting the cluster shrink was tried and is *worse* — its children have intrinsic widths, so a
  squeezed container pushes them 50–150px past the edge instead. **The durable fix and this
  bullet's removal both belong to `docs/plans/reach.md` Phase 4** (the header overflow menu); do
  not close it from another plan. Everything fits at 375+, and the transcript's own beat controls
  meet the 44px touch floor at 320 (verified in the same pass).
- **Scene images still cannot be re-rolled, edited or deleted from the transcript.** The beat
  machinery around them landed — every prose beat now has re-roll, edit, branch and rewind, and
  the take/`activeTake` fields exist on `scene_image` — but the image-specific half did **not**:
  `scene_moment.regenerate_moment`, `DELETE …/beats/{id}` for an image, and the per-image prompt
  edit were cut from `docs/plans/control-over-the-record.md` Phase 9 to keep it to the prose seam.
  An unwanted picture still stays in the beat log. There is also still no way to ask for a
  specific subject — the prompt is written from the scene as it stands.
  Owned by `docs/plans/making-it-legible.md` Phase 11.
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

## Housekeeping

- **11 stale git worktrees** under `.claude/worktrees/`, all registered in `git worktree list`, each 25+ days idle with a merged-looking final commit. Prune them along with the ~45 leftover local branches.
