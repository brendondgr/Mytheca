# Scene Control Density — the config popover, the scene menu, and the presence selects

**Branch:** `claude/config-menu-sizing-layout-09b32b`
**Status:** in progress
**Owner:** frontend chrome (`components/ui/`, `components/feature/`)

## The problem, measured

Not a matter of taste. Measured live in the running app at 1280×720, Slate theme,
default text-size preset, scenario `embergate/salt`:

| Surface | Measurement | Why it is wrong |
| --- | --- | --- |
| `SceneConfigMenu` panel | **996 px of content** in a 264 px-wide, 557 px-tall scroller | Six controls; the player scrolls past ~440 px of hidden content to reach the last one. |
| Its six `<select>`s | `font-size: 16px`, IBM Plex Mono, 36 px tall | 16 px mono in a 221 px field is the single loudest thing on the screen. `--fs-field` is pinned at 16 px to stop iOS auto-zoom — a *mobile* contract that desktop is paying for. |
| Its six labels | 12 px mono, `uppercase`, `tracking: .12em`, **17–52 px tall** | Four of the six wrap. "Follow-up ideas offered after each turn" is **52 px** — four lines of wide-tracked caps, which is the hardest possible way to read a control's name. |
| Its help paragraphs | 12 px EB Garamond, **16–81 px each, 356 px total** | 36 % of the panel is prose nobody reads twice. It belongs on demand, not in flow. |
| `SceneMenu` rows | **71–88 px per row**, 454 px panel | Each row's one-line hint wraps to two or three lines of 12 px mono. Six rows fill the viewport. |
| `CastRail` presence select | `font-mono text-field` = **16 px mono**, full rail width, once per cast member | Same 16 px-everywhere mistake, repeated N times down a narrow rail. This is the "in the scene / unconscious / departed / left / dead" dropdown. |

Three distinct causes, and each needs its own fix:

1. **One font size for every form control at every width.** `--fs-field: 16px` is
   pinned in every preset (`styles/themes.css`) so that focusing a field on an
   iPhone does not trigger Safari's auto-zoom. That is a real constraint **below
   640 px** and no constraint at all above it — exactly the split `--control`
   already makes (44 px → 34 px at `sm`). Form text never took the same split.
2. **Descriptions live in the layout.** Every `SceneControlSelect` renders its
   `help` as a paragraph in flow, and every `SceneMenu` row renders its `hint` the
   same way. Copy that is read once, on first encounter, is charged to every frame
   after that.
3. **Labels are sentences.** The mono/uppercase/`.12em` treatment is the design
   system's label style (`docs/design-system.md` — "Labels / metadata: IBM Plex
   Mono, uppercase, letterspaced"). It is correct for a label and catastrophic for
   a sentence. The fix is to shorten the labels, not to abandon the style.

## What changes

- A **compact form-control size** that respects the iOS floor below `sm` and drops
  to the dense chrome size above it — the `--control` split, applied to type.
- Descriptions move **out of flow and behind an info button**, shown on hover and
  on keyboard focus, dismissible with Escape, while remaining the control's
  `aria-describedby` target so nothing is lost to a screen reader.
- Control labels become **short titles**; the sentence they used to be moves into
  the info tip and into the control's accessible name, so the visible label stays
  a prefix of the accessible name (WCAG 2.5.3, label in name).
- The same compact select reaches `CastRail`'s presence control.

## Gaps and decisions

- **Do we shrink the trigger buttons themselves?** No. `SceneConfigMenu`'s and
  `SceneMenu`'s triggers are already `h-control` (44 px touch / 34 px desktop),
  which is the WCAG 2.5.8 size below `sm` and the design system's dense size above
  it. Shrinking them would break a target-size rule to fix a problem that lives
  inside the panels. **Assumption stated, not asked.**
- **Does the info tip need a portal?** No. The panels are `overflow-y-auto`, so an
  absolutely-positioned tip inside one clips at the panel edge. The tip is placed
  *below* its button and constrained to the panel's own width, which is the one
  geometry that cannot clip horizontally in a 264 px panel.
- **Truncating `SceneMenu` hints loses information visually.** Accepted: the full
  hint stays in `aria-describedby` and in a native `title`, and the label alone
  identifies every row in this menu today.

---

## Phase 1 — A compact form-control size, and an `InfoTip` primitive

**Goal:** the two shared pieces every later phase consumes.

1. `components/ui/Icon.tsx` — add an `info` path on the 24 grid (circle + stem +
   dot), keeping the one-viewBox/one-stroke rule. `ICON_NAMES` picks it up for the
   guard test automatically.
2. `components/ui/Select.tsx` — **new primitive.** A native `<select>` carrying the
   one field chrome the app should have: `text-field sm:text-ui` (16 px below
   `sm`, 13 px above), `font-mono`, field tokens, `focus:border-accent`, sized by
   padding rather than a fixed height. Forwards every native prop. The comment
   states the iOS-zoom reason for the split, because the next person to see
   `text-field sm:text-ui` will otherwise "simplify" it.
3. `components/ui/InfoTip.tsx` — **new primitive.** A 20 px icon button
   (`touch-target-overlay` for the projected 44 px hit area) that reveals its
   content on `pointerenter`, on focus, and on click. WCAG 1.4.13: dismissible
   with Escape, hoverable (the tip is inside the same hover container), persistent
   until dismissed. The visible tip is `aria-hidden`; the same text is rendered
   `sr-only` with the id the caller hands to `aria-describedby`, so the screen
   reader path is unchanged from today's in-flow paragraph.

**Tests (new, co-located):** `Select.test.tsx` — renders options, fires `onChange`
with the native value, disabled state. `InfoTip.test.tsx` — hidden by default,
shown on hover and on focus, Escape dismisses, the described text is in the
accessibility tree at all times. `Icon.test.tsx` — extend the existing name guard.

**Validate:** `npx vitest run components/ui`, `npm run typecheck`, `npm run lint`.
**Commit:** `Mytheca — ui: a compact Select and an InfoTip, sized for the pointer that is actually there`

## Phase 2 — `SceneControlSelect`: title + dropdown + info

**Goal:** the layout the request asks for, without losing a byte of the a11y contract.

1. Rewrite `components/ui/SceneControlSelect.tsx` as: a header row holding
   **title** (mono uppercase, `min-w-0 truncate`, `text-ink` — not `text-mute2`,
   which is the readability half of the complaint) + `InfoTip` + the `action`
   slot (the pin); then the `Select` at full width.
2. New prop `description` — the long copy, which now reaches the reader through
   the `InfoTip` and through `aria-describedby`. `help` is renamed to it rather
   than kept alongside, so there is one way to say this.
3. New prop `accessibleName` — when the visible title is shortened, the select's
   `aria-label` becomes `"<title> — <accessibleName>"`. Visible text stays a
   prefix of the accessible name.
4. `cost` folds into the tip beside the description, as it does today.

**Tests:** extend `SceneControlSelect.test.tsx` — the title renders, the tip is
closed by default, the select keeps an accessible description while closed, the
accessible name contains the visible title, `onChange` still returns the original
(non-stringified) option value.

**Validate:** `npx vitest run components/ui`. **Commit:** `Mytheca — ui: SceneControlSelect becomes title + dropdown + info, not a paragraph per setting`

## Phase 3 — `SceneConfigMenu` relaid out

1. Six short titles, each with the old sentence as its `accessibleName` so the
   existing name-regex tests and screen-reader behaviour both survive:
   `How a turn is built` · `Follow-ups` · `Turn planning` · `How it is written` ·
   `Character history` · `Moment's pitch`.
2. Panel: `p-lg` → `p-md`, `gap-md` → `gap-sm`, `w-[264px] sm:w-[296px]`.
3. `PinToggle` 24 px → 22 px with `touch-target-overlay`, so the projected target
   is 44 px where a coarse pointer exists and the glyph is quiet where it does not.
4. The "What the scene remembers" section keeps its prose — it is a *readout*, not
   a control, and there is nothing to hover for.

**Validate:** `npx vitest run components/feature/SceneConfigMenu`. The live
re-measure is **deferred to Phase 5**, deliberately: the backend only allows CORS
from `http://localhost:3346` (`Settings.frontend_origin`), the owner's own dev
server is already on that port, and taking it over — or restarting the backend
with a wider origin list — would interrupt a running session to read a number
that is just as readable after the merge. Phase 5 measures on the owner's server
once `main` has the change.
**Commit:** `Mytheca — scene: the config popover fits on one screen again`

## Phase 4 — `SceneMenu` rows, and `CastRail` presence

1. `SceneMenu`: the hint becomes one line — `truncate` plus a native `title`
   carrying the full text; the row keeps `px-md py-sm` below `sm` (touch) and
   tightens to `sm:px-sm sm:py-2xs` above it. Row label stays Cinzel `text-label`
   per the design system.
2. `CastRail`'s `PresenceControl` renders the shared `Select`, dropping its
   hand-rolled `font-mono text-field` chrome.

**Validate:** `npx vitest run components/feature/SceneMenu components/feature/CastRail`.
Re-measure: menu rows under 50 px at `sm+`, at or above 44 px below it.
**Commit:** `Mytheca — scene: menu rows and presence selects stop shouting`

## Phase 5 — Gate and docs

1. Full frontend suite, `npm run typecheck`, `npm run lint`.
2. `uv run pytest` (unchanged, but the gate is the gate).
3. `node utils/scripts/check_frontend_css.mjs`.
4. Responsive + a11y pass at 320 / 375 / 768 / 1024: no horizontal overflow, the
   config panel reachable end to end, tips dismissible, focus visible on the new
   info buttons.
5. Docs: `docs/design-system.md` gains the compact-form-control rule and the
   info-tip pattern; `docs/component-map.md` gains `Select` and `InfoTip`;
   `CLAUDE.md`'s primitive count moves 25 → 27.

**Commit:** `Mytheca — docs: the compact form-control split and the info-tip pattern`

## Deliverables

| File | Change |
| --- | --- |
| `web/frontend/components/ui/Icon.tsx` | `info` glyph |
| `web/frontend/components/ui/Select.tsx` | **new** — compact native select |
| `web/frontend/components/ui/InfoTip.tsx` | **new** — hover/focus description |
| `web/frontend/components/ui/SceneControlSelect.tsx` | title + dropdown + info |
| `web/frontend/components/feature/SceneConfigMenu.tsx` | short titles, tighter panel |
| `web/frontend/components/feature/SceneMenu.tsx` | one-line hints, denser rows at `sm+` |
| `web/frontend/components/feature/CastRail.tsx` | presence select → shared `Select` |
| co-located `*.test.tsx` | new + extended |
| `docs/design-system.md`, `docs/component-map.md`, `CLAUDE.md` | the two new rules |
