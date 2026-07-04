# Plan: Character Stat Display Fixes (Library + Scene)

## 1. Introduction

Two related user-reported defects: **(A)** on the storyline/Library page, character
cards show no stat values at all beneath a character's name — the author has no
at-a-glance view of a character's starting stats. **(B)** inside a scene, the
Turn Inspector correctly traces every `state_update` (e.g. "Trust +12 → 62"), but
none of the persistent, always-visible surfaces (cast rail, the Director rail's
"Character stats" section) ever reflect that change — a player has to click into
a specific character's Dossier to see anything live, and even that view falls
back to a generic default until *that* character's *that* stat happens to change
during the current session.

Root-cause investigation (two research passes) found the real defects:

1. **`useScenePlay`'s `statsByChar` map starts empty and is only ever populated
   by live/resumed `state_update` events** (`web/frontend/features/story-player/useScenePlay.ts:56`,
   `turn-stream.ts:167-173`). It never seeds from each cast member's actual
   **persisted starting stats** (`CharacterStat` rows, `GET /characters/{id}/stats`,
   `web/backend/app/services/stats.py:132`). So until a stat is touched in *this*
   session, every live display falls back to the storyline's generic schema
   `default` — which reads as "the value never changes" even when the character's
   real starting value differs from the schema default.
2. **`DirectorRail`'s "Character stats" section** (`web/frontend/components/feature/DirectorRail.tsx:241-244`)
   calls `<StatSchema defs={statDefs} />` with **no `values` prop at all** — it is
   not wired to any character, live or otherwise, and always renders the schema
   defaults as a static legend (this is documented as intentional in the
   `StatSchema` doc comment, but it reads to the user as "the values just are not
   changed").
3. **`CastRail`** (`web/frontend/components/feature/CastRail.tsx`) renders each cast
   member's name/role/portrait but **no stat values at all** — there is no
   always-visible "beneath the name" surface in the scene.
4. **`CharacterCard`** (`web/frontend/components/feature/CharacterCard.tsx`) — the
   Library page's character tile — also renders name/role only, no stats.
5. **`ScenarioCarousel`'s `CastStats`** sub-component (the Library hero's per-card
   stat flyout) exists and is wired up, but reads `d.default` (the schema
   default) instead of the character's actual persisted `CharacterStat.value`
   (`web/frontend/components/feature/ScenarioCarousel.tsx:556`) — so it always
   shows the same numbers for every character regardless of their real starting
   stats.

The backend already has everything needed (`CharacterStat` model, `GET`/`PUT
/characters/{id}/stats`, both clamped to the storyline's stat definitions) — this
is a **frontend wiring fix**, with one small addition to `lib/api.ts` to expose the
already-existing `GET` endpoint. No schema/migration changes.

**Decisions (assumptions, stated so they can be corrected):**
- Both the Library `CharacterCard` and the scene's `CastRail` will show a compact
  list of the storyline's **public** stats (`visibility === "public"`, matching
  the existing `StatSchema`/`CastStats` convention) with that character's current
  value, beneath the name/role line.
- The Director rail's un-wired "Character stats" legend is **removed** (not
  fixed-in-place) — it duplicated the same information the (now-live) `CastRail`
  shows per character, and its own doc comment confirms it was only ever a static
  legend, not a bug in isolation. Leaving both an always-static generic legend
  and a correct, live, per-character list next to each other would be more
  confusing, not less. The "Scene state" (`StateChips`, global deltas) and
  "Relationships" sections of `DirectorRail` are untouched.
- Values shown fall back to the storyline's stat schema `default` whenever a
  character has no explicit value on record for that key — this already matches
  the backend's own semantics (`get_character_stats` only returns rows that were
  ever explicitly set) and the existing dossier convention.

---

## 2. Gaps & Unanswered Questions

- **Simple gap:** how many public stats a storyline typically defines, and
  whether a compact per-card list will overflow the tall 2:3 `CharacterCard`
  tile. Assumption: cap the rendered list at all `public` stats (typically a
  handful, matching the existing `CastStats` flyout which renders the same set
  with no cap) using a small mono row list; if a storyline defines an unusually
  large stat schema the list scrolls/wraps rather than breaking the layout — no
  new cap is introduced beyond what `StatSchema`/`CastStats` already do.
- **Simple gap:** whether to batch-fetch every cast/library character's stats
  with `Promise.all` (N requests) vs. a bulk endpoint. Assumption: reuse the
  existing per-character `GET /characters/{id}/stats` endpoint via `Promise.all`
  — cast/library lists are small (a handful to a few dozen), matching the
  existing `Promise.all` pattern already used in `useSceneData.ts`. A bulk
  endpoint is not introduced (out of scope, no evidence it's needed yet).
- No complex/ambiguous gaps requiring human input were found — the two research
  passes traced every relevant read/write path and the fix is a bounded,
  mechanical wiring correction. Proceeding directly.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — `lib/api.ts`: expose the existing `GET /characters/{id}/stats` endpoint

- **Locations:** `web/frontend/lib/api.ts` (near the existing `setCharacterStats`,
  ~line 386).
- **Rationale:** The backend route already exists
  (`web/backend/app/routes/stats.py:41-43`, `services/stats.py:132`) and returns
  `dict[str, int]`, but no frontend wrapper reads it — every subsequent phase
  needs it.
- **Action:** Add `export function getCharacterStats(characterId: string):
  Promise<Record<string, number>>` calling `GET /characters/{id}/stats`,
  mirroring the existing `setCharacterStats` request shape/error handling. Add a
  matching entry to the shared `lib/api-mock` (or wherever `setCharacterStats` is
  mocked for tests) if one exists.
- **Validation & Commit:** `cd web/frontend && npm run typecheck`. Commit:
  `[Character Stat Display Fixes] (1/6) Complete: added getCharacterStats API wrapper.`

### Phase 2 — Seed live scene stats from each character's persisted starting values

- **Locations:** `web/frontend/features/story-player/turn-stream.ts`
  (`rehydrateFromHistory`, `applyStatByChar`), `web/frontend/features/story-player/useScenePlay.ts`
  (the session-resume `useEffect`, ~lines 105-126).
- **Rationale:** This is the actual "values just are not changed" bug — the live
  per-character map must start from each cast member's real persisted stats, not
  an empty map that only fills in as events happen to fire.
- **Action:**
  - `turn-stream.ts`: give `rehydrateFromHistory` an optional third parameter
    `initialStatsByChar: Record<string, StatChip[]> = {}` used as the starting
    accumulator for `statsByChar` (instead of the hardcoded `{}`), so persisted
    session events layer their changes on top of a supplied baseline instead of
    replacing it.
  - `useScenePlay.ts`: merge the existing "resume most-recent session" effect and
    a new baseline-fetch step into one sequential async flow: (1) `Promise.all`
    over `scenario.cast` calling `getCharacterStats(c.id)` (best-effort — a
    failed fetch for one character resolves to `{}`, never blocks the others);
    fold each returned `{key: value}` map into a `StatChip[]`-shaped baseline via
    the existing `applyStatByChar` (treat each entry as a synthetic
    `StatPatch{characterId, key, value, reason: null}`); `setStatsByChar(base)`.
    (2) *then* run the existing `listPlaySessions` → `getSessionHistory` →
    `rehydrateFromHistory(events, traces, base)` resume flow so persisted deltas
    apply on top of the baseline rather than starting from empty. Both steps stay
    best-effort (fetch failure → keep whatever baseline/empty state exists; no
    thrown error reaches the UI).
- **Validation & Commit:** `cd web/frontend && npm test -- turn-stream useScenePlay`
  plus `npm run typecheck`. New/updated tests: `turn-stream.test.ts`
  (`rehydrateFromHistory` honors a non-empty `initialStatsByChar`, persisted
  deltas override baseline entries by key, untouched baseline entries survive),
  `useScenePlay` hook test (baseline stats fetched and seeded before any turn;
  a resumed session's persisted deltas layer on top of, not replace, the
  baseline; a failed baseline fetch degrades to the pre-existing empty-map
  behavior). Commit: `[Character Stat Display Fixes] (2/6) Complete: seeded live per-character stats from persisted starting values.`

### Phase 3 — `CastRail`: live per-character stats beneath each name

- **Locations:** `web/frontend/components/feature/CastRail.tsx` (`CastMemberRow`,
  `CastRail`), `web/frontend/components/feature/DirectorRail.tsx` (export the
  existing `liveValueFor` helper so it isn't duplicated), `web/frontend/features/story-player/StoryPlayerView.tsx`
  (wiring, ~lines 88-96, 162-169).
- **Rationale:** This is the "beneath their names" always-visible in-scene stat
  surface the user asked for, now that Phase 2 makes the underlying data correct
  and live.
- **Action:**
  - `DirectorRail.tsx`: export `liveValueFor` (rename/keep as-is, just add
    `export`) so both the Dossier's `StatSchema` and the new `CastRail` rows use
    one matching implementation.
  - `CastRail.tsx`: `CastMemberRow` takes new optional props `statDefs:
    StatDefinition[]` and `values?: StatChip[]` (that character's
    `statsByChar[c.id]`); renders a compact list of `visibility === "public"`
    stats (filtered by `appliesTo` the same way `CastStats` does) as small
    `label value` rows beneath the existing role `Eyebrow`, using
    `liveValueFor(def, values) ?? def.default` for each. Top-level `CastRail`
    takes `statDefs: StatDefinition[]` and `statsByChar: Record<string,
    StatChip[]>` and threads `statDefs` + `statsByChar[c.id]` into each row.
  - `StoryPlayerView.tsx`: pass `statDefs={statDefs}` and
    `statsByChar={scene.statsByChar}` into `<CastRail>`.
  - Remove the now-redundant "Character stats" section from `DirectorRail`
    (lines ~241-244) and drop the `statDefs` prop from `DirectorRail`'s own
    signature (no longer used there) — `StoryPlayerView` stops passing
    `statDefs` to `DirectorRail` (still passes it to `CharacterDossier`,
    unchanged).
- **Validation & Commit:** `cd web/frontend && npm test -- CastRail DirectorRail StoryPlayerView`,
  `npm run typecheck`, `npm run lint`. Updated/new tests: `CastRail.test.tsx`
  (public stats render beneath a cast member's name; a live `statsByChar` value
  overrides the schema default; non-public stats omitted; renders with no
  `statDefs`/`values` unaffected — existing tests updated for the new props),
  `DirectorRail.test.tsx` (the "Character stats" heading/section no longer
  renders; "Scene state"/"Relationships" still do), `StoryPlayerView.test.tsx`
  (statDefs/statsByChar reach `CastRail`). Also run an accessibility + responsive
  pass (`docs/skills/accessibility-mobile/SKILL.md` — the new rows are
  non-interactive text, reuse existing AA `--ink-soft`/`--mono` tokens, check
  320/375/768/1024 the rail doesn't overflow/clip). Commit:
  `[Character Stat Display Fixes] (3/6) Complete: live per-character stats in the cast rail; removed the unwired Director-rail legend.`

### Phase 4 — Library: `useLibraryState` fetches per-character persisted stats

- **Locations:** `web/frontend/features/library/useLibraryState.ts` (character
  load, ~lines 142-143; wherever character create/edit/starting-stats-save
  triggers a reload).
- **Rationale:** Both the Library `CharacterCard` grid and the `ScenarioCarousel`
  hero need each character's actual persisted values, not just the schema
  defaults already loaded.
- **Action:** After the active storyline's characters load, `Promise.all` a
  `getCharacterStats(c.id)` call per character (best-effort — a failed fetch for
  one character resolves to `{}`), store the result as
  `statsByCharId: Record<string, Record<string, number>>` state. Re-run this
  fetch (at least for the affected character, or the whole map for simplicity —
  match whatever reload pattern already exists after a character mutation) after
  `CharacterModal` saves (create, edit, or a starting-stats apply via
  `applyStartingStats`/`setCharacterStats`) so the Library reflects a just-edited
  character's new values without a full page reload.
- **Validation & Commit:** `cd web/frontend && npm test -- useLibraryState`,
  `npm run typecheck`. New/updated tests: stats map is fetched and populated
  after characters load; a failed per-character fetch degrades to that
  character being absent from the map (not a thrown error); the map refreshes
  after a character/stats save. Commit:
  `[Character Stat Display Fixes] (4/6) Complete: Library loads each character's persisted stat values.`

### Phase 5 — `CharacterCard` + `ScenarioCarousel`'s `CastStats`: show real values

- **Locations:** `web/frontend/components/feature/CharacterCard.tsx`,
  `web/frontend/components/feature/CharacterColumn.tsx` (props passthrough),
  `web/frontend/components/feature/ScenarioCarousel.tsx` (`CastStats`, ~line
  498-565; threading through `CastCard`/`CastStrip`/`ScenarioCarousel`),
  `web/frontend/features/library/LibraryView.tsx` (wiring `statsByCharId` from
  `useLibraryState` down to both).
- **Rationale:** Closes the Library-side half of the report — stats appear
  beneath each character's name on the storyline page, and the existing
  `CastStats` flyout stops showing the same generic defaults for every
  character.
- **Action:**
  - `CharacterCard.tsx`: new optional props `statDefs?: StatDefinition[]`,
    `statValues?: Record<string, number>`; render a compact list of public
    (+ `appliesTo`-filtered) stats as small rows in the footer band beneath the
    existing name/role, using `statValues?.[d.key] ?? d.default` per stat;
    renders nothing extra when `statDefs` is omitted (back-compat for any other
    caller).
  - `CharacterColumn.tsx`: pass `statDefs`/`statValues={statsByCharId[c.id]}`
    through to each `CharacterCard`.
  - `ScenarioCarousel.tsx`'s `CastStats`: add a `values?: Record<string, number>`
    prop; change the rendered value from `d.default` to `values?.[d.key] ??
    d.default`. Thread `statsByCharId` from `LibraryView` through
    `ScenarioCarousel` → `CastStrip` → `CastCard` → `CastStats` (mirroring how
    `statDefs` is already threaded today).
  - `LibraryView.tsx`: pass the new `statsByCharId` map from `useLibraryState`
    into both the `CharacterColumn` and `ScenarioCarousel` call sites.
- **Validation & Commit:** `cd web/frontend && npm test -- CharacterCard CharacterColumn ScenarioCarousel LibraryView`,
  `npm run typecheck`, `npm run lint`, `npm run build`. New/updated tests:
  `CharacterCard.test.tsx` (renders public stat rows with a real value when
  given; falls back to schema default when a key is missing from
  `statValues`; renders nothing extra without `statDefs`), `ScenarioCarousel.test.tsx`/`CastStats`
  case (shows the passed real value instead of the schema default when
  provided). Also run an accessibility + responsive pass (compact text rows,
  no new interactive elements, check the tall 2:3 card doesn't overflow/clip its
  stat list at 320/375/768/1024). Commit:
  `[Character Stat Display Fixes] (5/6) Complete: Library CharacterCard + carousel CastStats show real per-character stat values.`

### Phase 6 — Docs + full validation + merge

- **Locations:** `docs/data-flow.md` ("Stat Change Flow" section),
  `docs/component-map.md` (`CharacterCard`, `CastRail`, `DirectorRail`,
  `ScenarioCarousel`/`CastStats` rows), `docs/api-contract.md` (note
  `GET /characters/{id}/stats` is now frontend-consumed, if not already
  documented that way), `docs/checklist.md` (new entry for this fix).
- **Rationale:** Required documentation-maintenance step per
  `docs/skills/global-project-rules/SKILL.md` — docs must reflect the same
  change that altered behavior, in the same change.
- **Action:** Update the five files above to describe: baseline-seeded live
  per-character stats (Phase 2), the cast rail as the live "beneath the name"
  scene surface replacing the removed Director-rail legend (Phase 3), and the
  Library `CharacterCard`/`CastStats` now reading real persisted values (Phases
  4-5). Add a `docs/checklist.md` entry summarizing the user report, root
  causes, and the fix (matching the format of existing entries).
- **Validation & Commit:** Full gate: `uv run pytest` (backend — confirm no
  regression; this plan makes no backend code changes), `cd web/frontend && npm
  test && npm run typecheck && npm run lint && npm run build`. Full
  accessibility + responsive pass across the touched surfaces (Library grid,
  scene cast rail, Director rail) at 320/375/768/1024. If working in a
  worktree, merge to `main` here, resolving any conflicts. Commit:
  `[Character Stat Display Fixes] (6/6) Complete: docs + validation + merge.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `getCharacterStats` API wrapper | Frontend client for the existing `GET /characters/{id}/stats` | `web/frontend/lib/api.ts` |
| Baseline-seeded live stats | `statsByChar` starts from persisted starting values, not empty | `web/frontend/features/story-player/useScenePlay.ts`, `turn-stream.ts` |
| Cast rail live stats | Per-character public stat values beneath each cast member's name | `web/frontend/components/feature/CastRail.tsx` |
| Director rail cleanup | Removed the unwired, always-default "Character stats" legend | `web/frontend/components/feature/DirectorRail.tsx` |
| Library stats map | Per-character persisted stat values loaded for the active storyline | `web/frontend/features/library/useLibraryState.ts` |
| `CharacterCard` stats | Public stat values beneath the name on the Library tile | `web/frontend/components/feature/CharacterCard.tsx` |
| `CastStats` real values | Carousel flyout shows real persisted values instead of schema defaults | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Tests | Baseline seeding, resume-merge, cast rail render, Library card render, CastStats real-value | `web/frontend/**/*.test.ts(x)` (co-located) |
| Docs | Stat flow, component map, checklist updated | `docs/data-flow.md`, `docs/component-map.md`, `docs/checklist.md` |
