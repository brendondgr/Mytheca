# Play-Experience Fixes — narrator parsing, combined thought+speech, live dossier stats, richer graph trace

## 1. Introduction

Four independent play-surface defects, fixed in one plan. (1) The **narrator** agent (`narrator_agent.interstitial`) returns the raw model completion with only `.strip()`, so a reasoning model's chain-of-thought and harmony-style channel tokens (`<channel|>`, `*Check:*`, `*Revised:*`) leak into the on-screen narration. (2) A character's hidden **thinking** and spoken **dialogue** render as two separate transcript beats; they should read as one message — the muted thought sitting between the character's name and their spoken line. (3) The **character dossier** (right rail, per-character) shows the storyline's stat schema at its *defaults* and never reflects the live per-character stat changes that stream in as `state_update` events — because the frontend keeps a single global stat list that ignores each event's `characterId`, and the dossier's sliders read `def.default`. (4) The Turn Inspector's **Graph**-tagged trace steps (`commit`, `relationships`) only report a *count*; the user wants to see *what* was written (the actual stat/relationship consequences and seeded edges).

Approach, per Mytheca's architecture: fixes (1) and (4) are backend (`web/backend/app/agents`, `.../services/turn_engine.py`, `.../services/relationships.py`), verified with `pytest`. Fixes (2) and (3) are frontend-only (`web/frontend/features/story-player`, `.../components/feature`), verified with Vitest plus an a11y/responsive reasoning pass. Work happens in a git worktree branched off `main`, commit-per-phase, merged back at the end.

## 2. Gaps & Unanswered Questions

- **Narrator sanitizer scope** *(assumption):* apply the new sanitizer **only in the narrator agent**, not centrally in `llm.chat_complete`. Rationale: the character path already parses by marker (`<type:>`/`<thinking>`) and works; a central strip risks colliding with the app's own `<thinking>` tag. The sanitizer lives as a **shared, tested helper** in `agents/_common.py` so it can be reused later if leaks surface elsewhere.
- **Channel-token format** *(assumption):* the leaked `<channel|>` is a harmony-style channel marker (with/without the leading pipe). The sanitizer keeps only the text after the **last** channel marker and strips residual harmony control tokens (`channel`/`message`/`start`/`end`/`return`/`analysis`/`final`, pipe-delimited), never the app tags. Unit-tested against the exact reported example.
- **Stats surface** *(resolved with user):* fix the **character dossier** only. The Director rail's "Character stats" sliders stay a static schema legend (live deltas already show in its "Scene state" chips, by existing design).
- **Graph trace** *(resolved with user):* **enrich the detail** of the existing `commit`/`relationships` steps (list the real consequences/edges); do **not** build a graph visualization widget.
- **`state_update` value semantics** *(assumption):* the validator emits an absolute clamped `value` on each `StatPatch` (existing `applyStatUpdate` already relies on this); the dossier reads `value` and falls back to the schema default when a stat hasn't moved yet.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Narrator output sanitizer (backend)

- **Locations:** `web/backend/app/agents/_common.py` (new `strip_reasoning`/`strip_channels` helper), `web/backend/app/agents/narrator_agent.py` (`interstitial`, apply the helper to `text` before returning), `utils/tests/backend/agents/test_narrator_agent.py` (extend), plus a focused helper test (`utils/tests/backend/agents/test_common.py` or a new `test_reasoning_sanitizer.py`).
- **Rationale:** The narrator is the only freeform-prose agent with no marker parsing, so reasoning leaks straight to the transcript. A dedicated, unit-tested sanitizer is the smallest correct fix and keeps the character/emission path untouched.
- **Details:** helper handles (a) final-channel extraction (take text after the last `<|channel|>`/`<channel|>`-style marker, dropping any `analysis`/`final`/`<|message|>` label), (b) stripping residual harmony control tokens, (c) a no-marker input returns unchanged/trimmed. Add fixtures: the exact reported example → expect only the final revised paragraph; a clean paragraph → unchanged; empty/whitespace → `None` (narrator skip preserved).
- **Action:** Run `uv run pytest utils/tests/backend/agents/` (ruff + mypy on touched files). Once green, commit: `[Play-Experience Fixes] (1/5) Complete: Sanitize narrator output — strip reasoning/channel leakage.`

### Phase 2 — Combine character thinking + speech into one beat (frontend)

- **Locations:** `web/frontend/features/story-player/scene-data.ts` (`SceneMessage`: add `thought?: string`; drop the standalone `"thought"` kind usage), `web/frontend/features/story-player/turn-stream.ts` (`mergeFrame`: fold `internal_thought` into the same-speaker `char` beat), `web/frontend/components/feature/TranscriptBeat.tsx` (`CharacterMessage`: render `thought` between name and dialogue, muted/smaller; remove `ThoughtBubble` routing), `web/frontend/features/story-player/turn-stream.test.ts` and `web/frontend/components/feature/TranscriptBeat.test.tsx` (update).
- **Rationale:** Backend emits `internal_thought` before the speaker's `character_action`/`character_dialogue`, so a single `char` beat can carry thought → action → text using the same "merge into the open same-speaker beat" pattern that already merges action+dialogue.
- **Details:** `mergeFrame` — on `internal_thought`, attach to the last open `char` beat of that speaker (else push a new `char` beat with `thought`); generalize the action/dialogue "merge into the open beat" condition so it also merges into a thought-only beat (open = same `who`, `text === undefined`). Rendering — thought uses the muted, slightly-smaller treatment (reuse the existing `text-ink-soft`/dashed idiom from `ThoughtBubble`), placed above the dialogue bubble inside `CharacterMessage`; a thought with no dialogue still renders (thought only).
- **Action:** Run `cd web/frontend && npm test` (turn-stream + TranscriptBeat) + `npm run typecheck && npm run lint`; a11y/responsive reasoning pass (muted thought keeps AA contrast via `text-ink-soft`; no new interactive elements). Commit: `[Play-Experience Fixes] (2/5) Complete: Merge character thinking + speech into one transcript beat.`

### Phase 3 — Live per-character stats in the dossier (frontend)

- **Locations:** `web/frontend/features/story-player/turn-stream.ts` (new `applyStatByChar` keyed by `stat.characterId`, reusing `applyStatUpdate`), `web/frontend/features/story-player/useScenePlay.ts` (new `statsByChar` state updated in the `state_update` branch; expose it), `web/frontend/components/feature/DirectorRail.tsx` (`StatSchema`/`StatSlider`/`bandLabelFor` accept optional live `values` and render the current value + band + thumb, falling back to `def.default`), `web/frontend/components/feature/CharacterDossier.tsx` (accept + pass the character's live stats into `StatSchema`), `web/frontend/features/story-player/StoryPlayerView.tsx` (thread `statsByChar[profileChar.id]` into `CharacterDossier`). Tests: `turn-stream.test.ts`, `DirectorRail.test.tsx`/`CharacterDossier.test.tsx` (add if absent).
- **Rationale:** Root cause is twofold — global stat state discards `characterId`, and the dossier's sliders hardcode `def.default`. Keying stats per character and making the slider value-aware fixes both without disturbing the Director rail's existing global "Scene state" chips.
- **Details:** `StatSlider` computes `value = liveValue ?? def.default` and derives `pct`, floating readout, and band from it; keep it read-only. `StatSchema` maps each visible `def` to its live `StatChip` by matching `chip.label`/`def.key` (same casing rule as `applyStatUpdate`). Director rail keeps calling `StatSchema` without `values` (unchanged legend). Verify the `state_update` handler updates both the existing global `stats` (rail chips) and the new `statsByChar` (dossier).
- **Action:** Run `cd web/frontend && npm test` + `npm run typecheck && npm run lint`; a11y/responsive reasoning pass (slider stays a labeled read-only visual; live value announced via existing markup). Commit: `[Play-Experience Fixes] (3/5) Complete: Character dossier stats update live per character.`

### Phase 4 — Enrich Graph trace detail (backend)

- **Locations:** `web/backend/app/services/relationships.py` (`ensure_seeded` returns the seeded edge summaries, e.g. `list[str]` of `"A <type> B — reason"`, not just a count — keep best-effort `[]`), `web/backend/app/services/turn_engine.py` (the `commit` trace `detail` lists each `Consequence.summary`; the `relationships` trace `detail` lists the seeded edges from the new return; titles keep their counts via `len(...)`), tests in `utils/tests/backend/services/test_relationships.py` and `utils/tests/backend/api/test_play_turn.py` (assert the enriched detail/summaries appear).
- **Rationale:** Each `Consequence` already carries a human `summary` (`"Suspicion +2: reason"`, `"Maerin trusts Wren: reason"`); `ensure_seeded` already builds edges with `reason`. Surfacing them turns the Graph steps from a bare count into an audit of what the graph actually wrote — exactly the visibility asked for — with no schema, endpoint, or frontend change (the Inspector already renders `detail`).
- **Action:** Run `uv run pytest utils/tests/backend/services/ utils/tests/backend/api/test_play_turn.py` (ruff + mypy on touched files). Commit: `[Play-Experience Fixes] (4/5) Complete: Graph trace steps list the real consequences + seeded edges.`

### Phase 5 — Docs, full validation, merge

- **Locations:** `docs/data-flow.md` (narrator sanitization; combined thought+speech beat; per-character dossier stats; enriched graph trace), `docs/api-contract.md` (note the narration prose is sanitized; `internal_thought` now renders inline with the speaker), `docs/design-system.md` (combined thought+speech beat treatment; live dossier stat sliders), `docs/documentation.md` (status line), `docs/checklist.md` (new completed entry), plus this plan file.
- **Rationale:** Docs must move in the same change (global rules). Then run the full gate and merge the worktree to `main`.
- **Action:** Run the **full** suites — `uv run pytest` and `cd web/frontend && npm test && npm run typecheck && npm run lint` (+ `next build` if the worktree build seam is set up per the frontend-worktree memo). Record counts in the checklist. Merge the worktree into `main`, resolving any conflicts, and re-run the gate post-merge. Commit: `[Play-Experience Fixes] (5/5) Complete: Docs, full validation, merge to main.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Reasoning sanitizer | Shared helper stripping reasoning/channel leakage | `web/backend/app/agents/_common.py` |
| Narrator fix | Sanitized interstitial output | `web/backend/app/agents/narrator_agent.py` |
| Combined beat (data) | `thought` folded into the `char` beat | `web/frontend/features/story-player/scene-data.ts`, `.../turn-stream.ts` |
| Combined beat (UI) | Thought rendered muted between name + dialogue | `web/frontend/components/feature/TranscriptBeat.tsx` |
| Per-character stats | `statsByChar` state + `applyStatByChar` | `web/frontend/features/story-player/useScenePlay.ts`, `.../turn-stream.ts` |
| Value-aware sliders | `StatSchema`/`StatSlider` render live values | `web/frontend/components/feature/DirectorRail.tsx` |
| Live dossier | Dossier shows the character's live stats | `web/frontend/components/feature/CharacterDossier.tsx`, `.../StoryPlayerView.tsx` |
| Richer graph trace | `commit`/`relationships` list real changes | `web/backend/app/services/turn_engine.py`, `.../relationships.py` |
| Backend tests | Sanitizer, narrator, relationships, play-turn | `utils/tests/backend/agents/`, `.../services/`, `.../api/test_play_turn.py` |
| Frontend tests | turn-stream, TranscriptBeat, dossier/rail | `web/frontend/features/story-player/`, `web/frontend/components/feature/` |
| Docs | data-flow, api-contract, design-system, documentation, checklist | `docs/` |
