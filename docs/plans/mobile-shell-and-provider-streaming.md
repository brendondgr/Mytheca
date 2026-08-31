# Mobile Shell & Provider Streaming

**Status:** in progress · started 2026-08-31
**Mode:** B (no worktree) — feature branch off `main`, merged back at the end.

## Why

Two unrelated pieces of work, requested together.

**1. Streaming is not provider-dispatched.** `docs/checklist.md` records this as the
remaining half of the LLM seam: `llm.chat_complete_stream` still parses the OpenAI SSE
dialect inline, so choosing `anthropic`, `gemini` or `ollama` fails the content-type check,
lands in `_NO_STREAM`, and degrades every turn to the blocking path. The Options picker
says so honestly ("· no live typing") — this plan makes the sentence unnecessary.

**2. The mobile chat and library shells are crowded and awkward.** The previous overhaul
fixed *measurable* mobile failures — auto-zoom, contrast, overflow, undersized targets — and
the numbers moved a long way. What it did not do is reduce the number of things on screen.
At 390px the scene header carries a back link, a title, a two-position segmented switch, a
status glyph and a menu; the composer carries three text-labelled control buttons plus a
dial, a ghostwriter and a Send pill; and a third row of Cast/Scene/Knows sits between them.
Every one of those passes its own check and the whole reads as clutter. The owner's report,
verbatim: *"a lot of the buttons and layout look goofy."*

The fix is **subtraction and iconography**, not another round of spacing.

## Gaps & decisions

| Gap | Decision |
| --- | --- |
| "Remove the guide overlay" — mobile only, or everywhere? | **Everywhere.** The owner's words are "it looks terrible and isn't needed". A hint system kept alive for one breakpoint is a maintenance cost with no constituency. `CoachMark`, `use-coach-marks`, `lib/coachMarks` and their tests are deleted outright. |
| "The top bar should contain only back + title" — at every width? | **Below `sm` only.** The section is headed *Mobile UI*, and the same owner said the desktop look is "really nice". Stripping the desktop header would remove the graph view's only entry point to fix a phone problem. Below `sm` the view switch, memory toggle and model status fold into the scene menu, which is where the narrow header already sends everything else. |
| "Icons over text" — drop the labels entirely? | **Labels are `hidden sm:inline`.** The stated reason is "the text doesn't fit", which is a width problem, not a preference for pictograms. Every icon-only control keeps its `aria-label` and `title`, so nothing is lost to a screen reader or to a hovering mouse. |
| "Everything on this page should be vertically centered." | Read as: **the library should scroll as one page on mobile** (the stated core need is "for the page to scroll and move properly"), with the hero's text block vertically centred in its panel rather than top-aligned. The current `h-dvh` + `overflow-hidden` + inner scroller is a desktop layout; below `lg` it becomes a normal document scroll. |
| Carousel: swipe, or keep the transform pager? | **Native scroll-snap at every width.** It gives swipe and click-drag for free, keeps keyboard and trackpad behaviour, and removes a transform pager that no longer has a counter to drive. The chevrons stay at `sm`+ and scroll the track. |
| Which "Recent label on the button"? | The `ScenarioCard` **badge** beside the edit pencil. The hero's "RECENT SCENARIO" eyebrow is a section label, not a button, and stays. |

**Assumption stated rather than asked:** the Options *menu* becoming a link on mobile drops
the quick theme swatches at that width. Nothing is lost — the same control is on
`/options` → Appearance, which is exactly where the icon now goes.

## Phase 1 — Provider-dispatched streaming

Backend only. No UI change beyond copy that stops apologising.

1. `web/backend/app/services/llm_providers/base.py` — confirm the streaming surface on
   `ProviderAdapter` is sufficient (`stream_delta`, `stream_done`, `stop_matches_reasoning`,
   `streaming_dispatched`, and whatever builds a streaming request). Extend it if the four
   dialects need something it does not carry.
2. `web/backend/app/services/llm.py` — `chat_complete_stream` builds its request through
   `active_adapter()` and parses frames through the adapter, instead of hardcoding
   `data:` / `[DONE]` / `choices[0].delta.content`.
3. `stop_is_safe` consults the active adapter's `stop_matches_reasoning` rather than
   applying the openai-compatible rule globally.
4. Flip `streaming_dispatched` to `True` on all four adapters, and remove the
   "· no live typing" branch from `features/options/tabs/LanguageModelsTab.tsx` — the field
   stays on the contract, since a future adapter may not stream.
5. Tests in `utils/tests/backend/services/test_llm_providers.py` (and a new
   `test_llm_stream_dispatch.py` if the file is at its ceiling): one streaming round-trip
   per dialect from a fake transport, asserting the accumulated text, the reasoning channel
   where the dialect has one, usage accounting, and that a mid-stream error surfaces.

**Validation:** `uv run pytest`; `openai-compatible` parity checked against the live
endpoint on :4000 with a real `scene_smoke` turn. **Commit.**

## Phase 2 — One icon set

1. New `web/frontend/components/ui/Icon.tsx` — inline SVG paths on a 24 viewBox, stroked in
   `currentColor`, sized by prop, `aria-hidden` by default. Names needed by the phases
   below: `back` `menu` `send` `write` `undo` `gear` `sliders` `plan` `think` `plus`
   `book` `pencil` `cast` `scene` `knows` `graph` `chat` `image` `chevron-left`
   `chevron-right` `close`.
2. Migrate the existing one-off SVGs (`PlanModeButton`, `ThinkingButton`, `PovSelect`,
   `AppHeader`, `Composer`'s send arrow) onto it. No visual change intended.
3. Co-located `Icon.test.tsx`: every name renders exactly one `<svg>`; the default is
   `aria-hidden`; a `label` prop promotes it to `role="img"`.

**Validation:** `npm test`, `npm run typecheck`, `npm run lint`. **Commit.**

## Phase 3 — Mobile chat shell

1. **Delete the coach marks.** `components/feature/CoachMark.tsx`,
   `hooks/use-coach-marks.ts`, `lib/coachMarks.ts`, both test files, and the three call
   sites in `features/story-player/StoryPlayerView.tsx`.
2. **`components/layout/SceneHeader.tsx`** — below `sm`, the bar is back button, title,
   menu. `ViewModeSwitch`, `ModelStatus` and the memory toggle fold into `SceneMenu` as
   items (the view switch as a two-row radio group via `render`, so it does not read as two
   unrelated commands). The meta subline is `hidden sm:block` — the owner asked for "the
   chat title on its own".
3. **Square chrome buttons.** The back link and the menu trigger become fixed-size squares
   (`h-control w-control`, a new token pinned to the existing scale) with an icon inside,
   expanding to icon + "Library" at `sm`.
4. **Delete `SceneRailBar` from the composer band.** Cast / Scene / Knows move into
   `SceneMenu` as items carrying their counts in the accessible name, exactly as the rail
   bar did. `SceneRailBar.tsx` + its test are deleted; `RailTrigger` moves to `SceneMenu`.
5. **Composer controls become icon-first.** `SceneConfigMenu`, `PlanModeButton`,
   `ThinkingButton`, `PovSelect`, `GhostwriteButton` and Send all render icon-only below
   `sm` (`hidden sm:inline` on the label) with unchanged `aria-label`/`title`.

**Validation:** `npm test`; keyboard pass (tab order through header → menu → composer, no
trap, visible focus); the V1–V8 viewport matrix, 320px and 390px specifically; screenshots
at 390px before/after. **Commit.**

## Phase 4 — Mobile library shell

1. **`components/layout/AppHeader.tsx`** — the storyline switcher gains a book icon; the
   search field stays `hidden sm:flex` as today.
2. **`CreateMenu`** — below `sm` the trigger is a square `+` icon button; the popover is
   unchanged (it already asks what to create). Label returns at `sm`.
3. **`OptionsMenu`** — below `sm` it is a `Link` to `/options` wearing the sliders icon, not
   a dropdown. At `sm`+ the dropdown is unchanged.
4. **`ScenarioCard`** — drop the "Recent" badge; the edit control becomes a square
   `IconButton` inside the card's top-right.
5. **`ScenarioCarousel`** — native scroll-snap track (swipe + drag), `onScroll` syncs the
   featured id, external `index` changes scroll the track. `CastStrip` is `hidden lg:flex`.
   The `1 / 3` counter is deleted; chevrons are `hidden sm:flex`. Hero text block vertically
   centred.
6. **`LibraryView` / `LibraryColumns`** — below `lg` the page is a normal document scroll
   (header sticky) rather than `h-dvh` + inner scroller. The per-column `ColumnChrome`
   heading is `hidden lg:block` below `lg`, since the tab above it already says the same
   word and the same count.

**Validation:** `npm test`; the viewport matrix; a real swipe/drag check in the browser;
screenshots at 390px. **Commit.**

## Phase 5 — Gate, docs, merge

1. `uv run pytest` · `npm test` · `npm run typecheck` · `npm run lint` ·
   `uv run python utils/scripts/check_contrast.py` · `node utils/scripts/check_frontend_css.mjs`.
2. Live verification in the browser at 390 and 1280.
3. Docs in the same change: `docs/component-map.md` (three components deleted, one added),
   `docs/design-system.md` (icon set + any new token), `docs/checklist.md` (the streaming
   entry is retired; anything newly deferred is added), `docs/api-contract.md` if the
   streaming contract's shape changes, `CLAUDE.md`'s facts list where it asserts the
   openai-only streaming path.
4. Merge the branch into `main` with `--no-ff`, delete the branch. **Commit.**

## Deliverables

| Area | Files |
| --- | --- |
| Streaming | `services/llm.py` · `services/llm_providers/{base,openai_compatible,anthropic,gemini,ollama}.py` · `utils/tests/backend/services/test_llm_*.py` · `features/options/tabs/LanguageModelsTab.tsx` |
| Icons | `components/ui/Icon.tsx` + test; migrations in `PlanModeButton` `ThinkingButton` `PovSelect` `AppHeader` `Composer` |
| Chat shell | `components/layout/SceneHeader.tsx` · `components/feature/SceneMenu.tsx` · `components/feature/Composer.tsx` · `features/story-player/StoryPlayerView.tsx` · **deleted:** `CoachMark.tsx` `SceneRailBar.tsx` `hooks/use-coach-marks.ts` `lib/coachMarks.ts` + tests |
| Library shell | `components/layout/AppHeader.tsx` · `CreateMenu.tsx` · `OptionsMenu.tsx` · `ScenarioCard.tsx` · `ScenarioCarousel.tsx` · `features/library/{LibraryView,LibraryColumns}.tsx` |
| Docs | `docs/component-map.md` · `docs/design-system.md` · `docs/checklist.md` · `CLAUDE.md` |
