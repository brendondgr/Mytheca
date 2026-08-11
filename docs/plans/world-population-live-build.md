# World Population — build it in front of the author, and build it whole

## 1. Introduction

The population phase shipped, but it is neither complete nor visible. Three findings
from driving the live app on 2026-08-11:

1. **It builds half a character.** `services/world_populate.py` writes the base draft
   only. The retired "build the whole world" agent produced a `ProposedCharacter` with
   **voice samples** and **proposed starting stats** on top of the draft; the current
   run leaves `voiceSamples: []` and no stat values, so the cast reaches the world
   thinner than it used to.
2. **It happens off-screen.** `BuildWorldModal` closes the moment the author confirms,
   and the only progress is a small line in the create page's sticky footer. Minutes of
   generation look like nothing happening, then the app navigates — which reads exactly
   as "it skipped the build".
3. **It navigates on a truncated stream.** `populateWorld` treats *any* clean end of the
   stream as success. When the stream ends without a `done` frame (observed for real: the
   dev-server reloaded mid-run and dropped the connection at 17 s), the client reported no
   warning and redirected into a half-built world.

Artwork is also opt-in and default-off while ComfyUI is in fact running locally
(`0.28.0`, CUDA) — so the images the author expects are never rendered by default.

This plan makes the dialog the build console: it stays open, shows every step and every
entity as it lands, and only lets the author into the world once the run genuinely
finishes. It also completes the character build (voice + starting stats + portrait) and
defaults artwork on when ComfyUI answers.

## 2. Gaps & Unanswered Questions

- **Navigation on completion.** A clean run auto-enters the new world (that is what the
  author asked for: move on only when everything is built). A run with any failure stays
  open with an explicit *Enter the world anyway* — the world exists, so it must never
  trap them, but it must not silently swallow the failure either.
- **Cancel.** Aborting mid-run leaves a partly-built world (rows already committed). The
  dialog says so rather than pretending to roll back; the author enters and edits.
- **Artwork default.** Probed per-open via the existing `POST /options/comfy/status`, so
  the checkbox defaults on exactly when the render server can answer. No new endpoint.
- **Assumption:** voice samples and starting stats stay best-effort — a character with no
  voice profile is still a character, and a failed proposal must not cost the row.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Build the whole character

- **Locations:** `web/backend/app/services/world_populate.py`;
  `web/backend/app/schemas/world_populate.py` (a `PopulateStatusFrame` per sub-step);
  `utils/tests/backend/services/test_world_populate.py`.
- **Work:** after a character is persisted, run the same two proposals the retired build
  ran, in the same order (voice first, then stats keyed to the world's schema):
  `character_agent.propose_voice_samples` → `crud.update_character`, and
  `character_agent.propose_starting_stats` → `stats.set_character_stats` (skipped with no
  LLM call when the world defines no stats). Each is best-effort with its own status frame
  and its own `error` frame on failure.
- **Rationale:** "populated with the correct information" is the regression — the fields
  the old build filled must be filled again, and per-step frames are what makes the
  dialog legible in phase 3.
- **Validation & commit:** `uv run pytest utils/tests/backend/services`. Commit:
  `[Live World Build] (1/4) Complete: Population fills voice samples and starting stats, not just the base draft.`

### Phase 2 — Truthful stream contract

- **Locations:** `web/frontend/features/library/storylineCreator.ts` (population moves out
  of `commitWorld`), new `web/frontend/features/library/worldBuild.ts` (framework-free
  build state + `foldPopulateFrame`), `web/frontend/features/library/useStorylineCreator.ts`;
  co-located tests + `utils/tests/backend/api/test_storyline_populate.py` unchanged.
- **Work:** `commitWorld` returns to persisting the world/stats/corpus only. A new
  `runPopulate(storylineId, options, onEvent, signal)` owns the stream and — this is the
  fix for finding 3 — a stream that ends without `done` is a **failure**, not a success.
  `useStorylineCreator` exposes `build` state (phase · steps · entities · errors) and a
  `createAndBuild(options)` action that commits then streams, so the dialog can render
  the whole thing.
- **Rationale:** the dialog needs frame-level state, and the truncation bug is in exactly
  the code being replaced.
- **Validation & commit:** `npm test -- features/library`, `npm run typecheck`. Commit:
  `[Live World Build] (2/4) Complete: The build stream drives reviewable state and a truncated run counts as a failure.`

### Phase 3 — The dialog becomes the build console

- **Locations:** `web/frontend/components/feature/BuildWorldModal.tsx` (+ its test),
  `web/frontend/features/library/StorylineCreatorView.tsx`, `docs/component-map.md`.
- **Work:** three phases in one dialog — **ask** (what to build; artwork pre-checked when
  the ComfyUI probe answers), **building** (the live checklist: the current step, each
  character and setting as it lands with its portrait thumbnail, and any non-fatal
  problems), **done** (auto-enter on a clean run; on any failure, stay with a summary and
  *Enter the world anyway*). The dialog cannot be dismissed by backdrop/Escape mid-run —
  only by an explicit Stop. Live region announces each step.
- **Rationale:** the author asked to watch it happen and to move on only when it is done.
- **Validation & commit:** `npm test`, `npm run typecheck && npm run lint`, plus a
  keyboard / focus / contrast / 320-375-768-1024 pass and a live run in the app. Commit:
  `[Live World Build] (3/4) Complete: The Build-world dialog stays open, shows every entity as it lands, and gates the redirect.`

### Phase 4 — Docs + full gate + merge

- **Locations:** `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`,
  `docs/checklist.md`.
- **Validation & commit:** `uv run pytest` + `npm test` + typecheck + lint. Commit:
  `[Live World Build] (4/4) Complete: Documented the live build console and closed the gate.`
  Then merge into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Complete character build | Voice samples + starting stats after the draft | `web/backend/app/services/world_populate.py` |
| Sub-step frames | A status frame per build step | `web/backend/app/schemas/world_populate.py` |
| Build state | Framework-free frame folding + phases | `web/frontend/features/library/worldBuild.ts` |
| Stream runner | Owns the run; truncation = failure | `web/frontend/features/library/storylineCreator.ts` |
| Build console | Ask → building → done, in one dialog | `web/frontend/components/feature/BuildWorldModal.tsx` |
| Backend tests | Voice/stats persistence + best-effort failure | `utils/tests/backend/services/test_world_populate.py` |
| Frontend tests | Folding, truncation, dialog phases, gated redirect | `web/frontend/features/library/worldBuild.test.ts`, `storylineCreator.test.ts`, `components/feature/BuildWorldModal.test.tsx` |
