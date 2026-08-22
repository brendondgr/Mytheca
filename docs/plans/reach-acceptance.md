# Reach — Accessibility + Responsive Acceptance

Self-verification for `docs/plans/reach.md` Phase 11, run 2026-08-22 against
`docs/skills/accessibility-mobile/SKILL.md` and `docs/skills/ada-compliance/SKILL.md`.

**Measured live**, in a real browser against the running app at **320 / 375 / 768 / 1024+**,
not read off the JSX. Where a line could not be verified, it says so and is not claimed as a
pass — the same rule `docs/plans/frontend-polish-acceptance.md` holds itself to.

## Summary

**PASS 19 · PARTIAL 3 · FAIL 0 · DEFERRED 1.**

Five defects were found and fixed in this phase: no `<main>` landmark anywhere in the story
player or the Library; a heading tree that went `h1 → h3`; the composer's POV trigger at
**18px wide**; **57** beat controls in the tab order of a twelve-beat transcript; and the
`sr-only` root-scroller symptom's last unverified claim. One WCAG criterion was **unmet and is
now met** (2.1.4, single-character shortcuts).

The three PARTIALs are stated density trade-offs, not omissions. The one DEFERRED line is
`:focus-visible`, which still cannot be observed in this environment.

---

## Landmarks and headings

| Line | Result | Where |
| --- | --- | --- |
| Exactly one main reading region, and it is a landmark | **PASS (fixed here)** | There was **no `<main>` at all** — the transcript sat between two named `<aside>`s with no landmark of its own, so a screen-reader user could jump to either rail by name and not to the thing they were reading. `StoryPlayerView.tsx` now wraps the reading column in `<main>`; `LibraryView.tsx` does the same for its columns. Verified in the tree: `header`, `aside "Cast"`, `main`, `aside "Scene"`. |
| No heading level is skipped | **PASS (fixed here)** | The whole story player exposed **one** heading — the `sr-only <h1>` — and the dossier jumped to `<h3>`. Each rail shell now carries an `sr-only <h2>` (`CastRail.tsx`, `DirectorRail.tsx`, `CharacterDossier.tsx`); the sheet gets its visible `<h2>` from `Drawer`'s `title`, so neither surface doubles up. Measured with a skip detector over `h1…h6`: `h1 → h2 → h2 → h3` with the dossier open, **0 skips**. |
| Both rails are distinguishable in a landmark list | **PASS** | `aria-label="Cast"` / `"Scene"`, added in Phase 2. Two unnamed `complementary` landmarks are indistinguishable; these are not. |
| A closed drawer leaves no orphaned landmark | **PASS** | The `Drawer` is unmounted when closed, and while it animates out it is `aria-hidden`. Measured: exactly one `role="dialog"` in the tree when one sheet replaces another. |

## Keyboard

| Line | Result | Where |
| --- | --- | --- |
| Both drawers trap focus and restore it | **PASS** | `use-focus-trap.ts`, shared with `Modal`. Live at 320: Tab wraps forward and backward across all 7 controls of the Cast sheet, Escape closes and returns focus to the trigger with `aria-expanded="false"`. |
| Every popover closes on Escape and returns focus | **PASS** | `SceneMenu` (Escape steps out of a drilled panel *before* closing the menu), `PlaythroughTray`, `SceneConfigMenu`, `PovSelect`, `StorylineMenu`, `MentionMenu`, `ShortcutSheet`. |
| The per-beat cluster is not hover-gated | **PASS** | Measured at 320 with touch emulation: every control `opacity: 1`, `visibility: visible`, `display: flex`. The `sm:opacity-0` quieting applies only from `sm` up, where a pointer exists. |
| The per-beat cluster is one tab stop | **PASS (fixed here)** | It was **five stops per beat — 57 controls** in the tab order of a twelve-beat transcript, so reaching the composer by keyboard meant passing every edit, re-roll and rewind button in the scene. `BeatControls` is now a `role="toolbar"` with a roving tabindex (the `LibraryTabs` idiom): Tab enters and leaves once, Arrow/Home/End move inside. Rebuilt as a control **list** rather than five conditional blocks, because a hardcoded roving index would assign the tab stop to a control that a beat without `onEdit` never renders — dropping the whole cluster out of the tab order. Four tests cover it, including that case. |
| Each beat control names *which* beat it acts on | **PASS** | "Edit Wren Calloway's beat", "Re-run the whole turn containing Wren Calloway's beat", "Edit your message" — not bare "Edit". |
| Destructive beat actions confirm | **PASS** | Rewind confirms in place and names the count ("Remove 4 beats?"); Branch does not, because it removes nothing. |
| `BeatEditor`'s textarea has a real label and is not covered | **PARTIAL** | The label association is covered by its own suite. Not re-verified live in this pass with a sheet open over it — stated rather than claimed. |
| Single-character shortcuts (WCAG 2.1.4) | **PASS (was unmet; fixed here)** | `/` and `?` are document-wide single-character bindings. The hook already stood down inside editable targets, which is **none of the three things the criterion accepts** — a screen-reader user browsing the transcript is not in a text field, and their AT sends single characters to navigate. Added the "turn off" mechanism: an Options → Appearance switch (`lib/shortcuts.ts`, `hooks/use-shortcuts-enabled.ts`), persisted, reacting in the current tab as well as across tabs. Route-level tests assert `/` works by default and does nothing when off. |

## Touch targets

| Line | Result | Where |
| --- | --- | --- |
| 44×44 on touch | **PASS for height, PARTIAL for width** | At 320 with coarse-pointer emulation, all 106 controls are **44px tall**. 14 are between 24 and 44 wide (`Back to Library` 27, `Scene menu` 26, `Chat` 40, the cast monograms 40, `Got it` 24, the context dial 24). The repo's floor in `motion.css` is deliberately height-only, to protect the dense chrome the design system specifies; those 14 all clear the WCAG floor. Reported, not redesigned, per the plan. |
| 24×24 on touch (WCAG 2.5.8) | **PASS (fixed here)** | Was **1 failure**: the composer's "Speaking as" trigger at **18×44**, because `min-w-0` let it collapse and the global floor sets `min-height` only — so a control could be 44 tall and 18 wide and pass silently. Fixed in both places: `motion.css`'s zero-specificity coarse-pointer floor gained `min-width: 24px` (24, not 44, so it stays a floor and not a mandate), and `PovSelect`'s trigger takes `min-w-[24px]` instead of `min-w-0`, since a zero-specificity rule cannot outrank a utility class. Re-measured: **0 controls under 24×24**. |
| 24×24 with a **mouse** | **PARTIAL — 39 controls, reported not redesigned** | The coarse-pointer floor does not apply to a mouse, and `/storylines/new` at 1280 has 39 controls under 24×24: `TriagePanel`'s `Draft`/`RAG`/`Extract` chips (68×20, 55×20, 65×20), the per-doc category selects (91×23), and five text-buttons across the creator ("↺ New chat" 72×15, "❖ Generate primer" 120×15, "+ Add statistic" 102×15, "Cancel" 45×17, "‹ Library" 507×17). This is the density the design system specifies and the plan explicitly says to report rather than silently change. **One exception was fixed**: `Remove <file>` was **10×24** — a destructive control ten pixels wide, the smallest target on the page — and is now 24×24. |

## Live regions

| Line | Result | Where |
| --- | --- | --- |
| The count is not out of hand | **PASS** | The plan expected seven regions firing in one turn. Measured at 320 with the accessibility tree filtered for hidden ancestors: **3** are live. The two rail-bound ones (`ScenePulse`, `DirectionChecklist`) are inside `display: none` below `lg` and are out of the tree entirely. |
| A drawer-mounted `ScenePulse` does not duplicate `TurnStatusStrip` | **PASS** | With the Scene sheet open at 320, both sheet regions report `aria-live="off"` — the `live` prop from Phase 2 — so the total announcing stays at 3, not 5. |
| `DirectionChecklist` does not announce on drawer open | **PASS** | Same measurement: `aria-live="off"` inside the sheet. A log that reads out a whole turn the instant a sheet opens is worse than silence. |
| Streamed prose is announced once per completed turn | **PARTIAL** | `TranscriptAnnouncer` is designed for exactly this and is covered by its own suite. Not re-verified end-to-end with a screen reader in this pass. |

## Layout

| Line | Result | Where |
| --- | --- | --- |
| No horizontal overflow, no root-scroll growth | **PASS** | `documentElement.scrollWidth === clientWidth` **and** `scrollHeight === clientHeight` measured at 320×720 on the story player (sheet closed and open) and on `/storylines/new` with **28 documents** loaded — the exact case that produced 6212px of blank page before Phase 7. |
| The scene header fits at 320 | **PASS** | `header.scrollWidth === clientWidth === 320`, 0px overflow, down from 17px, with the health indicator inline. |
| The storyline switcher's popover fits at 320 | **PASS** | 12→308 in a 320 viewport, scrolling inside itself rather than running 4912px off the bottom. |
| The document list has usable height at 320 | **PASS** | 34px → **197px**. |
| Reduced motion: nothing becomes invisible | **PASS** | `.drawer-panel/.drawer-backdrop` carry an explicit `prefers-reduced-motion` block beside `.modal-panel`'s. Verified the resting state directly: transitions removed, the sheet is `opacity: 1`, `transform: none`, on screen, focus inside, all controls operable. The base style is the resting state, which is the repo's rule. |
| Contrast | **PASS** | `check_contrast.py` green; no colour token changed in this plan. The new `SceneRailBar` badge uses the already-gated `accent-ink / accent` pair rather than accent-as-text, which would not clear AA at 9px. |

## Deferred

| Line | Result | Where |
| --- | --- | --- |
| `:focus-visible` observed rendered | **DEFERRED — re-recorded, not claimed** | Still unobservable here: the automation pane reports `document.hasFocus() === false` for its own tab, so the selector never matches, and screenshots time out because the pane does not composite frames (verified directly — a bare CSS transition sits at `currentTime: 0` indefinitely). The rules are asserted in source and the focus *order* was verified programmatically, but the rendered ring has still not been seen. Claiming a pass here would be exactly what the polish spec forbids. Remains in `docs/checklist.md`. |
