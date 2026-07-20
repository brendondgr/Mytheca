# Chat Composer Redesign — two-row composer, context dial, exact tokens

## Introduction

The story-player composer currently stacks a **slim full-width context bar**
(`ContextUsageBar`) above a **single-row auto-grow textarea with an embedded
circular Send button** (`Composer`). Scene **Config** lives up in the
`SceneHeader`. The context readouts — both the bar and the config menu's
"Number of beats" estimate — are **char/4 approximations of the visible
transcript only**; they never reflect what the model was *actually* sent (World
Primer, output contract, stat guidance, RAG lore, relationship notes are all
excluded), so they badly under-count.

This plan reworks the composer into the layout in the reference screenshot and
makes the context readout **exact**:

1. **Two-row composer.** Top row = the extendable textarea (as today). Bottom
   row = a controls bar: **Config** on the left (moved down from the header, with
   room reserved for future options), and on the right a **circular fillable
   context dial** immediately left of a **"Send →" pill** button (matching the
   screenshot).
2. **Retire the context bar** (`ContextUsageBar`) in favour of the circular
   dial (`ContextUsageDial`).
3. **Exact token counts.** Capture the LLM's reported `usage.prompt_tokens`
   (the real size of what was sent) from the character-turn call, stream it live,
   and persist it so a resumed scene shows the real last value. The dial shows
   `real used / model max`. The config "Number of beats" readout is recomputed
   from the **actual transcript beats' text** instead of a flat 180-char average.

### Design decisions (locked for this plan)

- **Token source = `usage.prompt_tokens` of the character-turn LLM call.** That
  call carries the largest, most representative context (system = contract +
  stable prefix (primer + stat guidance); user = identity + full transcript +
  act-now). It is the honest "context window used" number.
- **Transport = a persisted `context` trace step**, not a new story-event type
  or a new transport frame. The story player already (a) always requests
  `trace: true`, (b) receives trace frames live in `onFrame`, and (c) reloads
  persisted traces on resume via `getSessionHistory` → `rehydrateFromHistory`.
  Piggy-backing on that mechanism delivers **both live and reload-persistent**
  exact tokens with **no new EventType, no new wire frame, and no Alembic
  migration**. (The Inspector gains a "Context window" step for free.)
- **Reload/pre-first-turn fallback.** Before any turn has streamed (fresh scene,
  or a resumed scene with no persisted `context` step), the dial falls back to
  the existing char/4 heuristic so it always shows *something*; once a real value
  is known it is used verbatim. The dial marks which it is (aria/title) only
  insofar as the number itself changes.
- **Config "Number of beats" readout** stays a client-side estimate (no client
  tokenizer exists) but is computed from the **real text of the last N transcript
  beats** rather than a flat average — content-real, not exact. A true-tokenizer
  readout (via the engine's `/tokenize`) is noted as a deferred follow-up.
- **Send button** becomes a labelled **"Send →" pill** (accent fill) per the
  screenshot, replacing the icon-only circular button. `aria-label="Send"` is
  retained so existing tests and screen readers are unaffected.

### Gaps / assumptions

- Multi-speaker turns make several character calls; the dial reflects the **last
  (or peak) character call this turn** — a single representative number, not a
  per-agent breakdown. Assumed acceptable.
- Endpoints that omit `usage` (rare for vLLM/llama.cpp/OpenAI non-streaming)
  leave `prompt_tokens = None`; the engine simply emits no `context` step and the
  dial keeps the heuristic. No hard failure.
- Live in-browser verification follows the standing worktree precedent (shared
  dir + backend CORS pinned to 3346 + configured-LLM requirement); if a clean
  `preview_start` is not achievable it is deferred and documented, with
  verification via the deterministic suites + typecheck + lint + `next build`.

---

## Phase 1 — Backend: capture exact `prompt_tokens`, emit a `context` trace step

**Files:** `web/backend/app/services/llm.py`,
`web/backend/app/agents/character_turn_agent.py`,
`web/backend/app/services/turn_engine.py`;
tests under `utils/tests/backend/`.

- `llm.py`: add `chat_complete_usage(...) -> tuple[str, int | None]` that runs
  the same request as `chat_complete`, returns `(scrubbed_text, prompt_tokens)`
  where `prompt_tokens = payload["usage"]["prompt_tokens"]` when present, else
  `None`. Refactor `chat_complete` to call it and return only the text (all
  existing callers + `test_llm.py` unchanged). Keep the empty/length error paths
  in the shared helper.
- `character_turn_agent.py`: add `generate_line_with_usage(...) ->
  tuple[str, int | None]` (the current body, using `chat_complete_usage`);
  `generate_line(...)` delegates and returns only the raw string.
- `turn_engine._generate_speaker`: call `generate_line_with_usage` for the
  initial (and, if it runs, the consistency-regen) call; after generation, when
  `prompt_tokens is not None`, `yield from tr.emit("context", "Context window",
  detail=f"{prompt_tokens:,} tokens sent to the model", data={"promptTokens":
  prompt_tokens})`. The step persists via the tracer regardless of the stream
  opt-in (already how `_Tracer` works).
- **Tests:** `test_llm.py` — `chat_complete_usage` returns the parsed
  `prompt_tokens` and `None` when `usage` is absent; `chat_complete` still returns
  text. `test_character_turn_agent.py` — `generate_line_with_usage` surfaces the
  tokens. A turn-engine/play test — a real turn emits a persisted `context` trace
  carrying `promptTokens` (and none when the endpoint omits usage).
- **Validate:** `/home/bdgr/Agents/Mytheca/.venv/bin/python -m pytest
  utils/tests/backend/services/test_llm.py
  utils/tests/backend/agents/test_character_turn_agent.py utils/tests/backend/api
  utils/tests/backend/services -q` (relevant subset), then the full backend suite.
  ruff + mypy on touched files. **Commit** `[Chat Composer Redesign] (1/5)`.

## Phase 2 — Frontend state: consume real tokens (live + on resume)

**Files:** `web/frontend/features/story-player/useScenePlay.ts`,
`web/frontend/features/story-player/turn-stream.ts`; co-located tests.

- `turn-stream.ts`: add `latestContextTokens(traces: PersistedTrace[]): number |
  null` (the last `step === "context"` trace's `data.promptTokens`). Ensure
  `applyActivity`/`applyCharacterActivity` **ignore** the `context` step (no pulse
  spam / no false "thinking").
- `useScenePlay.ts`: new `liveContextTokens` state; in `onFrame`, on
  `frame.type === "trace" && frame.step === "context"` set it from
  `data.promptTokens`. On resume, seed it from `latestContextTokens(history.traces)`.
  Expose `usedTokens = liveContextTokens ?? <existing heuristic>` and a boolean
  `usedTokensExact = liveContextTokens !== null`. Reset on a fresh (unresumed) load.
- **Tests:** a `context` trace frame updates `usedTokens` to the exact value;
  resume seeds it from history traces; a non-`context` trace does not disturb the
  pulse feed.
- **Validate:** `cd web/frontend && npm test -- useScenePlay turn-stream` then
  full frontend suite for the touched files; `npm run typecheck`.
  **Commit** `[Chat Composer Redesign] (2/5)`.

## Phase 3 — Frontend: `ContextUsageDial` (circular) replaces `ContextUsageBar`

**Files:** new
`web/frontend/components/feature/ContextUsageDial.tsx` (+ `.test.tsx`); delete
`ContextUsageBar.tsx` + `ContextUsageBar.test.tsx`.

- `ContextUsageDial`: small SVG ring (`role="progressbar"`, same aria-value*
  attrs + `title`/`aria-valuetext` "X of Y tokens" as the bar). Fill arc
  proportional to `used/max`; stroke colour by the same thresholds (`--success`
  < 50 %, `--gold` 50–75 %, `--danger` ≥ 75 %). Centre shows a compact `K` label
  (`fmtTokensK`). Renders `null` when `maxTokens <= 0`. Motion-reduce safe
  (transition on the arc only, `motion-reduce:transition-none`).
- Port the bar's test assertions (hidden ≤ 0, aria values, colour thresholds,
  K/K title, ≥100 % cap) to the dial's shape.
- **Validate:** `cd web/frontend && npm test -- ContextUsageDial`; `npm run
  typecheck`. **Commit** `[Chat Composer Redesign] (3/5)`.

## Phase 4 — Composer two-row redesign + relocate Config + real-content beats readout

**Files:** `web/frontend/components/feature/Composer.tsx`,
`web/frontend/components/feature/SceneConfigMenu.tsx`,
`web/frontend/components/layout/SceneHeader.tsx`,
`web/frontend/features/story-player/StoryPlayerView.tsx`,
`web/frontend/lib/contextBudget.ts`; co-located tests.

- `contextBudget.ts`: add `beatsTokensFromTexts(texts: string[], beats: number):
  number` (sum `estimateTokens` over the last `beats` of `texts`). Keep
  `estimateBeatsTokens` as the flat fallback.
- `SceneConfigMenu.tsx`: accept an optional `beatTexts?: string[]`; when present,
  the "Number of beats" readout = `beatsTokensFromTexts(beatTexts, contextBeats)`
  (label "≈ N tokens (recent beats)"), else the flat estimate. No behavioural
  change to the controls themselves.
- `Composer.tsx`: rebuild as one panel with **two rows** —
  - **Row 1:** the existing auto-grow textarea (full width; drop the reserved
    right padding / absolute Send).
  - **Row 2:** a controls bar. **Left:** `SceneConfigMenu` (its popover now opens
    **upward**), with the remaining left space blank (future options). **Right
    cluster:** `ContextUsageDial` then the **"Send →" pill** button
    (`aria-label="Send"`, accent fill, disabled while `sendDisabled`).
  - New props: the config props (`maxTurns`/`onMaxTurnsChange`/… /`beatTexts`),
    plus `usedTokens`/`maxContextTokens` for the dial. Enter-to-send / Shift+Enter
    and the type-while-streaming behaviour are preserved.
- `SceneHeader.tsx`: remove the `SceneConfigMenu` render + its config props (now
  owned by the composer). Export/Theme/Narrator/Inspector unchanged.
- `StoryPlayerView.tsx`: stop passing config props to `SceneHeader`; pass them
  (plus `beatTexts` derived from `scene.messages`, `usedTokens`,
  `maxContextTokens`) to `Composer`; remove the standalone `ContextUsageBar`
  block.
- **Tests:** update `Composer.test.tsx` (now renders a Config button + a dial +
  the "Send →" pill; keep the aria-label/Enter/Shift+Enter/streaming cases);
  update `SceneConfigMenu.test.tsx` (content-based readout when `beatTexts` given,
  flat fallback otherwise, upward popover); update `SceneHeader.test.tsx` /
  `StoryPlayerView.test.tsx` (Config no longer in the header; dial present; bar
  gone). Add `contextBudget.test.ts` cases for `beatsTokensFromTexts`.
- **Validate:** full `cd web/frontend && npm test`; `npm run typecheck && npm run
  lint`. **Commit** `[Chat Composer Redesign] (4/5)`.

## Phase 5 — Docs, full validation, a11y/responsive pass, merge to `main`

**Files:** `docs/api-contract.md` (the `context` trace step + `promptTokens`
semantics), `docs/data-flow.md` (exact-token path: capture → trace → live +
resume → dial; config readout from real beats), `docs/design-system.md` (two-row
composer, circular dial states, Send pill, Config relocated to the composer),
`docs/component-map.md` (`ContextUsageDial` new; `ContextUsageBar` removed;
`Composer`/`SceneHeader`/`SceneConfigMenu`/`StoryPlayerView` rows), `CLAUDE.md`
(component list: dial in, bar out), `docs/checklist.md` (this entry). Backend
`docs/*` only where the trace contract is documented.

- **Validate (full gate):** backend `uv run pytest` (or repo-root
  `.venv/bin/python -m pytest`) all green; frontend `npm test` + `npm run
  typecheck` + `npm run lint` + `npm run build` (`next build`) clean.
- **A11y/responsive:** the dial is a labelled `progressbar` with a text title
  (meaning never colour-only); the Send pill + Config button are keyboard
  operable; verify the two-row composer reflows at 320/375/768/1024 and the
  config popover (now upward) stays on-screen. Attempt a live `preview_start`
  pass; if the standing worktree/CORS/LLM constraint blocks it, document the
  deferral per precedent.
- **Merge:** merge `worktree-chat-composer-redesign` into `main`, resolving any
  concurrent drift; re-run the full gate post-merge. **Commit**
  `[Chat Composer Redesign] (5/5)`.

## Deliverables

| Phase | Deliverable | Validation |
| --- | --- | --- |
| 1 | Exact `prompt_tokens` captured + `context` trace step (persisted) | backend pytest subset + full; ruff/mypy |
| 2 | `useScenePlay` consumes real tokens live + on resume | frontend tests (useScenePlay/turn-stream) + tsc |
| 3 | `ContextUsageDial` (circular) replaces `ContextUsageBar` | dial tests + tsc |
| 4 | Two-row composer, Config relocated, real-content beats readout | full frontend tests + tsc + lint |
| 5 | Docs + full gate + a11y/responsive + merge | full backend + frontend gate; merge clean |
