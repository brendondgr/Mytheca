# Beat controls — a thin bar under the beat, a menu on a phone

## Why

The per-beat record controls (Edit · Re-roll · Re-run the turn · Branch · Rewind) sit
`absolute -top-sm right-0` — *above* the beat, overlapping the beat before it — and draw
themselves with **text glyphs** (`✎ ⟳ ⟲ ⑂ ↺`). Both are defects the icon set already
exists to fix: a glyph inherits the font stack, so it renders differently per platform,
lands at whatever size the type scale gives it, and — for `⟳` vs `⟲` — asks the player to
tell two characters apart that differ by the direction of an arrowhead at 12px.

The take pager is a *second* floating cluster on the opposite edge (`-bottom-sm right-0`),
so a re-rolled beat has controls hanging off two of its corners.

On a phone all five buttons are permanently visible at 44px each — 220px of chrome on
every beat of the transcript, on the narrowest screen in the app. That is the same mistake
`SceneRailBar` was deleted for on 2026-08-31.

## What changes

1. **The icon set gains the five glyphs it was missing**: `reroll` `rerun` `branch`
   `rewind` `more`. Drawn on the one 24 grid at the one stroke weight, like everything
   else in `Icon.tsx`.
2. **One bar, under the beat, at the right.** The take pager and the action cluster share
   a single surface anchored below the beat's bottom-right corner. It is absolutely
   positioned, so revealing it on hover costs no layout shift — a bar that pushed the next
   beat down on mouse-over would make the transcript jump as the pointer crossed it.
3. **Below `sm`, the bar collapses to one `⋯` button** that opens a menu of the same
   actions, each with its icon *and its words*. Nothing is removed: the menu is the same
   action list the toolbar builds, rendered as rows.

## Non-goals

- No new capability. Every action, its confirmation copy and its callback contract are
  unchanged.
- The pager keeps its own component and its own tests; it is composed into the bar, not
  absorbed by it.

## Phases

### Phase 1 — the five icons
`components/ui/Icon.tsx`: add `reroll` `rerun` `branch` `rewind` `more` to `PATHS`.
`more` is drawn as three dots and is the one caller that passes `filled`.
**Validate:** `npm test -- Icon`.

### Phase 2 — `BeatControls`
- Glyphs → `<Icon>`; the control list gains an `icon: IconName`.
- The list is built *above* the confirming branch, because the narrow rendering needs it too.
- `narrow = useMediaQuery("(max-width: 639px)")` — **`false` on the server and under jsdom
  on purpose**: the wide rendering is the superset, so a viewport we do not yet know about
  gets every action present and reachable rather than hidden behind a menu that has not
  been measured.
- Narrow: one `⋯` trigger + a `mytheca-menu mytheca-menu-up` popover of rows. Escape and
  outside-click close it and return focus to the trigger. Rewind still confirms, inside
  the menu, in the same words.
**Validate:** `npm test -- BeatControls` (existing cases unchanged + new narrow cases).

### Phase 3 — `BeatTakePager`
`‹ ›` → `Icon name="back" | "forward"`. No behaviour change.
**Validate:** `npm test -- BeatTakePager`.

### Phase 4 — placement
`StoryPlayerView`: replace the two absolute spans with one bar under the beat holding the
pager then the controls. The hover/focus reveal moves to the bar; a beat with more than
one take keeps its bar visible, because the count is state, not an action.
**Validate:** `npm test -- StoryPlayerView`.

### Phase 5 — docs + gate
`docs/component-map.md`, `docs/design-system.md`, `docs/frontend-polish-spec.md` where they
describe the cluster. Then the full gate: `uv run pytest`, `npm test`, `npm run typecheck`,
`npm run lint`, `check_frontend_css.mjs`, `check_contrast.py`.
