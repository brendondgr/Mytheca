# Mytheca — Checklist

**Genuinely open work only.** Completed work is not tracked here — every shipped feature has a plan under `docs/plans/` and a commit series in git history. This file was previously a 742-line append-only log whose "next steps" section had gone stale enough to contradict its own completed entries (it still listed the NDJSON stream, the validator, and the vector DB as unbuilt long after all three shipped). It is now kept short on purpose.

Verified against the code on 2026-08-04.

## Undesigned decisions

| Decision | State |
| --- | --- |
| **Auth mechanism** | Completely undesigned. There is no `User` model, no auth routes, and no session or token handling anywhere in `web/backend/app/`. JWT-vs-cookie, provider, and whether the app becomes multi-tenant at all are open. Everything downstream — protected routes, per-user libraries, admin surfaces — is blocked on this. |
| **Stat lifecycle across scenarios** | Undecided: reset / persist / partial carry-over between scenarios, and how `hidden`-visibility stats should render. |
| **Deployment target** | Undecided: containerized full-stack on one host vs. split hosting. Nothing is configured. |

## Unbuilt capabilities

- **Re-running world population on an existing world.** `POST /storylines/{id}/populate/stream` is only wired to the create flow (`BuildWorldModal` → `commitWorld`). A world created before the feature, or one whose population partly failed, has no in-app way to top up its cast — the author adds the rest by hand. The endpoint itself is id-scoped and would work; it needs a Library-side entry point (and a decision about whether it appends to, or dedupes against, the existing roster).
- **Population never proposes scenarios.** It writes characters and settings only (each character whole — draft, voice profile, starting stats, portrait); the first scenario is still authored by hand.
- **World-build runs are in-process and non-durable.** `services/world_populate_runs.py` keeps a run's frame log in memory, keyed by storyline. A backend restart ends the run (the client is told, and never silently rebuilds), and a multi-process deployment would not share the registry. Durable runs (a table + a worker) are unbuilt.
- **A stopped build leaves a partly-built world.** *Stop* aborts the stream but does not roll back the rows already committed, and there is no in-app way to resume the run — the author finishes the cast by hand. Tied to the missing re-run entry point above.
- **The scene direction is not persisted.** `TurnRequest.guidance` shapes the turn it was
  sent with and shows up in the Inspector's `direction` trace steps, but it is not written to
  the `user_turn` row — so a session reload does not restore it into the composer's direction
  box, and an export cannot show what the player asked for versus what the turn delivered.
  The row already carries `data = {text, directedAt, pov}`; adding `guidance` is additive.
- **Nothing verifies that a requirement was actually met.** A beat marks its requirements
  delivered because it *carried* them into the prompt, not because the emitted prose reached
  them (a deliberate call — an LLM "did that happen?" check would roughly double the turn's
  call count). A character that ignores its stated outcome is not caught, and the end-of-turn
  trace will still report the direction delivered in full.
- **A guidance-only turn cannot be sent.** The direction box rides along with a message;
  `validate_turn_inputs` requires `text`, and the optimistic bubble plus the `user_turn` row
  are keyed to it. Steering the scene without also speaking as your character means typing
  something in the message box.
- **A direction longer than the scene's turn cap is compressed, not spread.** The opening
  narration absorbs every narrator-owned requirement at once when `maxTurns` is at or below
  the requirement count, and the last beat collapses to a narrator beat covering whatever
  several characters are still owed. Both are correct — the cap is hard — but they read as
  summary rather than scene. Raising the scene's turn limit is the only remedy today.
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
- **Composure as a stat, and a tonal redo pass** — the two rejected arms of the same design (ideas 4 and 6). The stat machinery already renders bands to prose; the beat-redo seam that used to live on the continuity guard went with it, so a tonal redo would now need its own. Both are cheap enough to revisit if the register alone proves insufficient.
- **`end_scene` / `move_scene` verbs** — the presence/action bus is built to take them.
- **YAML config loaders** in `app/content/` — only the Markdown stat-guidance loader exists. Entities live in Postgres, so this may simply be unnecessary; decide rather than leave it pending.
- **Dice-based resolution** — explicitly dropped (decision D11), not merely deferred. The `CheckCard` renderer was removed. Reopen only as a deliberate reversal.

## Known defects and rough edges

- **The prompt cache is wasted, and it IS worth reclaiming at the configured settings.**
  `character_turn_agent._build_user_prompt` puts the speaker's current stat values,
  register-selected voice samples and recent lines in the HEAD of the user message, ahead
  of the transcript. A prefix cache can only reuse a common prefix, so one stat change
  invalidates everything after it. Measured over a real 10-turn scene (EXP-2026-08-005):
  cached tokens pinned at **exactly 800** — the static system message — while the prompt
  grew 1830 → 4678, hit rate 44 % → 17 %. A short-context comparison found no measurable
  difference (0.59 s vs 0.55 s below 1.5 k tokens), but a long-context one is decisive:
  at 100 / 200 / 400 turns of history (11 k / 22 k / 45 k tokens) reordering cuts
  time-to-first-token by **~40 %** (3.67 → 2.22 s, 7.23 → 4.24 s, 15.47 → 8.98 s) and is
  the only arm reporting any reuse at all (42–48 %). vLLM omits the cache field when the
  hit is zero, so the current layout reporting nothing at every size *is* the measurement:
  **it achieves no reuse whatsoever.** At `contextBeats = 100` a full scene reaches ~20 k
  tokens, squarely in the paying range. The change is still prompt engineering with quality
  consequences — the character sees the same content in a different order — so it wants a
  quality check, not just a latency one. Both layout properties are pinned by
  characterisation tests in `utils/tests/backend/agents/test_character_turn_agent.py`.
- **The beat planner stalls, and a stall costs the player the full generation timeout.**
  Two of ten turns in the post-fix run took 355 s and 272 s, attributed almost entirely to a
  single `plan` call — **300.1 s** (exactly `LLM_GEN_TIMEOUT_SECONDS`) and 240.6 s. Because
  the planner is best-effort, the turn does not error (`failures: 0`); the player simply
  waits five minutes with no indication anything is wrong. Not a context-length effect: the
  same run's largest prompt (6800 tokens) reached first prose in 9.4 s, and a controlled
  sweep to 7355 tokens measured 1.2 s. **The fix is a per-operation timeout** — the planner
  and intent calls are small JSON classifications that normally take 3–5 s, so a 20–30 s
  ceiling would turn a five-minute stall into a hiccup, while prose generation keeps the
  long window it needs.
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
- **The default Reasoning-visibility setting leaves the longest wait empty.**
  The model spends most of a generation deliberating before writing its first word of
  prose: ~17 s of ~20 s on the `local` route (EXP-2026-08-003), and on the deployed
  `skynet` route the first *reasoning* token arrives at ~0.4 s while the first *prose*
  token takes seconds longer (EXP-2026-08-005). The live reasoning channel covers that
  window — but it only streams at `full`, and the default `summary` shows nothing until
  the answer starts, so the status-strip phases are all a default-configured player gets.
  Now that the channel actually works on the deployed model, moving the default is a live
  decision rather than a theoretical one: it trades spoiler risk against a visibly shorter
  wait. Not made yet.

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
- **Two frontend tests are load-flaky.** `features/library/{CharacterModal,SettingModal}.test.tsx`
  → "drafts a full … from a seed into the form" hit Vitest's 5s per-test timeout on a busy
  machine (they wait on the ~150 ms-per-field choreographed reveal). Observed 2026-08-11
  while a dev server, a second backend and ComfyUI were running: ~50% failure at full
  worker concurrency, 0/3 failures with `--maxWorkers=4`. The tests are correct; the
  budget is too tight. Fix by raising the per-test timeout on those two, not by loosening
  the assertions.
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
- At the 320px floor the scene-header Inspector icon clips ~7px. There is no page-level horizontal overflow at any width, and everything fits at 375+. **Re-measured live on 2026-08-12: still exactly 7px, and the button is genuinely unreachable there** (an `overflow: hidden` ancestor clips it). Letting the control cluster shrink was tried and is *worse* — its children have intrinsic widths, so a squeezed container pushes them 50–150px past the edge instead of 7. The real fix is to collapse or overflow-menu some scene-header controls below `sm`, which is a design decision, not a layout tweak.
- **Scene images cannot be regenerated or deleted from the transcript.** The Create image
  control paints a new one each time; an unwanted picture stays in the beat log (it can
  only be removed by deleting the session). No re-roll, no per-image prompt editing, and
  no way to ask for a specific subject — the prompt is written from the scene as it stands.
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

- **The persisted player beat shows no attachment.** `@`-tagged files are visible in the
  composer (chips) before sending and in the Inspector's `Files` step after, but the
  `user_turn` row records only the stripped text, so a resumed scene cannot show which
  files a past turn carried. Rendering an attachment chip on the transcript beat means
  persisting the ids on the event and threading them through `rehydrateFromHistory`.
- **No token accounting for tagged text.** `ContextUsageDial` estimates from the beats and
  the model's reported `prompt_tokens`; up to 12 000 characters of tagged text is not in
  the pre-send estimate, so the dial under-reads until the turn's real usage comes back.

## Housekeeping

- **11 stale git worktrees** under `.claude/worktrees/`, all registered in `git worktree list`, each 25+ days idle with a merged-looking final commit. Prune them along with the ~45 leftover local branches.
