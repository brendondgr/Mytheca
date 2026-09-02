# Mytheca — Design System & Design-Quality Brief

This is the design gate that must be satisfied before broad UI implementation. It follows `docs/skills/ui-frontend/ui/design-quality.md`. The visual language below is **locked** — it is derived from the reference designs in `docs/CharacterFrontpage/` (the "Embergate" front page, home, and live scene). Implement it with the project stack (Next.js + React + TypeScript + **Tailwind CSS** + **Framer Motion**); the tokens here are the source of truth, surfaced to Tailwind as CSS variables.

## Visual Motif

Mytheca is a **multi-character roleplay chat engine** styled as **a living manuscript — an illuminated codex / tome**. The reading surface is warm parchment; the chrome reads like the cover and rails of an old book; streamed story beats appear like a play script or annotated transcript. Narrator beats are set apart as marginalia/quotes, character lines as bubbles with wax-seal monogram avatars, the player's voice as an inked reply. Avoid sci-fi "AI" clichés entirely.

### Brand mark & logo assets

The **Mytheca logo** ("Myth" + Greek *Bibliotheca* = "Library of Myths") ships as SVGs in `images/` (canonical brand kit) and `web/frontend/public/brand/`. It is **theme-aware**: the dark-ink icon reads on the light Parchment theme; the cream icon takes over on the dark Ember/Slate themes.

| Asset | File | Use |
| --- | --- | --- |
| Icon — dark | `web/frontend/public/brand/basic.svg` | Header emblem on the **light** theme; also the app **favicon** (`web/frontend/app/icon.svg`) |
| Icon — cream | `web/frontend/public/brand/basic-light.svg` | Header emblem on the **dark / slate** themes |
| Wordmark — dark text | `images/DarkText.svg` | README (GitHub light mode) |
| Wordmark — light text | `images/LightText.svg` | README (GitHub dark mode) |

The header emblem (`.mytheca-brandmark`, in `AppHeader.tsx`) is a decorative `aria-hidden` span whose `background-image` is swapped by a CSS rule keyed on the `.theme-dark` / `.theme-slate` ancestor class (`styles/themes.css`) — no JS, no hydration flash. The `MYTHECA` Cinzel wordmark beside it remains the accessible name.

The recurring identity marks are the **❖ glyph** (`&#10070;`, the "Mytheca seal") and the **◆ diamond** (`&#9670;`) used as the bullet for branches, settings, and choices. Each **storyline** also carries a **customizable seal** — a simple shape glyph + hex color chosen in a dedicated **seal pop-up** (`SealModal`, opened from a compact Seal row in `StorylineModal`) — rendered left of its name in the switcher. The pop-up offers ~24 shapes, a curated color palette, and a native **color wheel** for any custom hex; the shape/color sets live in `web/frontend/lib/seals.ts` (default: gold `◆`).

## Domain Vocabulary (use in copy)

storyline · character · setting · scenario · scene · event · beat · turn · narrator · cast · stat · branch · tone/tension · session. Replace vague phrases ("AI-powered storytelling") with concrete actions: "Begin Scene", "Forge Character", "Add Setting", "New Scenario", "Choose a path", "Speak, or describe what you do".

### Coach marks: hints, not a tour

Three one-time hints on the story player, anchored to the three things a first-time player
provably does not discover: that the composer takes **actions** as well as speech, that they
can play **as** a character, and that the cast rail is **interactive**.

The contract, all of it deliberate:

- **One at a time, never a queue**, and never a modal walkthrough — no overlay, no backdrop,
  no focus trap, no forced sequence. The scene stays fully usable and a player who ignores
  them is never blocked. (The review ruled out a tour explicitly.)
- `role="status"`, not `dialog` — announcing an aside as a dialog implies a modality it does
  not have.
- **Three ways out**: the × (a 24×24 target), `Escape`, or simply *acting on the thing it
  points at*. Anything dismissible only one way eventually traps someone.
- **Dismissal is stored as a set of ids**, not a "seen the tour" flag, so a fourth mark can
  ship later without re-showing the first three.
- **Never point at something that is not there.** The cast-rail hint is suppressed below `lg`,
  where the rail does not exist.
- Nothing renders before hydration (the dismissal set is in `localStorage`, which the server
  cannot see), and a mangled stored value degrades to "show the hints" rather than crashing.

### Keyboard shortcuts in the scene

| Key | Does |
| --- | --- |
| `/` | Jump to the message box |
| `↑` | Bring back the last sent message — **from an empty box only** |
| `Esc` | Close the topmost open thing |
| `?` | Open/close the shortcut sheet |
| `Enter` / `Shift+Enter` | Send / newline (pre-existing) |
| `@` | Name a character, or attach a file (pre-existing) |

Two rules, both non-negotiable:

**Never take a key out of a text field.** `useSceneShortcuts` ignores every event originating
in an editable target, except `Escape` and the empty-box `↑`. A shortcut that eats characters
someone is typing is worse than no shortcut, and it is the first thing a player will hit. The
composer's `@` menu already owns Arrow/Enter/Tab/Escape while open; the hook standing down
inside editable targets is what keeps the two from fighting without either knowing about the
other.

**Never make a shortcut the only way.** Everything above has a pointer equivalent, and the
sheet says so — a shortcut sheet that lists the only route to something is documenting an
accessibility failure, not a convenience.

### The model-status light: four states, never colour alone

The scene header's indicator has exactly four states, and each is a different problem with a
different fix — which is why it is not a boolean and not a single "something is wrong":

| State | Reads | Means |
| --- | --- | --- |
| `reachable` | *Model ready* · `bg-success` | The configured model is served by the endpoint. |
| `model_missing` | *Model not found* · `bg-gold` / `text-gold` | The endpoint is up but does not serve that model — a typo in Options. |
| `unreachable` | *Model unreachable* · `bg-danger` / `text-danger` | Nothing answered — a dead process. |
| `unconfigured` | *No model set* · `bg-mute2` | Nothing was ever set up. Informative, not alarming. |

The dot is **never the only channel**: the label changes with the state and the `aria-label`
carries the endpoint's own explanation. Nothing renders until the first check answers — a light
that guesses is worse than one that waits.

### Control copy: state the effect, and the cost where one exists

**Every control says what it *does*, not what it is called.** A label names a setting; it
never tells the player what happens if they change it, and a menu of implementation nouns
("Max turns", "Beat length", "Number of beats") is why nobody touched the scene config. So:

- The **label is the consequence**: *"How many beats one message produces"*, not *"Max turns"*.
- A one-line **`help`** says what to expect, and is wired through `aria-describedby` so it is
  announced *with* the control rather than floating beside it (`SceneControlSelect`).
- A **cost** goes with the consequence, never in a separate readout — "what it does" and "what
  it costs" are one decision, and splitting them makes the player read twice to make it once.
- **Better silent than invented.** A cost is shown only where there is an honest number; a
  seconds-per-beat figure made up in the UI would be wrong for every operator's hardware.
- A number is not an explanation. `5.2K / 16K` gets prose first: *"how much of what the model
  can read at once this scene is using"*.
- Where the app knows better than the player, it **reports rather than asks** — "What the scene
  remembers" is read-only, and replaced the beats slider outright.

## Typography

Three families, each with a fixed role. **Self-hosted** — the latin-subset woff2 files live in
`web/frontend/app/fonts/` with their OFL licences, loaded through `next/font/local` in
`lib/fonts.ts`. Cinzel and EB Garamond ship as *variable* fonts (Google returns one identical
file for every weight), so each is stored once and declared with a weight range; IBM Plex Mono
is static, so its two weights are two files. This is why `next build` runs offline at all —
`next/font/google` fetched at build time and hard-failed with no network. Each family keeps
`display: "swap"` and a metric-compatible `adjustFontFallback`/`fallback` stack, so removing
the Google loader did not introduce layout shift. `lib/fonts.test.ts` guards the arrangement.

| Role | Family | Usage |
| --- | --- | --- |
| Display / headings | **Cinzel** (500/600/700) | Wordmark, storyline/scenario titles, character names, section headers. Letterspaced (`.16em`–`.2em`) for the wordmark and small caps headers. |
| Body / reading | **EB Garamond** (400/500/600 + italic) | All story prose, descriptions, card body, inputs. Narrator prose and the character action label are **upright** (not italic) — kept muted, not slanted, for legibility. Line height 1.45–1.55. |
| Labels / metadata | **IBM Plex Mono** (400/500) | Eyebrow labels, role tags, counts, stat values, check labels — uppercase, letterspaced (`.1em`–`.22em`). |

Rules: body story text ≥ 16px on mobile; reading measure capped (~720px transcript column). Distinguish narrator beats, character turns, and player turns by **typography + layout + a left-accent**, never by color alone.

### Typography Scale (font-size presets)

Text sizes are driven by **seven** CSS custom properties defined in `styles/themes.css` under `:root`, with four named preset classes that the user chooses from **Settings → Appearance → Text size**:

| CSS variable | Default | Compact | Comfortable | Large | Used for |
| --- | --- | --- | --- | --- | --- |
| `--fs-eyebrow` | 12px | 11px | 13px | 14px | `Eyebrow` component (role tags, section kickers, "❖ Draft with Mytheca" labels) |
| `--fs-label` | 13px | 12px | 14px | 15px | `FieldLabel` headings, form section labels |
| `--fs-ui` | 13px | 12px | 14px | 15px | `Button` text, tab labels |
| `--fs-body-sm` | 15px | 14px | 16px | 17px | Card descriptions, modal body prose |
| `--fs-body` | 16px | 15px | 17px | 18px | Longer reading text |
| **`--fs-field`** | **16px** | **16px** | 17px | 18px | **Every form control.** A floor, not a preference — see below. |
| `--fs-tag` | 12px | 11px | 13px | 14px | `Tag` chips (genre, tone, role pills) |

**Two of these numbers are platform facts, not taste, and no preset may go below them.**

`--fs-field` is pinned at **≥ 16px in every preset, Compact included**. Safari on iOS zooms the page
when an `<input>`/`<select>`/`<textarea>` renders below 16 CSS px on focus, and does not reliably zoom
back out. The 2026-08-31 baseline audit measured **776** controls below the floor across seven routes.
Disabling zoom is not the alternative — that is a WCAG 1.4.4 failure. The floor is applied three ways:
the token, an `@layer base` default in `globals.css` (in `base` so a component that genuinely wants
larger still wins), and a source guard in `components/ui/design-scale.test.ts`.

**One exemption, added 2026-09-01, and it is narrow: `pointer-fine:`.** The zoom the floor exists to
prevent needs a touch keyboard; a mouse never triggers it, and paying the floor on a mouse is what put
six 16px monospaced selects into a 264px popover. `components/ui/Select.tsx` is the one place that
takes the exemption — `text-field pointer-fine:text-ui` — and `pointer: fine` is the same predicate
`styles/motion.css` uses to decide where the 44px touch floor applies, so the two rules agree about
what a phone is. A **breakpoint** prefix is deliberately *not* exempt and the guard still fails it:
`sm:text-ui` looks like the same idea, but an iPhone 14 Pro Max in landscape is 932 CSS px wide, so a
width-gated split hands the device that most needs the floor a 13px field.

`--fs-tag` and `--fs-eyebrow` are caption tiers and stay **≥ 11px**. The same audit found 10.5px text
making up 58.2 % of one route's visible copy. Anything that needs to be smaller than a tier here is
decoration, and decoration does not carry information.

The active preset is stored in `localStorage` key `mytheca-font-size` (default: `"default"`) and applied as a class on `<html>` (e.g., `.fs-comfortable`) by `lib/font-size.ts`'s no-flash inline script in `app/layout.tsx`. The hook is `useFontSize()` in `hooks/use-font-size.ts`. Tailwind utilities `text-eyebrow`, `text-label`, `text-ui`, `text-body-sm`, `text-body`, `text-field`, `text-tag` resolve from the live CSS variable via `@theme inline` in `globals.css`.

### A control's description: on demand, never in the layout

A setting needs a name *and* a consequence — a label alone never tells a player what happens if they
change it. Both used to sit in flow: `SceneControlSelect` rendered its help as a paragraph under every
control, and `SceneMenu` rendered its hint as a wrapped line under every row. Measured live on
2026-09-01 at 1280×720, that put **996 px of content in the 264 px scene-config popover** (356 px of it
prose) and **71–88 px per scene-menu row**.

The rule that replaced it: **the consequence is reached, not displayed.**

- A control gets a short title — short enough not to wrap at 264 px — plus an `InfoTip`
  (`components/ui/InfoTip.tsx`) whose bubble opens on hover, on keyboard focus, and on tap.
- **Nothing leaves the accessibility tree.** The bubble is `aria-hidden`; an `sr-only` twin holds the
  same text under the id the control points `aria-describedby` at. A screen reader hears exactly what
  it heard when this was a paragraph, open or closed.
- WCAG 1.4.13 in full: hoverable (the bubble is inside the element the pointer entered), dismissible
  (Escape), persistent. The Escape is `stopPropagation`'d — dismissing a tip must not also close the
  popover the player is working in.
- Where the title has to be shortened, the longer phrasing goes into the control's **accessible name**,
  appended after the visible title, so the visible text stays a prefix of it (WCAG 2.5.3, label in
  name) and a voice user can still say the words they see.
- A **readout** is not a control and keeps its prose: the config popover's "What the scene remembers"
  block has no setting in it, so there is nothing to defer.
- Where a hint must stay visible (`SceneMenu` rows), it clamps to one line with `truncate` plus a
  native `title`. `truncate` does not touch `textContent`, so the `aria-describedby` target still
  carries the whole sentence.

### Entity colour on a surface

Characters, graph node types, seals and stat bands carry their own colour, chosen for **identity** and
independent of the theme. Rendering those raw as text is what produced **71** contrast failures in the
baseline audit — `#8e2b1c` on the Slate card ground measured **1.71:1** against a 4.5:1 requirement.

Set `--entity` on an element and use the derived colour; never apply the raw value to text:

| Token | Recipe | Worst measured | For |
| --- | --- | --- | --- |
| `--entity-ink` (`text-entity`) | `color-mix(in oklab, var(--entity) 45%, var(--ink))` | **4.55:1** | small text |
| `--entity-ink-strong` (`text-entity-strong`) | `color-mix(in oklab, var(--entity) 65%, var(--ink))` | **3.05:1** | large text (≥24px, or ≥18.66px bold) and non-text marks (1.4.11) |

Because `--ink` is dark on Parchment and light on Ember/Slate, one recipe moves the colour the right
direction in every theme automatically.

The same idea covers the accent and the five semantic colours. In every case the **raw** token stays
for fills, borders and focus rings — where the vivid hue is the point and the 3:1 non-text bar applies
— and an `-ink` variant carries the text:

| Text token | Recipe | Why that percentage |
| --- | --- | --- |
| `text-accent-ink` | `--accent` at **72 %** | The accent has only three known values, not an open palette, so it can keep far more hue. 75 % is the limit; 72 % leaves margin. Raw accent measured 4.27:1 on Ember's card2, 4.05:1 on Slate's, 3.32:1 on Slate's hover ground. |
| `text-gold-ink` · `text-gold-soft-ink` · `text-narrator-ink` · `text-success-ink` · `text-danger-ink` | each at **45 %** | These are theme-*agnostic* by design — one fixed hex cannot clear 4.5:1 against both a cream ground and a near-black one. `#a8762a` measured 4.08 / 3.61 / 3.11 across surfaces; `#1f8a5b` measured 3.30. |
| `text-prose-quote` | `--accent` at **45 %** | Quoted dialogue inside a **free-text** passage, which has no speaker and so no character colour for `speechColor()` to tint toward. The 45 % mix, not `--accent-ink`'s 72 %: a passage can be half dialogue, and at 72 % the quoted runs stop reading as emphasis and start reading as a second voice over the prose. Measured 8.70 / 10.92 / 8.72 on the three themes' card ground. |

`Monogram` is the one deliberate exception, and the exception proves the rule. Its ground is a fixed
parchment `#EDE3CD` in **every** theme, so mixing toward the theme's ink would make Ember and Slate
worse rather than better. Its initials mix toward a dark ink at 60 % instead; its ring keeps the
character's colour untouched, because a ring is a non-text mark.

`Eyebrow` takes `entity` for an identity colour and `color` only for a theme token, and clamps a
numeric `size` to the 11px caption floor — those two props were the app's single largest source of
contrast findings. The two percentages are the **highest hue retention** that
still clears the bar across every built-in entity colour × every surface × all three themes.
`utils/scripts/check_contrast.py` re-derives both numbers from the CSS on every run — the percentages
are read out of `themes.css`, never hardcoded in the gate — so the recipe and the contrast it
guarantees cannot drift apart.

## Themes & Color Tokens

Three themes ship from day one, switched by a `ThemeSwitcher` and persisted (`localStorage` key `mytheca-theme`). Themes are CSS-variable token sets on a root class (`.theme-light` / `.theme-dark` / `.theme-slate`); Tailwind colors reference the variables so components are theme-agnostic.

**Three-tier layering rule.** Every theme is built as three distinct lightness tiers so sections divide cleanly instead of blending: **chrome** (header/rail gradients — the darkest tier per theme), **page ground** (`--page-bg`, the middle tier), and **content** (`--card-bg`/`--card-bg2`/`--menu-bg` — the lifted tier that holds text). Inputs (`--field-bg`) sit slightly *recessed* from cards in the dark themes and slightly *raised* in Parchment. New surfaces should pick a tier deliberately; a panel that frames content (sidebar, nav rail) belongs on the chrome tier (`mytheca-rail`/`--surface`), never on the card tier.

**Contrast gate.** `utils/scripts/check_contrast.py` parses these token sets and asserts the load-bearing WCAG-AA pairs (hard-fails the build script on regressions). Adjust tokens and the script's pair list together.

| Token | Parchment (`light`) | Ember (`dark`) | Slate (`slate`) | Purpose |
| --- | --- | --- | --- | --- |
| `--page-bg` | `#DCCCA8` | `#0D0A05` | `#0A0E13` | App background (middle tier) |
| `--page-img` | warm radial wash | ember radial wash | cool radial wash | Subtle page glow (two `radial-gradient`s) |
| `--card-bg` | `#F4ECDA` | `#241C13` | `#1A2129` | Card / bubble surface (lifted tier) |
| `--card-bg2` | `#FAF3E1` | `#2E2417` | `#222B35` | Selected / raised surface |
| `--card-bd` | `#C2AC7E` | `#52422A` | `#3C4A57` | Card border |
| `--hair` | `#D2C093` | `#332818` | `#232C35` | Hairline divider |
| `--hair-strong` | `#A98F5D` | `#5C4A2B` | `#465667` | Stronger divider / rail edge (now visibly heavier than `--hair` in every theme) |
| `--ink` | `#241B10` | `#F1E5CC` | `#E7EDF3` | Primary text |
| `--ink-soft` | `#59492F` | `#C8B694` | `#A9BAC8` | Secondary text |
| `--mute` | `#55452C` | `#A9946B` | `#8A9FB1` | Muted labels (AA on page, card, menu, chrome) |
| `--mute2` | `#6E5B3C` | `#93805C` | `#6E8496` | Faint labels / placeholders (AA on `--field-bg`) |
| `--field-bg` | `#FBF6EA` | `#16100A` | `#10151C` | Inputs / icon buttons |
| `--field-bd` | `#A98F5D` | `#52422A` | `#3C4A57` | Input border |
| `--header-grad` | `linear-gradient(#D6C49A,#C9B586)` | `linear-gradient(#191208,#0F0B05)` | `linear-gradient(#121820,#0B0F15)` | Header / composer bar (chrome tier) |
| `--rail-grad` | `linear-gradient(#D9C8A0,#CFBD8F)` | `linear-gradient(#150F08,#0F0B06)` | `linear-gradient(#10161D,#0B0F14)` | Side rails (chrome tier) |
| `--modal-bg` | `#F1E8D3` | `#261D12` | `#1D2630` | Modal surface |
| `--accent` | `#8E2B1C` | `#D3694F` | `#DC634A` | Primary accent (ember); AA as text on page/card/field |
| `--accent-hover` | `#6E1F12` | `#B0492F` | `#BA4A32` | Hover fill for accent controls — always **darker** than `--accent`, so `#F6ECDA` text gains contrast on hover |
| `--menu-bg` | `#FAF3E1` | `#2B2214` | `#28323E` | Dropdown/popover surface (elevated above cards) |
| `--menu-bd` | `#A98F5D` | `#5C4A2B` | `#465667` | Dropdown/popover border |
| `--hover-bg` | `#ECDFBC` | `#382C1A` | `#2E3945` | Row/ghost hover tint — visible against page, card, and menu surfaces |
| `--surface` | `#EDE2C6` | `#1B1509` | `#141B22` | Raised panel ground between page and card (sidebar/nav chrome) |
| `--tab-ink` | `#59492F` | `#B09A6F` | `#B7C7D4` | Tab label text (`LibraryTabs`) |

**Theme-agnostic semantic colors** (used across all themes):

- **Gold** `#C8862A` / `#A8762A` — secondary highlight, eyebrow accents, featured tags, check chips.
- **Narrator teal** `#1F8A82` — the narrator card's left border + label; tint `rgba(31,138,130,.12)` for its background.
- **Success / "now" green** `#1F8A5B`.
- **Failure / danger** `#9A3520` (and the accent for "secret"/warning labels).
- **Character colors** — each character carries its own accent (chosen from a **12-color palette** in `web/frontend/lib/seed-data.ts` `PALETTE`: `#8E2B1C`, `#A8762A`, `#2F7D6B`, `#3A5A78`, `#6B4A8A`, `#5A534A`, `#1F8A5B`, `#B0506A`, `#C56A1F`, `#7E8A2B`, `#2C8E8E`, `#8E3B7A`) used for its monogram ring, name, and role tag.
- **Story-Graph node/edge colors** (`web/frontend/lib/graphColors.ts`) — the story-player **Graph view** colors nodes by type (Character `#B0492F`, Setting `#2F7D6B`, Event `#C56A1F`, Faction `#6B4A8A`, Secret `#B0506A`, Consequence `#3A5A78`) and edges by **valence family** (positive `#1F8A5B`, negative `#9A3520`, neutral slate `#5B6B7A`), theme-independent so the graph reads the same in all three themes. Any **unknown/user-defined type** is assigned a **stable color from a deterministic name hash** (mid-band HSL, clears 3:1 on both grounds) so the map keeps working as the graph grows. A **visible legend** pairs every color with its type label and an **sr-only `<table>`** lists nodes/edges — the canvas never conveys meaning by color alone (WCAG 1.4.1) and always has a text alternative (1.4.11 / 1.1.1).

All text must meet WCAG AA contrast (4.5:1 body, 3:1 large/non-text) **in every theme** — verify Parchment, Ember, and Slate. Status and stat changes are never conveyed by color alone (pair with a label, sign, or icon).

**Frontend implementation.** The three token sets live in `web/frontend/styles/themes.css` as `.theme-light` / `.theme-dark` / `.theme-slate`; the active class sits on `<html>`, applied pre-paint by a no-flash inline script (`themeInitScript` in `lib/theme.ts`). `app/globals.css` maps the variables to Tailwind utilities via `@theme inline` — e.g. `bg-page`, `bg-card`, `bg-card2`, `text-ink`, `text-ink-soft`, `text-mute`, `border-cardbd`, `border-hair`, `text-accent`, and the interaction tokens `bg-accent-hover`, `bg-menu` / `border-menu-bd`, `bg-hover`, `bg-surface`, `text-tab-ink`, plus theme-agnostic `text-gold` / `text-narrator` / `text-success` / `text-danger`. Gradient surfaces (page glow, header, rails) use the `.mytheca-page` / `.mytheca-header` / `.mytheca-rail` helper classes. The current theme is read via `useTheme()` (a `useSyncExternalStore` over the `<html>` class + `localStorage['mytheca-theme']`, so no provider is needed) and toggled by `ThemeSwitcher`.

## Geometry, Elevation, Icon, Spacing

### The scales (space · radius · elevation)

The baseline audit counted **1,335 arbitrary spacing values over 165 distinct numbers** and **8
distinct border radii** across 136 component files. That is the measured mechanism behind "every part
looks good, the whole looks unpolished": components tuned in isolation cannot align with each other
because there is nothing for them to align **to**.

All three scales live in `:root` in `styles/themes.css` and are mapped to Tailwind in `globals.css`:

| Scale | Steps | Tailwind |
| --- | --- | --- |
| Space | `--sp-3xs` 2 · `--sp-2xs` 4 · `--sp-xs` 6 · `--sp-sm` 8 · `--sp-md` 12 · `--sp-lg` 16 · `--sp-xl` 24 · `--sp-2xl` 32 · `--sp-3xl` 48 | `p-md`, `gap-lg`, `mt-xl` |
| Radius | `--r-xs` 3 · `--r-sm` 5 · `--r-md` 9 · `--r-lg` 14 · `--r-full` | `rounded-xs` … `rounded-lg` |
| Elevation | `--elev-sm` · `--elev-md` · `--elev-lg` · `--elev-xl`, all tinted by the per-theme `--shadow-tint` | `shadow-sm` … `shadow-xl` |

**A value that is not on a scale is a bug, not a refinement.** If a design genuinely needs a step that
does not exist, the scale gains a step — once, in `themes.css` — rather than the component gaining an
arbitrary number. `components/ui/design-scale.test.ts` holds a **ratchet** on the arbitrary-value
counts: the budgets are the totals at the end of the last completed overhaul phase, and they may
never rise.

Space is deliberately **not** tied to the `.fs-*` presets: text size is the user's preference, layout
rhythm is the design's. Tying them makes the Large preset explode the layout instead of enlarging the
words. Page rhythm that should follow the *viewport* uses `--gutter` and `--step-*` instead.

Elevation tokens are named `--elev-*`, **not** `--shadow-*`, because Tailwind v4 owns the
`--shadow-*` theme namespace: a token of the same name mapped through `@theme inline` compiles to
`--shadow-sm: var(--shadow-sm)`, a self-referential custom property.

`--control` is the one square-chrome edge — **44px below `sm`, 34px above it**. The header's
back link and menu trigger were sized by padding (`px-sm py-xs`), which made them ~10px taller
than wide; a bar whose controls are each a slightly different rectangle reads as sloppiness. The
breakpoint split is deliberate: on a phone the square **is** the WCAG 2.5.8 target rather than a
projected one, and above `sm` the chrome returns to the dense size the design system asks for.

Note what forced that split. The coarse-pointer floor in `styles/motion.css` sets
`min-height: 44px`, and **`min-height` beats `height` regardless of specificity** — it is the box
model, not the cascade — so a control that set its own height was grown anyway. The floor's own
comment claimed the opposite, citing the 24px `IconButton` as an example of a control that "still
wins"; measured, that button rendered 24 wide by 44 tall on a coarse pointer. The floor now
exempts `.touch-target-overlay`, which is exactly the promise it wants: an element already
projecting a 44x44 hit area from its centre gains nothing by growing its box.

`--header-h` (56px) is also declared here. It was previously referenced by the `scroll-margin` rule in
`globals.css` and **declared nowhere**, so the 4.5rem fallback always applied while the real bars were
52px and 50px — deep links landed ~20px off. It now also drives `scroll-padding-top`, which is what
satisfies WCAG 2.2 SC 2.4.11 (Focus Not Obscured).

Each theme declares `color-scheme` (`light` on Parchment, `dark` on Ember and Slate). Without it the
dark themes were dark only in the parts Mytheca paints — native selects, date pickers, autofill
grounds and Firefox scrollbars all rendered in light chrome.

### The icon set

`components/ui/Icon.tsx` is the only place an `<svg>` may be written. Eight components drew
their own — fifteen drawings on their own grids at their own stroke weights — which is the
scale problem one layer down: an icon tuned to look right beside one label cannot line up
with an icon tuned beside another, because there is nothing to line up to.

Three rules make it a set:

- **One 24 viewBox and one stroke weight** (`1.7`), so two icons at the same `size` carry the
  same visual mass. A path drawn on a 16 grid and scaled up arrives ~1.5x heavier.
- **`currentColor`, never a literal.** Each of these sits inside a control that already
  changes colour on hover, focus and `aria-pressed`. `filled` (fill from `none` to
  `currentColor`) exists for `pin` alone, whose on/off state *is* the fill.
- **`aria-hidden` by default.** Nearly every icon sits beside a visible label or inside a
  control carrying its own `aria-label`, where announcing itself is a duplicate reading.
  `label` promotes it to `role="img"` for the rare standalone case.

Icons replace text glyphs (`✎ ⚙ ◍ ‹ ›`) in **chrome**, and that is not cosmetics: a glyph
inherits the font stack, so it renders differently per platform, shifts the line box, and
lands at whatever size the type scale gives it rather than at the size the control needs.
The `❖` seal and `◆` diamond stay — they are brand marks in *content*, not controls.

`Icon.test.tsx` enforces zero inline `<svg>` outside the set. Two files are exempt on a
principle rather than a backlog: `ContextUsageDial` and `GraphCanvas` compute their geometry
from live values, which is drawing, not iconography.

### Legacy geometry notes

- **Radius:** cards/inputs/buttons `2–3px` (manuscript-flat); chat bubbles use asymmetric `3px 11px 11px 11px` (character) and `11px 3px 11px 11px` (player); pills/chips `11–20px`; modals/hero `4–6px`; avatars are circles.
- **Borders:** hairline `1px` in `--card-bd`/`--hair`; selected state is a `2px` accent border on `--card-bg2`. Section headers use a thin double rule (`border-top:1px solid ink; border-bottom:1px solid hair-strong`).
- **Elevation:** subtle, warm shadows — cards `0 1px 2px rgba(20,14,6,.06)`, hover `0 6px 16px rgba(40,30,16,.12)`, frames `0 6px 22px rgba(40,30,16,.16)`, modals `0 24px 60px rgba(14,9,4,.55)`. No glassmorphism, no neon glow.
- **Avatars:** monogram circles — character initials in **Cinzel 700**, background `#EDE3CD` (light), `2px` ring in the character's color, text in the character's color. Sizes ~24–62px by context.
- **Icons:** the ❖ seal and ◆ diamond are the brand glyphs; otherwise the single line-icon family above. Avoid generic AI brain / sparkle / network-node iconography — the deliberation icon is a spark rather than a brain because a brain at 14px is a grey blob, not because a brain is on-brand.
- **Spacing:** consistent rhythm — rails ~16–18px padding, cards ~11–14px, transcript column max-width **720px** centered with 16px gaps between beats.

## Story-Player Layout (the signature surface)

A three-zone "open book": a **left cast rail** (At the table · turn order, portrait avatars with per-character **"Thinking"/"Speaking"** activity indicators), a **reading-first center column** (a `SceneIntro` "scene is set" band — setting, genre/tone, the player's aim, dramatis personae — then the transcript of beats and a **two-row composer**), and a **right director rail** (a live **"Scene pulse"** activity feed + scene-state chips). The per-scene **Config** (gear button → popover with "Max turns" 1–10, "Suggestions" 0–4, and a "Number of beats" 5–100 slider) now lives in the composer's **bottom-left controls row**, not the header. The transcript is the primary surface and stays centered at ≤720px; the `SceneIntro` band ensures the reading column carries the full scene context even on mobile. This is deliberately **not** a generic three-pane SaaS shell or a card grid.

**`sr-only` is `position: fixed`, not `absolute`.** `app/globals.css` overrides Tailwind's
utility with a bare, unlayered rule. An absolutely-positioned visually-hidden element with no
positioned ancestor lays out against the *initial containing block*: it escapes every
`overflow: hidden` between it and the root and adds its offset to the **root** scroller —
measured at 6212px of blank, scrollable, empty page for 28 files in a 720px viewport. `fixed`
resolves against the viewport (or a transformed ancestor, which is itself clipped), so it
cannot extend the root scroller; document order, and therefore the reading order and the
accessibility tree, are unchanged. Two things to know before touching it: use a **bare rule,
not `@utility sr-only`** — `@utility` merges with the core utility rather than shadowing it,
and the offline PostCSS pipeline and Turbopack order that merge differently — and Tailwind's
`not-sr-only` escape hatch does **not** survive this override (nothing uses it;
`responsive-floor.test.ts` fails if anything starts to).

**Below `sm` the scene header collapses into one overflow menu.** The control cluster is `flex-none` on purpose — letting it shrink pushes its children 50–150px past the viewport edge rather than 7px — so the fix is the *item model*, not the width. `SceneHeader` renders its cluster once, in one of two forms, chosen by `useMediaQuery("(min-width: 640px)")`: at `sm`+ the inline row; below `sm` only the **Chat ⇄ Graph** switch and the **model-health** glyph stay inline, and the play-through tray, theme, the memory toggle, the Inspector, Export, Writing… and the keyboard-shortcut sheet all live in `SceneMenu`. An item that owns a panel (the tray) is **drilled into in place** — its rows replace the menu's, with a `‹ Back` row — because a popover inside a popover has two Escape targets and a focus order nobody can follow. At 320×720 this took the header from **17px of clipped overflow to zero**, while *adding* two controls that width never had: the health indicator (previously `hidden sm:flex`) and the shortcut sheet (previously `?`-only).

**Below `lg` the two rails become bottom sheets.** They are not reduced copies: `CastRail`, `DirectorRail` and `CharacterDossier` are each split into a `…Content` component and a thin `lg`-only `<aside>` shell, and the sheet mounts the *same* content component with the *same* prop object — so a capability added to a rail reaches the phone in the same edit. The triggers are **rows in the scene menu**: **Cast** with the present-cast count, **Scene** with an amber badge counting what the direction still owes, and **What the scene knows**. They were a `SceneRailBar` directly above the composer until 2026-08-31 — one tap rather than two, and one more horizontal band of chrome on the narrowest screen in the app, which is what it cost. A row that opens a sheet carries `closesMenu`, because a sheet raised under a still-open menu is a surface hidden by the thing that revealed it. The desktop rule that the dossier takes over the Director rail holds in the sheet too — selecting a character below `lg` raises the Scene sheet showing their dossier, since setting a profile that nothing renders reads as the app ignoring the tap. The sheets use the `Drawer` primitive (portal, shared focus trap, scroll lock, `@starting-style` entrance with a reduced-motion path); a sheet that is animating out is `aria-hidden`, so exactly one dialog is ever in the accessibility tree. The scene pulse and the direction checklist take `live={false}` inside a sheet — a log that mounts on open would otherwise announce the whole turn at once, after the fact.

**The scene menu, and writing prompts at play time.** The scene header's right-hand cluster
is `flex-none` on purpose — letting it shrink pushes its children 50–150px past the viewport
edge rather than a few — so every control in it costs width a 320px screen does not have.
`SceneMenu` is one `☰ Scene` popover holding what used to be three inline controls:
**Writing…**, **Turn Inspector** (a toggle) and **Export as Markdown / JSON**. The header
therefore *gains* an entry point while *losing* width (measured: 45px of 320px overflow down
to 17px — see `docs/checklist.md`, which `docs/plans/reach.md` Phase 4 closes).

Idiom, shared with `SceneConfigMenu` so the app has one popover behaviour rather than two:
native buttons in a `role="menu"`, Esc and outside-click close, focus moved into the panel on
open. A **toggle** is a `menuitemcheckbox` with `aria-checked`, never a `menuitem` wearing
`aria-pressed` (invalid ARIA — screen readers may drop the state), and selecting one **keeps
the panel open**, because closing it would hide the change just made. Each row's `hint` is its
accessible **description**, not part of its name — left to the default computation the two
concatenate ("Turn Inspectorwhat the scene read…"). A disabled row's hint doubles as the
reason it is unavailable, since a disabled control with no explanation reads as a bug.

**Writing prompts, with their origin named.** The scene's **"How this world writes"** modal is
the play-time entry point to the prompt-override system — previously two navigations from the
only place its effect is observable. It edits the **scenario** layer, and each prompt now
carries a small text badge naming where its live value actually comes from: *Default ·
Everywhere · This world · This scene* (`lib/promptLayers.resolveLayers`, mirroring
`prompt_registry.resolve_prompts` — last non-blank wins, and a **blank means inherit**). The
labels are player words: "Everywhere", not "global". Badges render **only** where every layer
is known; a surface that cannot see the storyline layer shows none rather than mis-attributing
"This world" to "This scene".

**Word choice (character editor).** A character's **looseness** is a 5-stop native
`input[type="range"]` above the voice-sample rows in the Voice & tone section, `-2 … +2`,
with a **text** readout — *Controlled · Measured · Natural · Expressive · Loose* — because a
slider position alone does not tell a reader which of five settings they landed on. The stop
names carry the meaning; the number is an implementation detail of the sampler nudge behind
it. One line of consequence sits under it via `aria-describedby`: *"How far this character's
word choice may wander. The moment's register still leads; this only leans against it."* A
native range keeps keyboard operation free. `CharacterDossier` renders the same value
**read-only** during play, beside the character's speech style, so a player can find out why
someone sounds the way they do without leaving the scene — editing from the dossier is a
recorded deferral.

**Presets before controls.** The scene-config popover opens with **"What kind of scene this
is"** — Custom plus four named presets (`content/scene_presets.py`) — above the three
individual controls, because that is the question a player actually has; the controls answer
the one they have to be taught to ask. The selected preset's **blurb names the trade, not the
numbers**: the numbers are in the controls immediately beneath it, and restating them in prose
tells the reader only what they can already see. A preset writes through the **pinned** path
(it is a statement about the scene, not one turn) in a single scenario write, and drops any
pending per-turn override for the controls it sets — leaving one would have the next turn
silently contradict the preset just chosen. Moving a control afterwards does **not** clear the
preset: the row reads *· modified* and a **"Reset to <preset>"** button appears, which is only
offered in that state (a reset with nothing to undo is a button that does nothing). Choosing
Custom clears the name and touches no value. If the catalogue fails to load the picker does
not render at all and every control stays exactly where it was.

**Pins — permanent versus this-turn.** Every row in the scene-config popover carries a
24×24 **pin toggle** to the right of its caption, and the pin decides where a change *goes*,
not what it is. **Pinned** (the default, and where every control starts) is the original
behaviour exactly: picking a value writes it to the scenario and it stays. **Unpinned**, the
same pick applies to the **next message only** and then springs back — nothing is written,
and the menu still shows the chosen value because it renders the pending override in
preference to the scene's own.

Scope is stated in **text, never in colour alone**, in three independent places: the pin's
`aria-pressed` plus an accessible name that says which scope is in force ("Max turns —
pinned to this scene" / "Max turns — this turn only"); a filled versus **outlined** pin glyph
(shape, not hue); and a "· this turn" suffix on the row's own caption. A footer line appears
only while something is unpinned — *"2 settings apply to your next message only, then spring
back."* — and the closed **Config** button grows an accent dot whose meaning lives in the
button's accessible name, so the state is legible without opening the popover.

The footer and the scope suffix are `--ink`, **not** `--accent`: accent on the menu ground is
3.67:1 in Slate and 4.40:1 in Ember, which is fine for a border or a glyph and fails AA for
copy. `check_contrast.py` carries that pair as `accent(nontext) / menu` at 3:1 so the
distinction is enforced rather than remembered. The pins take the **global** `:focus-visible`
outline; they deliberately do not set `focus:outline-none`, which would be inert anyway (that
rule is unlayered and a Tailwind utility cannot override it).

Re-pinning a control **discards** its pending override rather than promoting it to the scene.
Promoting would make a pin click a silent permanent write, which is the exact surprise the
pin exists to remove.

**Graph view mode.** The `SceneHeader` carries a compact **Chat ⇄ Graph** segmented switch (left of Export). Switching to **Graph** replaces the center transcript+composer column with `GraphView` — the scenario's Story-Graph as a force-directed canvas (`react-force-graph-2d`), nodes/edges colored by type (see the Story-Graph node/edge colors bullet above) with an sr-only node/edge table. The cast rail stays; the Director rail + Turn Inspector are replaced by the **`GraphInspectorPanel`** right rail. The graph is fetched (and its renderer chunk loaded) only on first switch, and shows a calm "offline" state when the graph DB is down. **Graph Inspector:** with nothing selected it shows the **type breakdown** (node types and edge types, each `swatch · type · count`); **clicking a node or edge** highlights it on the canvas (selection ring / thicker link) and switches the rail to that element's **properties** (its `metadata`, a colored type badge, name-resolved edge endpoints), with a **Back** button to the overview; clicking the background clears. It is an author-facing diagnostic (like the Turn Inspector), so it surfaces every property the graph carries. Mirrors the `DirectorRail` shell (`hidden … lg:block`), so on `< lg` the graph shows canvas-only (the sr-only table remains the data alternative).

**Context usage dial.** A small (24 px) circular **button** (`ContextUsageDial`) in the composer's bottom controls row, immediately left of Send, visible only when the model's context-window size is known. The ring fills with `used / max` and is stroke-coloured by the same token-driven thresholds — `--color-success` (green) below 50 %, `--color-gold` at 50–75 %, `--color-danger` at or above 75 %. The ring is **purely visual — no number in the centre**; the count surfaces only on **hover / keyboard-focus**, in a tooltip above the dial reading `"8.3K of 16K tokens · 56% · exact"`. That same text is the button's `aria-label`, so the exact figure and its provenance (the model's reported `usage.prompt_tokens` vs. a char/4 estimate) are always available non-visually. The arc transition is `motion-reduce:transition-none`. It replaced the earlier slim full-width **context usage bar**.

**Two-row composer.** The composer is a transparent outer band wrapping a centered `max-w-[720px]` chat panel (`rounded-[14px]`, `border-field-bd bg-field` surface, `focus-within` accent ring) that reads as **one continuous unit**: a compact auto-growing `<textarea rows=1>` (full width; expands to `scrollHeight` capped at 240 px ≈10 lines, then scrolls), then a small **gap** (no dividing line), then the controls bar. The textarea's boxy `:focus-visible` outline is suppressed (a `.composer-input` opt-out from the global focus outline); focus shows as the panel's `focus-within` accent border **plus a 2 px inset accent bar down the focused field's leading edge**. The bar is per-field on purpose — under Player POV the panel holds two textareas, and a panel-level ring alone cannot say which one you are in. **Scene direction (Player POV only).** A second, shorter textarea sits **above** the message box, separated by a hairline `border-field-bd` rule: `13 px`/`text-mute`, placeholder "Guide the scene — what happens next…", growing to a 120 px cap (half the message box's — direction is a note to the scene, not the line you are performing) and then scrolling. The panel grows **upward**, so opening it lifts the transcript rather than covering it. It is hidden in Playwright mode, where the message box already carries the direction. The controls bar holds **Config** on the bottom-left (rounded button; popover opens **upward** — `openUp` — so it clears the screen edge; the "Number of beats" readout reflects the **real** recent transcript when `beatTexts` is supplied), then the **Player POV "Speaking as" select** (`PovSelect`) immediately to its right, a flexible blank gap reserved for future options, then on the right the **context dial** and a small **"Send →" pill** (`bg-accent`, `Send` label + right-arrow SVG, `aria-label="Send"`). Everything in the controls bar is deliberately small/quiet so the panel stays low-profile. The **`PovSelect`** is a compact **custom dropdown** whose trigger matches the Config pill (a small **portrait avatar** of the current POV + its mono/uppercase name + a caret; `min-w-0`/`truncate` so it shrinks rather than overflowing on a 320 px composer row, showing "M…" at the extreme). Clicking it opens an **upward** `role="menu"` popover whose rows each carry the character's **portrait avatar (monogram-initials fallback) + name** — "Playwright" (a mask glyph) plus each present cast member — with the active row accent-tinted + checked. The textarea placeholder follows the selection ("Speaking as Mei…"). Enter sends; Shift+Enter inserts a newline; the textarea stays editable while a turn streams (only Send + Enter are blocked via `sendDisabled`).

**Player-POV character bubble.** When the player speaks *as* a character (Player POV), their line renders on the player's side of the transcript (right-aligned, like the ordinary player bubble) but wears the character's identity: a header of the character's `Monogram` + name in the character's color, above the **same `--accent` bubble with `#F6ECDA` text** as `PlayerMessage`. The accent fill is kept deliberately (rather than tinting the bubble with the character's color) so contrast stays AA regardless of how light a character's color is — only the header carries the character color, on the parchment background where cast colors are already used for names/roles. This is the sole right-aligned *character* variant; a left-aligned `CharacterMessage` remains the AI-voiced form.

**Scene pulse (Director rail).** The static Scene Goal, TensionMeter, and Relationships sections were replaced by a **"Scene pulse"** live feed: a `role="log"` `aria-live="polite"` scrollable region (`max-h` capped, newest entry first) of up to 12 `ActivityEntry` items. Each entry is a compact line with character-colored name, a status verb, and optional detail text; entries animate in with the transcript beat-entrance idiom (opacity + 8 px rise, `motion-reduce` safe). An idle empty state reads **"The scene is quiet — your move."**. The `StateChips` scene-state block is kept beneath the feed.

**Turn status strip (transcript foot).** While a turn streams, a rounded pill under the last beat names **who is up**: the speaker's `Monogram` (their color on the ring), a phase sentence — "X is about to speak" · "X is speaking" · "X is acting" · "The narrator is setting the scene" · "The turn is ending" — and the shared `TypingDots`. Between beats it reads "The scene is unfolding" rather than blinking out, because a strip that vanishes at every beat boundary reads as a glitch instead of as progress; in the "ending" phase the dots are dropped, since nothing more is coming. It occupies the slot `CreateImageBar` uses between turns, so the foot of the transcript never empties and the composer never hops. The label sits on `--ink-soft`, never the character's color: at 10px uppercase a light cast color would fall under AA (measured 7.4–8.5:1 across the three themes as written), so identity is carried graphically by the monogram ring. One `role="status" aria-live="polite"` region carries the label — it changes at most once per beat, and says what the `TranscriptAnnouncer` (which speaks *finished* prose) cannot. **This is the only speaker signal below the `lg` breakpoint, where the cast rail is hidden**, which is why it lives in the reading column rather than a rail.

**Character activity indicators (Cast rail).** Each cast-row shows an animated **three-dot typing indicator** (`embDots` keyframe, `static "…"` base style so reduced motion degrades gracefully per the `.mytheca-themed *` global rule) plus a **"Thinking"** label while a character is processing, and a **"Speaking"** label while their dialogue is streaming. Both states clear to idle when the turn ends. Status is never conveyed by motion alone — the text label ("Thinking"/"Speaking") is always present alongside the dots or accent treatment.

### Event → component mapping (visual contract)

| Event | Rendering |
| --- | --- |
| `narration` | Teal left-border card (`#1F8A82`), faint teal tint, **upright** EB Garamond (not italic), mono "Narrator" eyebrow. Quoted runs render **bold** (`QuotedText`). |
| `character_dialogue` | Monogram avatar (character color) + Cinzel name in that color + chat bubble (`--card-bg`, asymmetric radius). Any text wrapped in double quotes (straight or curly) renders **bold** while keeping the quotes, via the `QuotedText` primitive. |
| `character_action` | Short **upright** label (5–10 words, not italic) next to the name, in `--mute2` (e.g. "leans in, low"). |
| `internal_thought` | **Folded into the speaker's beat inside ONE bubble** (not a separate block): the thought sits at the top of the spoken bubble as a muted, **italic** line (mono `thinks` tag + `--ink-soft`) at the **same 15.5px size as the speech** below it, separated by a `--hair` rule — so one message shows what they think, then what they say, without a size jump. |
| player turn | Right-aligned bubble in `--accent` with `#F6ECDA` text, mono "You" eyebrow. Quoted runs render **bold** (`QuotedText`). |
| `state_update` (stats) | Updates the Director rail's **Scene-state chips** (label + signed value, colored by direction; the change `reason` rides as the chip's title) AND the open **character dossier's** stat sliders, which are value-aware: the thumb, floating readout, and band title track that character's live per-`characterId` value (falling back to the schema default until it first moves). No chat message. |
| `branch_choices` | Centered "Your move — choose a path" block of ◆ choice rows (**label + outcome only** — no dice/check, D11). 1–2 choices stack in a column; **3–4 lay out in a 2-column grid** (4 → a 2×2 grid). Selecting a row submits a real turn steered **open-endedly** by `guidance` (not a scripted play-out). |
| `character_status_change` (presence) | Updates the **cast rail**, not the transcript: a non-`present` character dims and drops to an "Out of the Scene" group with a status badge (`dead` struck through); every row carries a labeled presence `<select>` for manual control. An `auto` change also raises an **Undo** toast (restores the character to `present`). |

### Turn Inspector (diagnostic panel)

A docked right-side column (opt-in `trace` frames) that shows, per message, what the turn
loop did and why. Turns are an **accordion** — the active (newest) turn is expanded, completed
turns collapse to a clickable header. Each step is a **colored dot on the left + a short tag +
title**, and clicking a step expands a dropdown to reveal its plain-language detail. The dot
colour categorises the step (Intent / Plan / Speaker / Thinks / Speaks / Stat / Bond / …) but
is always **paired with the text tag**, so meaning never rests on colour alone (WCAG 1.4.1).
Read-only — the panel never changes the scene.

### Stats & tension display

- **Scenario state chips:** a label (EB Garamond) + a mono value; positive/neutral/negative colored by `--ink-soft`/green/accent. Hidden-visibility stats are omitted from the player's view. Rendered in the Director rail beneath the Scene pulse feed.
- **Tension/tone meter (`TensionMeter`):** a thin bar with a gold→ember gradient fill and a mono label ("Rising — the room is taut"). Now used by `CharacterDossier` only (removed from the Director rail's main view when the Scene pulse replaced the static sections).
- **Relationships:** short lines keyed by character color. Now displayed in `CharacterDossier` only (removed from the Director rail's main view for the same reason).

## Library Layout (the front page)

**Below `lg` the Library is a normal document scroll; at `lg` it is a viewport-locked shell.**
That inversion is deliberate. At `lg` three columns each scroll inside `h-dvh` + `overflow-hidden`
so the page itself never moves. Below it there is one column at a time, so a locked shell buys
nothing and costs something real: it fights the browser's own scroll on a phone, the address bar
never collapses, and the hero and the list read as two surfaces moving separately. The header is
`sticky` there (and `static` at `lg`), since the storyline switcher and Create are what you reach
for after scrolling.

The per-column `ColumnHeader` is `lg`-only for the same reason the "Recent" badge is gone: it
restated the tab directly above it — "SCENARIOS 3" under a tab reading "Scenarios 3" — and pushed
the first card down a screenful. Its `+` moved into the tab bar's `action` slot rather than
disappearing with it.


The Library makes the **Storyline** the organizing object. The header wordmark is followed
by a prominent **storyline switcher** — an outlined button rendering the active storyline in
large Cinzel small-caps (echoing the `MYTHECA` wordmark) with a ◆ seal and a rotating chevron,
so it reads unmistakably as a dropdown. It lists every storyline (✓ active, with per-storyline
counts) plus "New Storyline"; switching swaps the whole working set. Below the recent-scenario
hero, the body is **three open columns** — **Scenarios** (one per row) · **Characters** (three
per row, two on the narrowest widths) · **Settings** (one per row) — shown side-by-side on desktop with hairline dividers.
On `< lg` they collapse to a single column chosen by a 3-tab section switcher (the same ARIA
tablist, `lg:hidden`); each column is rendered exactly once (CSS-only visibility), never
duplicated.

The **recent-scenario hero** (`ScenarioCarousel`) is the page's lead artifact and leans on
real imagery for contrast. A **left scene-art panel** sets the scenario's `image` full-bleed
behind a **graduated scrim** (strong on the left and bottom, under the title / location / tags
/ goal / Begin Scene button, fading to near-clear on the right so the artwork reads) — not a
flat wash. Beside it, an **arrow-paged cast carousel** renders the cast as **transparent portrait
tiles** that **match the Library Characters-column card**: the WebP portrait fills the card behind
the vertical **`PORTRAIT_SCRIM`**, with the **name** (`OVER_ART.title`) + **role** (`OVER_ART.eyebrow`)
reading over the lower scrim, framed in a **2px border keyed to the character's accent `color`**
(large monogram fallback on a solid `--card-bg2` surface). Statistics are **not baked into the
card**: each tile is a **2-column grid** (portrait + stats), and a small **`❯`/`❮` arrow**
(top-right) **slides a statistics extension out of the same bordered card** — the stats column's
width animates `0 → ~208px` (`grid-template-columns` transition, reduced-motion aware), so the
panel reads as **the character card extending**, not a separate box, and the now-wider card
**pushes the following cards over** (one open at a time). The extension lists the storyline's
**player-visible (public) stat names + default values** for that character (filtered by
`visibility`/`appliesTo`), with a "No statistics available." fallback. When
the cast **overflows** the visible width the strip shows **left/right arrow buttons** (`Previous` /
`Next characters`) that page it (`scrollBy`); each arrow hides at its respective end and both stay
hidden when everything fits, with native keyboard/trackpad scroll preserved underneath. The slide
is `w-full min-w-0` so the strip is bounded and **scrolls rather than clipping the cast off the
right edge**. **Deviation from the reference:** the reference mockup shows pictographic role icons;
we have no role→icon data, so role is shown as text.

The page is **self-contained** (`h-dvh`, no page scroll): on desktop the column row is pinned
to the viewport and **each column scrolls independently**; on mobile the single active column
scrolls. Each column header is **sticky** so its identity stays visible while its cards scroll.
The columns sit on a **solid `--page-bg`** that spans the full container width — the page's
radial glow (`--page-img`) is never allowed to show through behind the scrolling cards.

Selecting a scenario in the Scenarios column drives the rest: the hero reflects it, its
**cast lights up** in the Characters column (an **animated pulsing glow** keyed to each
character's own color — `.mytheca-glow` / `mythecaGlowPulse` in `styles/themes.css`, driven by
a `--glow-color` custom property set inline per card), and its **active setting is brought
forward** in the Settings column (2px accent border + the same animated glow keyed to
`var(--accent)`) **and scrolled into view** within that column. The glow's own box-shadow
(outside the keyframes) is the animation's brighter frame, so the existing app-wide
`prefers-reduced-motion` rule — which strips `animation` under `.mytheca-themed *` — leaves a
static glow rather than none. Per the not-color-alone rule, both
highlights also carry a mono **"◆ In this scene"** label, and the active setting sets
`aria-current`. A storyline with no scenarios
shows empty-state columns and an empty hero ("No scenarios yet"). This is deliberately a
manuscript "index" surface — not a generic SaaS card grid.

**Card art (Scenario & Setting cards).** When a scenario/setting has generated art, the image
**fills the whole card** behind the shared **`CARD_SCRIM`** "filter" (`lib/cardArt.ts`) — the
same left-dark→right-bright gradient as the hero panel: a near-opaque dark left under the text,
brightening to near-clear on the right so the artwork reads. The card's text (title/name, genre·tone
or type eyebrow, goal/description) is **light** (theme-independent over the dark scrim) and
**width-capped (~58–60%)** so it stays in the dark zone while the art shows on the right; the
Scenario card adds a cast + `◆ setting` footer and a top-right Recent/edit cluster. Cards **without**
art keep the prior solid, theme-aware treatment (Setting's striped "setting plate").

**AA over artwork — now guaranteed, not assumed.** `CARD_SCRIM` is three stacked layers: the
left-dark directional gradient, a bottom reinforcement, and a **flat 10% wash across the whole
card**. The wash is what closed the "near-white art directly behind the text band" edge that this
section used to record as an accepted limitation — it does show up in practice, with bright art
washing out the far end of a title or goal line. A gradient alone cannot fix it without dragging
its dark end so far right that the art stops reading; a flat floor costs the art far less.
Measured against **pure white**, the worst artwork possible:

| Position across the card | Body text, before | Body text, now | Title, now |
| --- | --- | --- | --- |
| 0% | 15.9:1 | 14.9:1 | 16.1:1 |
| 60% (text cap) | **3.5:1 — failed AA** | **8.4:1** | 9.2:1 |
| 78% (title extent) | **2.0:1** | 3.4:1 | **3.7:1** |

Far-right art darkening rose only **28% → 31%**. `OVER_ART.body` also became **opaque**
(`#EFE3CC`); as `rgba(…,0.86)` it composited with the backdrop, so over bright art it lost
contrast from both sides at once — the ink lightening as the ground lightened.

Those numbers are **computed by `lib/cardArt.test.ts`**, not measured by hand: it parses the
scrim strings, composites them over white, and asserts 4.5:1 for capped text, 3:1 for the large
title, **and a ceiling on how much the artwork may be dimmed** — so a future contrast fix cannot
be bought by quietly darkening everything (a first attempt at this one used a 16% wash, hit 50%
darkening, and was caught by exactly that assertion). `PORTRAIT_SCRIM` deliberately gets no wash:
its text is a narrow bottom band already at 0.72–0.92 alpha, and a wash over a portrait would dim
the face for nothing.

**The scrim element must be `absolute inset-0`.** Both constants are `background` values applied
to a sibling div layered between the `SmartImage` and the text. A div carrying only
`pointer-events-none` is an empty in-flow block with **zero height**, so it paints nothing — the
artwork sits directly behind the text and the computed guarantees above describe a layer the
browser never draws. All six scrims (`CharacterCard`, `SettingCard`, `ScenarioCard`,
`ScenarioCarousel` hero + cast tiles, `SceneLoader`) regressed this way at once; the carousel
hero also carried a hand-rolled copy of the gradient and now uses `CARD_SCRIM` like the rest.

## Motion Tokens (the timing system)

**No component may hardcode a duration or an easing.** Inconsistent timing is the single most
common reason a UI reads as scaffolded rather than designed — each animation can look fine on
its own while the set of them feels wrong. The tokens live in one place, `:root` in
`styles/themes.css`, and the full rationale is `docs/frontend-polish-spec.md` §2.

| Token | Value | Use |
| --- | --- | --- |
| `--dur-instant` | 80ms | State flips: press, toggle knob, tab underline |
| `--dur-fast` | 140ms | Hover, focus, tooltip — **and every exit** |
| `--dur-base` | 220ms | Dropdowns, accordions, small reveals, streamed-token fade |
| `--dur-slow` | 340ms | Modals, drawers, page-level entrances |
| `--dur-ambient` | 1200ms | Skeleton sweep, typing dots |
| `--dur-breath` | 2200ms | Slow pulse/travel loops: `.mytheca-glow`, `.mytheca-wash` |
| `--dur-breath-quick` | 1400ms | The tighter "writing here" ring, `.mytheca-field-active` |
| `--dur-theme` | 600ms | The whole-page theme cross-fade (a mood change, not an interaction) |
| `--ease-out` | `cubic-bezier(.16,1,.3,1)` | **Default.** Entrances, reveals |
| `--ease-in` | `cubic-bezier(.45,0,.55,1)` | Exits, dismissals |
| `--ease-soft` | `cubic-bezier(.33,1,.68,1)` | Hover and small state changes |
| `--ease-spring` | `linear(0, .42 12%, .87 24%, 1.05 36%, 1.01 60%, 1)` | One overshoot; sparingly |
| `--lift-sm` / `-md` / `-lg` | 2 / 6 / 14px | Travel distance by element size |
| `--stagger-step` | 50ms | Per-item offset in a choreographed group entrance |

Two rules decide which step to pick:

- **Exits are faster than entrances** (~60%). A dismissal that takes as long as an entrance
  feels like the interface is arguing with the user.
- **Travel scales inversely with size.** A 40px button lifts `--lift-sm`; a full-width card
  lifts `--lift-md`; a modal enters from `--lift-lg`. Large elements moving large distances
  read as sluggish.

**Reaching the tokens from a component.** `app/globals.css` declares `duration-instant` /
`duration-fast` / `duration-base` / `duration-slow` and `ease-soft` / `ease-spring` as Tailwind
utilities. `ease-out` and `ease-in` need no declaration — Tailwind's stock utilities already
emit `var(--ease-out)`, and `themes.css` redefines that variable, so every existing `ease-out`
in the app picks up the Mytheca curve automatically. The `--ease-*` names deliberately are
**not** routed through `@theme inline`: the namespace key collides with the token name and
compiles to a self-referential `--ease-out: var(--ease-out)`. `check_frontend_css.mjs` fails
the build on that pattern.

### Scroll reveals — two paths, four gates, one guarantee

`.reveal` runs an entrance as an element scrolls into view. It has **two implementations** and the
choice between them is made by the browser, not by the call site:

| Path | When | Cost |
| --- | --- | --- |
| `animation-timeline: view()` | the engine supports it (Chromium today) | zero JS, runs on the compositor |
| `IntersectionObserver` (`hooks/use-reveal.ts`) | it does not (Firefox, Safari) | one observer, mounted once in `MotionProvider` |

Before the second path existed, reveals ran **in Chromium only** — everywhere else `.reveal` was inert
and content simply appeared. That was the *correct* failure, but it meant most of the entrance
choreography was invisible to most browsers.

**The guarantee is that nothing can ever be left hidden.** The hidden state requires all four of:

1. `@supports not (animation-timeline: view())` — the JS path never fights the CSS one;
2. `@media (prefers-reduced-motion: no-preference)`;
3. `.js-reveal` on `<html>`, which `useReveal` adds **only after** constructing a working observer;
4. `data-reveal="pending"`, set per element by that observer.

Drop any one — script 404, CSP block, observer throw, reduced motion, an engine with `view()` — and
no rule matches, so the element is simply visible. `useReveal` additionally marks anything already on
screen `shown` immediately (no flash, and deep links landing mid-page are safe), `unobserve`s in the
callback (a 500-item transcript must not recompute geometry forever), uses `threshold: 0` with a px
`rootMargin` (a section taller than the viewport can never reach a fractional threshold; `em`/`vh` in
`rootMargin` throw `SyntaxError`), and re-sweeps on `pageshow` after a bfcache restore.

Use `<Reveal>` for a single element and `<Reveal.Group>` + `<Reveal.Item index={i}>` for a
choreographed sequence, rather than writing the classes and the `--i` property by hand.

Verified 2026-08-31 in Firefox 153 (`view()` unsupported): `.js-reveal` applied, on-screen items
`shown` at opacity 1, the below-fold item `pending` at opacity 0, and revealed on scroll.

### Shared motion utilities (`styles/motion.css`)

Pure CSS, no runtime cost. Framer Motion keeps only the jobs it alone can do —
`AnimatePresence` exits, layout animations, and the transcript beat entrances.

| Class | What it does |
| --- | --- |
| `.hover-lift` / `.hover-lift-md` | Lift + shadow, **gated behind `@media (hover: hover) and (pointer: fine)`** so the state cannot stick on touch |
| `.press` | `:active` scale to 0.985 at `--dur-instant` — the only feedback that exists on touch, so it is never optional |
| `.stagger > *` | Group entrance, `--i` set inline from the index, **capped at 8 items** (400ms cumulative) |
| `.content-enter` | The skeleton → content handoff; also used by error and empty states so failure reads as part of the system |
| `.skeleton` | Layout-tracing placeholder; sweeps `background-position`, never `width` |
| `.tok` | Blur-to-sharp fade on each arriving streamed chunk |
| `.stream-caret` | The 2px block caret at the tail of streaming text |
| `.mytheca-dots` | The shared three-dot thinking indicator (previously re-implemented in three places) |
| `.reveal` | Scroll reveal via `animation-timeline: view()`, behind `@supports` + `prefers-reduced-motion` |
| `.scroll-fade` | Edge fade on a horizontal scroller, driven by `animation-timeline: scroll()` — no scroll listener |

Every one of these keeps its **resting state in the base style**, so the app-wide reduced-motion
rule (which strips `animation` under `.mytheca-themed *`) degrades to something calm rather than
to an empty box. `.reveal` has *no* base styles at all: the revealed state is the default, so
content is visible with or without JS and CSS support.

### Fluid space and display type

`--gutter` and `--step-0…3` (`clamp()`-based) govern page rhythm and display headings, growing
with the viewport instead of jumping at breakpoints. They are surfaced as `gap-gutter`,
`p-gutter`, and `text-step-*`. The six `--fs-*` tokens stay **stepped on purpose** — they are
the user's explicit Text-size preference and must keep winning over anything fluid.

### Recorded deviations from `docs/frontend-polish-spec.md`

1. **The spec's blanket `*` reduced-motion reset is not adopted.** `themes.css` already carries
   a stronger repo-wide rule (`.mytheca-themed *` → `animation: none !important`), and the
   codebase idiom is to put the resting state in the base style. Adding the spec's reset on top
   would be a duplicate of an existing, load-bearing rule.
2. **Scroll-driven reveals apply narrowly.** Mytheca has no root scroll — every route is a
   self-contained `h-dvh` shell whose columns scroll. `.reveal` is used inside those scrollers;
   a scroll **progress bar** and **parallax** are skipped as inapplicable, not forgotten.
3. **Cross-document view transitions are skipped.** App Router navigations are client-side, so
   `@view-transition { navigation: auto }` never fires; Next 16's `experimental.viewTransition`
   would be a stack change. Tracked in `docs/checklist.md`.
4. **Framer Motion is retained** despite the spec's lean toward dropping animation libraries —
   the stack is locked to it and GSAP is banned. Its scope is narrowed, not removed.

## Motion (Framer Motion)

Purposeful only, and always with a near-instant `prefers-reduced-motion` fallback.

- **Beat entrance:** new narration/dialogue/choice beats animate in (`opacity 0 → 1`, `translateY(8px) → 0`, ~0.25s).
- **Card/list entrance:** fade + small rise (~0.18–0.2s).
- **Theme switch:** slow cross-fade of themed surfaces (background/border/color ~0.6s); buttons stay snappy (~0.16s) with a small hover lift (`translateY(-1px)` + soft shadow).
- **Hover affordances:** cards lift `translateY(-2px)`; rows nudge `translateX(2–3px)`.
- **Scenario load:** a full-screen **establishing "curtain"** (`SceneLoader`) that carries the scenario's context — an optional scene-art backdrop behind `CARD_SCRIM` (gradient fallback), the storyline/genre kicker, scenario title, setting + genre/tone, a cast portrait row, the scene goal, and a ❖ "Conjuring the scene…" progress line — then dissolves into the content reveal. Rendered as a plain conditional on the loading flag (the reveal-into-scene continuity comes from the transcript's own opacity/transform transition); navigation between library/scene may use the page-flip transition from the reference (optional, reduced-motion → instant).

**Implementation.** Framer Motion drives the signature **transcript beat entrances** (`StoryPlayerView`, opacity + 8px rise), wrapped in a `MotionConfig reducedMotion="user"` (`components/layout/MotionProvider`) so motion is dropped under `prefers-reduced-motion`. Simpler/continuous motion uses CSS keyframes from `styles/themes.css` — the modal (`embPop`/`embDim`, via Tailwind `motion-reduce:animate-none`), the scene loader (`embSpin`/`embDots`), the theme cross-fade (`.mytheca-page`/`.mytheca-card`/`.mytheca-row`), and the carousel slide. Keyboard focus is shown app-wide via a `:focus-visible` outline in `globals.css`. The full 3D page-flip is deferred.

### Real-time agentic authoring feedback

Every agentic authoring flow (drafting/editing a Character or Setting/Scenario, and generating voice samples, starting stats, or portrait/scene-art prompts) shows **which field is being written at that exact moment**, where the process is, and any error:

- **Active-field highlight** — `.mytheca-field-active` (`styles/themes.css`) rings the field being authored now (`mythecaFieldPulse` on the `--glow-color`, defaulting to `--accent`); the base `box-shadow` lives outside the keyframes so the app-wide `prefers-reduced-motion` rule leaves a **static** ring instead of nothing (same idiom as `.mytheca-glow`).
- **Choreographed reveal** — for the draft endpoints that return the whole result at once, `hooks/use-field-reveal.ts` (and the inline reveal loops in `useLibraryState`) fill fields **one at a time** on a ~150 ms cadence so the author watches them populate; under reduced motion everything appears at once.
- **Process progress** — `components/feature/ProcessProgress.tsx` is a compact done/active/pending stepper with a live `aria-live` "Now … · Next …" line, shown during a draft (character Identity → Voice & tone → Starting stats; setting fields as steps).
- **Notifications** — `components/ui/Toast.tsx` + `components/layout/ToastProvider.tsx` (`useToast`) render **top-right, stacking** toasts in a portal; errors are `role="alert"`, info/success `role="status"`, entrance via `embMsg` with `motion-reduce:animate-none`. Agentic errors across all surfaces raise an error toast (alongside the existing inline `role="alert"` copy). A toast may carry one optional **action button** (e.g. "Undo" for an auto scene-presence change), rendered before the dismiss control.

### In-narrative scene images

The story player's **Create image** action (`CreateImageBar` → `SceneImageBeat` →
`SceneImageModal`) paints the moment the scene is in. Its visual rules:

- **Same object family as scene art.** A picture in the transcript wears the frame the
  setting's establishing shot wears in `SceneArtModal` — `rounded-[6px]`, `border-cardbd`,
  `bg-field`, landscape — so a captured moment and an authored place read as the same kind
  of thing. Style tags in the prompt follow the watercolor look the portrait/scene-art
  agents already establish; only the *composition* is fixed (landscape, everyone in frame).
- **Centered, capped at `max-w-[560px]`** inside the 720 px reading column, with the
  caption below in muted italic under an "A moment in the scene" eyebrow.
- **Painting placeholder** — `.mytheca-wash` (`mythecaWash` in `styles/themes.css`) travels
  a slow gradient across the 3:2 frame the picture will occupy. The gradient lives outside
  the keyframes, so the app-wide `prefers-reduced-motion` rule leaves a **static** wash
  rather than an empty box (the same idiom as `.mytheca-glow` / `.mytheca-field-active`).
- **It only exists between turns.** The control is absent while a turn streams and before
  the first turn of a session, so the transcript's live region is never competing with an
  affordance that would picture a half-played beat. It enters with the same opacity + 8px
  rise the transcript beats use.
- **The image is a control.** The frame is a real `<button>` (pointer *and* keyboard) whose
  accessible name is the caption; the caption is also the `alt`, so the description a
  screen-reader user hears is the one a sighted user reads.

## Storyline Assistant Panel (conversational, scope-aware editing)

The storyline create/edit page (`StorylineCreatorView`) replaced its one-shot "Build the
whole world" hero with a **three-column layout** (at `lg+`): a **left sidebar** holding the
new **Assistant** (`StorylineAgentPanel`), the **by-hand fields in the center**, and a
**right sidebar** holding the existing **Context** (`TriagePanel` — whose upload setup collapses behind a **＋ Add files** disclosure below `lg`, leaving the document list usable height on a stacked layout — + `ContextBudgetMeter`,
hosted `embedded`). Each column scrolls independently; below `lg` they stack (the center form
leads via `order-1`, the two sidebars become bounded strips). No new tokens — the panel reuses
the existing `--field`/`--card` surfaces, `--accent`/gold highlights, and
`Button`/`TextArea`/`ToggleChip` primitives.

- **Scope selector** — one `ToggleChip` pill per writable field (Title · Genre · Tagline ·
  Premise · World Primer · Statistics), each `aria-pressed` to reflect whether the agent
  may write it; Statistics carries a small "schema" note since toggling it authorizes
  add/remove/re-range changes, not just a text edit.
- **Chat transcript** — a `role="log" aria-live="polite"` scrollable region of user/assistant
  message bubbles (mirrors the story-player transcript idiom: player bubble in `--accent`,
  assistant in `--card-bg`); streamed assistant text accumulates in place as `message`
  frames arrive.
- **Plan renderer** — once the agent proposes a change, a reviewable card lists each
  in-scope **field before/after** (label + old value struck or dimmed → new value) with its
  rationale; a **Statistics** change instead lists **per-stat before/after/delta** rows, and
  any **schema-altering** row (add, remove, range/band change) carries a visually distinct
  "schema change" flag (icon + text label, never color alone) so it reads as higher-risk
  than a value tweak.
- **Composer** — a labeled `<textarea>` + a **Send** pill (Enter sends, Shift+Enter newlines
  — the same convention as the story-player composer), disabled while a reply streams.
- **Approve / Refine / New chat** — **Approve** (labeled "Approve & fill form" on create,
  "Approve & apply" on edit) commits the pending plan; **Refine** sends a follow-up
  instruction without discarding the plan card; **New chat** resets the client-session
  message history and any pending plan (a plain button, not destructive-styled — the
  conversation is ephemeral by design, not a stored artifact).

## Writing-Agent Prompt Overrides UI

Three surfaces let authors override the writing-agent prompts at different scopes.

**Options › Prompts tab.** A top-level tab in the `/options` panel (label "Prompts", sub-label
"writing agents") that edits the **global** defaults. It renders a `PromptOverridesEditor` with
the full catalog sourced from `GET /options`. Saving calls `PATCH /options/prompts` with a merge
patch that clears any key the editor has returned to its default (blank clears; non-blank
replaces).

**StorylineMenu gear icon.** A per-row gear icon-button in the header storyline switcher dropdown
(labelled `aria-label="Writing prompts for {title}"`) opens a `PromptOverridesModal` scoped to
that storyline. Saving calls `updateStoryline({ promptOverrides })`.

**EntityModal (scenario editor) "⚙ Writing prompts" button.** Opens the same
`PromptOverridesModal` scoped to the scenario being edited. The override map stages into the
scenario draft (`_promptOverrides`) and persists with the scenario save.

**`PromptOverridesEditor` component.** A reusable editor that:
- Groups the catalog into per-agent **upper sub-tabs** (Character · Narrator · Director · Planner)
  with an ARIA `role=tablist` / `role=tab` / `role=tabpanel` pattern and arrow-key navigation.
- Each prompt row shows the prompt's `label` + `description`, then a `<textarea>`
  (`aria-label`led) pre-filled with the active override or the inherited baseline. A **Reset to
  default** button restores the field to the registry default.
- Overridden prompts (differ from the inherited baseline) carry a badge so the author can see at
  a glance which keys are customized.
- The Character `output_contract` key carries an inline warning that the contract contains strict
  `<speaker:>`/`<type:>` parsing tags — removing them will break the turn parser.
- On Save the editor emits only the layer's overridden (non-blank, differ-from-baseline) keys;
  returning a field to its default causes the key to be omitted (effectively clearing it).
- Uses existing `--field-bg` / `--field-bd` / `--ink` / `--ink-soft` tokens; tab styling matches
  the Options panel's vertical tablist; `TextArea` primitive.

**`PromptOverridesModal` component.** A `Modal` wrapper that fetches the catalog + global
overrides from `GET /options`, layers the passed `baseline` prop on top, and renders
`PromptOverridesEditor`. The modal's save handler is provided by the caller (writes the chosen
scope — global, storyline, or scenario). Uses `Modal`'s `externalClose`. No new design tokens
— all existing primitives and theme variables.

## Meaningful Imagery

Near the top of key pages show **real artifacts**: a live/sample scene transcript, a teal narrator card, a stat/tension panel, a character card with monogram and role — not abstract orbs, mesh gradients, or fake dashboards. The landing page should preview an actual narrator-card + dialogue exchange.

**Character dossier (read-only profile).** The expanded character view (`CharacterProfileModal`) is styled as a **bold, structured dossier** with a **two-column hero** (`md+`, stacking below): the **left** is a tall **2:3 framed portrait** (a 2px character-color frame + inner hairline; `object-cover` image, monogram fallback — no seal medallion); the **right** carries the large uppercase Cinzel name, a character-color role eyebrow set off by a hairline rule, a row of `◆`-led trait pills (the free-text traits string split into one pill per token), and **only the Background** box. The other four fields — **Appearance, Personality, Voice, Goal** — sit below in a **2×2 grid** (one column below `sm`), each in its own bordered manuscript box (`--card-bg2` surface, `--card-bd` border, ~4px radius, a circular gold glyph badge + small-caps header on a rule). **Secret is not surfaced** in the profile (it remains on the data model). Section identity is carried by the badge + header + border, never color alone. All surfaces use theme tokens, so the treatment holds across Parchment / Ember / Slate.

**Generated-image orientation.** Character **portraits** render **vertical — 832×1216 (2:3 portrait)** (`services/portraits.py`), to suit the portrait-dominant character cards and the profile hero; the display frames use `aspect-[2/3]` + `object-cover`. **Scene art** (scenarios + settings) stays **landscape 1024×576 (16:9)**. Both dimensions are divisible by 8 for the latent grid. Character cards in the Library Characters column are **portrait-dominant 2:3 tiles** framed in the character's color: the portrait fills the card behind the vertical **`PORTRAIT_SCRIM`** with name/role in a bottom footer (large monogram fallback on a solid surface), cast members lit by an animated glow in their own color + `◆ In this scene`.

## Required UI States (design all)

loading (scenario loader) · empty · error · partial-data (mid-stream / streaming deltas) · stalled/reconnecting stream · success · permission-denied · long-content · dense-data · hidden-stat (a stat the player isn't allowed to see) · mobile · reduced-motion · **all three themes**.

### The loading state ladder

Match the pattern to the *expected wait*; a mismatch is what reads as unpolished. Full
rationale in `docs/frontend-polish-spec.md` §3.

| Elapsed | Pattern |
| --- | --- |
| 0–300 ms | **Nothing.** `useDelayedFlag` gates every indicator — a flashed-and-gone spinner reads as a stutter, measurably worse than stillness. |
| 300 ms–1 s | An indicator on the element that was acted on (`Button loading`), never a full-screen block. |
| 1–10 s | A **skeleton tracing the incoming layout** (`Skeleton`, `LibrarySkeletons`). |
| >10 s | The skeleton times out into an error with a retry — a shimmer with no ceiling hides a dead request. |

**A skeleton is a tracing, not grey boxes.** Same card count, gaps, radii, and heights as the
real content, and the same *container* queries — `CharacterColumnSkeleton` uses the identical
`@[420px]:grid-cols-3` threshold as the real grid, because a skeleton that reflows on swap
destroys the trust it was built to buy. The last line of a text block runs 55–70% wide.

**Every async region owes five states**, not one: `idle · loading · success · error · empty`.
`AsyncPanel` renders all five so the four that aren't "success" cannot be forgotten. Errors
name what failed in the interface's voice and carry a **retry**; empty states carry their
**primary action inline** (`ColumnEmpty` — and a *filtered*-empty column is treated as the
different problem it is, offering "Clear search" rather than "Forge Character"). Both enter
with the same `.content-enter` as success, so failure reads as part of the system.

**Images** go through `SmartImage`, which fades in on load and checks `img.complete` at the ref
callback — without that, an image already in the browser cache never fires `load` and stays
invisible forever. Two sizing modes, chosen explicitly: `aspect` reserves a frame in normal
flow, and **`fill`** absolutely positions the frame for **card art** — the scenario, setting and
character cards, the carousel hero, and the scene-loader backdrop all paint the image as the
*background of the text*, full-bleed behind `CARD_SCRIM`, with the parent defining the box.
Never pass positioning through `className`: the caller's `absolute` loses to the component's
`relative` (equal specificity, and Tailwind emits `.relative` later), which turns a background
into an in-flow block sitting above the text.

**The scene curtain** (`SceneLoader`) is driven by real readiness, floored at 650 ms so an
instant load does not flash it and capped at 6 s so an unreachable backend cannot hold the
reader behind it. It was previously a blind `setTimeout(2200)`.

### Streaming text

The transcript **follows the newest beat only while the reader is already at the bottom**
(`useStickyBottom`, 64 px tolerance — never an exact test). Scrolling away detaches and raises
the **`JumpToLatest`** pill; scrolling back re-attaches. The viewport sets `overflow-anchor:
none` so the browser's own anchoring does not fight the hook.

Announcements live in a dedicated `sr-only` region (`TranscriptAnnouncer`) that speaks **once
per completed turn**, not on the transcript container. Because delta frames re-emit each
event's *full accumulated text*, a live region on the growing prose asks a screen reader to
re-read the sentence from the beginning on every delta. For the same reason there is **no
per-chunk fade**: the client never sees a chunk boundary. A streaming beat gets a block caret
(`.stream-caret`) and ~2 lines of reserved height so the composer does not hop.

Who is speaking is its own signal, separate from the prose: the **turn status strip** (above) sits under the last beat for the length of the turn, so the reader knows a new speaker was chosen and when the turn is wrapping up without having to infer it from text appearing.

### Responsiveness

**Container queries, not viewport queries, for anything whose width is not the page's.** The
Library's character grid was `sm:grid-cols-3` — at 1024px the Library splits into three
columns, so that grid is ~300px wide while a 640px *viewport* rule had long since fired,
packing three 2:3 portraits in at ~92px each. It now asks its own container.

`dvh`, never `vh`. Touch targets reach 44×44 on **coarse pointers only** — a zero-specificity
floor in `motion.css` grows any control that never expressed a height, while dense controls
that set their own size keep it and gain a projected hit area instead. Horizontal scrollers
carry `.scroll-fade`.

## Anti-Generic Checklist (forbidden unless justified)

- Blue/purple neon gradients, glowing orbs, mesh backgrounds.
- Floating glassmorphism cards as decoration.
- Generic AI brain / sparkle / chat-bubble iconography as identity (use the ❖ seal / ◆ diamond instead).
- Fake metrics and unverifiable dashboards.
- Perfectly centered hero with no product-specific detail.
- Every section reusing the same card grid, heading width, and spacing.
- Conveying status or stat direction by color alone.

## Reference Files

`docs/CharacterFrontpage/` holds the authoritative visual reference (HTML mockups + `support.js`). They are **design reference only** — not the implementation stack. Build the equivalent with Tailwind tokens (the variables above) and Framer Motion; record any deviation from the reference here.

## Beat controls and the take pager

Every transcript beat carries the same control cluster (`BeatControls`), in **one thin bar
under the beat, at its right**, alongside the take pager. It used to be two clusters hanging
off opposite corners — the actions `absolute -top-sm`, *above* the beat, where they overlapped
the beat before them.

The bar is absolutely positioned (`-bottom-sm right-0`), not in flow. An in-flow bar revealed
on hover would push every following beat down as the pointer crossed the transcript.

The rules behind its visibility are worth stating because they are easy to get wrong:

- **Quiet, never hidden.** At `sm` and up the bar sits at `opacity-0` and appears on
  `group-hover` **or** `group-focus-within`. It is never `display: none` — a hidden control is
  out of the tab order, which would make every one of these mouse-only.
- **A beat with more than one take keeps its bar visible.** "1 / 2" is *state*, not an action;
  the player should not have to hover to discover that a beat has another version.
- **Below `sm` the cluster collapses to a single `⋯` trigger** opening a menu of the same
  actions, each with its icon *and its words*. Touch has no hover, so on a phone five 44×44
  targets were 220px of permanently-visible chrome on every beat in the transcript — the same
  mistake `SceneRailBar` was deleted for. An earlier attempt at this was rejected for rendering
  the same action twice (two identical accessible names for one control); this one does not,
  because the rendering is **chosen** by `useMediaQuery("(max-width: 639px)")` rather than
  duplicated and CSS-hidden. That query is `false` on the server and wherever `matchMedia` is
  absent, and that default is deliberate: the wide rendering is the superset, so an unknown
  viewport gets every action present, named and in the tab order.
- **Both renderings are built from one `controls` list**, so an action added to one cannot go
  missing from the other.
- **Targets.** 44×44 for the narrow trigger and for every menu row; 26×26 for the wide
  toolbar's icon buttons, above WCAG 2.5.8's 24.
- **Icons, not text glyphs.** The cluster drew itself with `✎ ⟳ ⟲ ⑂ ↺`, which inherit the font
  stack — different per platform, sized by the type scale rather than by the control — and
  asked the player to tell `⟳` from `⟲` at 12px, which is the same arrow with the head at the
  other end. They are now `Icon` entries on the shared 24 grid: `pencil` `reroll` `rerun`
  `branch` `rewind`, plus `more` for the narrow trigger and `back`/`forward` in the pager.
  `reroll` and `rerun` differ by how much of the circle is drawn, not by which way one
  arrowhead points.
- **Destructive confirms in place; non-destructive does not.** Rewind removes content and
  asks first, naming how many beats go. Branch, edit and re-roll remove nothing and act on one
  click. That asymmetry is the signal — the safe way to explore costs the least. In the narrow
  menu the confirmation replaces the menu's body rather than closing it: the question has to
  land where the finger already is.

`BeatTakePager` ("1 / 2") appears only on a beat with **two or more** takes: one version is
not a choice, and a dead pager on every beat is noise. Its count is an `aria-live="polite"`
region, because flipping a take swaps the prose above it.
