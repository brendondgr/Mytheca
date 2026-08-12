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

## Typography

Three families, each with a fixed role. Load via Google Fonts (or self-host equivalently).

| Role | Family | Usage |
| --- | --- | --- |
| Display / headings | **Cinzel** (500/600/700) | Wordmark, storyline/scenario titles, character names, section headers. Letterspaced (`.16em`–`.2em`) for the wordmark and small caps headers. |
| Body / reading | **EB Garamond** (400/500/600 + italic) | All story prose, descriptions, card body, inputs. Narrator prose and the character action label are **upright** (not italic) — kept muted, not slanted, for legibility. Line height 1.45–1.55. |
| Labels / metadata | **IBM Plex Mono** (400/500) | Eyebrow labels, role tags, counts, stat values, check labels — uppercase, letterspaced (`.1em`–`.22em`). |

Rules: body story text ≥ 16px on mobile; reading measure capped (~720px transcript column). Distinguish narrator beats, character turns, and player turns by **typography + layout + a left-accent**, never by color alone.

### Typography Scale (font-size presets)

Text sizes are driven by six CSS custom properties defined in `styles/themes.css` under `:root`, with four named preset classes that the user chooses from **Settings → Appearance → Text size**:

| CSS variable | Default | Compact | Comfortable | Large | Used for |
| --- | --- | --- | --- | --- | --- |
| `--fs-eyebrow` | 10px | 9px | 12px | 13.5px | `Eyebrow` component (role tags, section kickers, "❖ Draft with Mytheca" labels) |
| `--fs-label` | 12px | 11px | 13px | 14px | `FieldLabel` headings, form section labels |
| `--fs-ui` | 12px | 11px | 13px | 14px | `Button` text, tab labels |
| `--fs-body-sm` | 14px | 13px | 15px | 16px | Card descriptions, modal body prose |
| `--fs-body` | 15px | 14px | 16px | 17px | Input fields, longer reading text |
| `--fs-tag` | 9.5px | 9px | 11px | 12px | `Tag` chips (genre, tone, role pills) |

The active preset is stored in `localStorage` key `mytheca-font-size` (default: `"default"`) and applied as a class on `<html>` (e.g., `.fs-comfortable`) by `lib/font-size.ts`'s no-flash inline script in `app/layout.tsx`. The hook is `useFontSize()` in `hooks/use-font-size.ts`. Tailwind utilities `text-eyebrow`, `text-label`, `text-ui`, `text-body-sm`, `text-body`, `text-tag` resolve from the live CSS variable via `@theme inline` in `globals.css`.

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

- **Radius:** cards/inputs/buttons `2–3px` (manuscript-flat); chat bubbles use asymmetric `3px 11px 11px 11px` (character) and `11px 3px 11px 11px` (player); pills/chips `11–20px`; modals/hero `4–6px`; avatars are circles.
- **Borders:** hairline `1px` in `--card-bd`/`--hair`; selected state is a `2px` accent border on `--card-bg2`. Section headers use a thin double rule (`border-top:1px solid ink; border-bottom:1px solid hair-strong`).
- **Elevation:** subtle, warm shadows — cards `0 1px 2px rgba(20,14,6,.06)`, hover `0 6px 16px rgba(40,30,16,.12)`, frames `0 6px 22px rgba(40,30,16,.16)`, modals `0 24px 60px rgba(14,9,4,.55)`. No glassmorphism, no neon glow.
- **Avatars:** monogram circles — character initials in **Cinzel 700**, background `#EDE3CD` (light), `2px` ring in the character's color, text in the character's color. Sizes ~24–62px by context.
- **Icons:** the ❖ seal and ◆ diamond are the brand glyphs; otherwise a single coherent line-icon family. Avoid generic AI brain / sparkle / network-node iconography.
- **Spacing:** consistent rhythm — rails ~16–18px padding, cards ~11–14px, transcript column max-width **720px** centered with 16px gaps between beats.

## Story-Player Layout (the signature surface)

A three-zone "open book": a **left cast rail** (At the table · turn order, portrait avatars with per-character **"Thinking"/"Speaking"** activity indicators), a **reading-first center column** (a `SceneIntro` "scene is set" band — setting, genre/tone, the player's aim, dramatis personae — then the transcript of beats and a **two-row composer**), and a **right director rail** (a live **"Scene pulse"** activity feed + scene-state chips). The per-scene **Config** (gear button → popover with "Max turns" 1–10, "Suggestions" 0–4, and a "Number of beats" 5–100 slider) now lives in the composer's **bottom-left controls row**, not the header. The transcript is the primary surface and stays centered at ≤720px; the `SceneIntro` band ensures the reading column carries the full scene context even on mobile, where the rails collapse to drawers. This is deliberately **not** a generic three-pane SaaS shell or a card grid.

**Graph view mode.** The `SceneHeader` carries a compact **Chat ⇄ Graph** segmented switch (left of Export). Switching to **Graph** replaces the center transcript+composer column with `GraphView` — the scenario's Story-Graph as a force-directed canvas (`react-force-graph-2d`), nodes/edges colored by type (see the Story-Graph node/edge colors bullet above) with an sr-only node/edge table. The cast rail stays; the Director rail + Turn Inspector are replaced by the **`GraphInspectorPanel`** right rail. The graph is fetched (and its renderer chunk loaded) only on first switch, and shows a calm "offline" state when the graph DB is down. **Graph Inspector:** with nothing selected it shows the **type breakdown** (node types and edge types, each `swatch · type · count`); **clicking a node or edge** highlights it on the canvas (selection ring / thicker link) and switches the rail to that element's **properties** (its `metadata`, a colored type badge, name-resolved edge endpoints), with a **Back** button to the overview; clicking the background clears. It is an author-facing diagnostic (like the Turn Inspector), so it surfaces every property the graph carries. Mirrors the `DirectorRail` shell (`hidden … lg:block`), so on `< lg` the graph shows canvas-only (the sr-only table remains the data alternative).

**Context usage dial.** A small (24 px) circular **button** (`ContextUsageDial`) in the composer's bottom controls row, immediately left of Send, visible only when the model's context-window size is known. The ring fills with `used / max` and is stroke-coloured by the same token-driven thresholds — `--color-success` (green) below 50 %, `--color-gold` at 50–75 %, `--color-danger` at or above 75 %. The ring is **purely visual — no number in the centre**; the count surfaces only on **hover / keyboard-focus**, in a tooltip above the dial reading `"8.3K of 16K tokens · 56% · exact"`. That same text is the button's `aria-label`, so the exact figure and its provenance (the model's reported `usage.prompt_tokens` vs. a char/4 estimate) are always available non-visually. The arc transition is `motion-reduce:transition-none`. It replaced the earlier slim full-width **context usage bar**.

**Two-row composer.** The composer is a transparent outer band wrapping a centered `max-w-[720px]` chat panel (`rounded-[14px]`, `border-field-bd bg-field` surface, `focus-within` accent ring) that reads as **one continuous unit**: a compact auto-growing `<textarea rows=1>` (full width; expands to `scrollHeight` capped at 240 px ≈10 lines, then scrolls), then a small **gap** (no dividing line), then the controls bar. The textarea's boxy `:focus-visible` outline is suppressed (a `.composer-input` opt-out from the global focus outline); focus shows as the panel's `focus-within` accent border **plus a 2 px inset accent bar down the focused field's leading edge**. The bar is per-field on purpose — under Player POV the panel holds two textareas, and a panel-level ring alone cannot say which one you are in. **Scene direction (Player POV only).** A second, shorter textarea sits **above** the message box, separated by a hairline `border-field-bd` rule: `13 px`/`text-mute`, placeholder "Guide the scene — what happens next…", growing to a 120 px cap (half the message box's — direction is a note to the scene, not the line you are performing) and then scrolling. The panel grows **upward**, so opening it lifts the transcript rather than covering it. It is hidden in narrator mode, where the message box already carries the direction. The controls bar holds **Config** on the bottom-left (rounded button; popover opens **upward** — `openUp` — so it clears the screen edge; the "Number of beats" readout reflects the **real** recent transcript when `beatTexts` is supplied), then the **Player POV "Speaking as" select** (`PovSelect`) immediately to its right, a flexible blank gap reserved for future options, then on the right the **context dial** and a small **"Send →" pill** (`bg-accent`, `Send` label + right-arrow SVG, `aria-label="Send"`). Everything in the controls bar is deliberately small/quiet so the panel stays low-profile. The **`PovSelect`** is a compact **custom dropdown** whose trigger matches the Config pill (a small **portrait avatar** of the current POV + its mono/uppercase name + a caret; `min-w-0`/`truncate` so it shrinks rather than overflowing on a 320 px composer row, showing "M…" at the extreme). Clicking it opens an **upward** `role="menu"` popover whose rows each carry the character's **portrait avatar (monogram-initials fallback) + name** — "Narrator" (a mask glyph) plus each present cast member — with the active row accent-tinted + checked. The textarea placeholder follows the selection ("Speaking as Mei…"). Enter sends; Shift+Enter inserts a newline; the textarea stays editable while a turn streams (only Send + Enter are blocked via `sendDisabled`).

**Player-POV character bubble.** When the player speaks *as* a character (Player POV), their line renders on the player's side of the transcript (right-aligned, like the ordinary player bubble) but wears the character's identity: a header of the character's `Monogram` + name in the character's color, above the **same `--accent` bubble with `#F6ECDA` text** as `PlayerMessage`. The accent fill is kept deliberately (rather than tinting the bubble with the character's color) so contrast stays AA regardless of how light a character's color is — only the header carries the character color, on the parchment background where cast colors are already used for names/roles. This is the sole right-aligned *character* variant; a left-aligned `CharacterMessage` remains the AI-voiced form.

**Scene pulse (Director rail).** The static Scene Goal, TensionMeter, and Relationships sections were replaced by a **"Scene pulse"** live feed: a `role="log"` `aria-live="polite"` scrollable region (`max-h` capped, newest entry first) of up to 12 `ActivityEntry` items. Each entry is a compact line with character-colored name, a status verb, and optional detail text; entries animate in with the transcript beat-entrance idiom (opacity + 8 px rise, `motion-reduce` safe). An idle empty state reads **"The scene is quiet — your move."**. The `StateChips` scene-state block is kept beneath the feed.

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
art keep the prior solid, theme-aware treatment (Setting's striped "setting plate"). **AA note:**
over typical mid-tone watercolor art the capped left-side text clears AA (measured ~14–17:1 over
the scrim base; the active `◆ In this scene` marker ~9:1); near-white art directly behind the text
band is the known edge — accepted as a deliberate, requested look, mitigated by the strong scrim +
width cap (mirrors the hero scrim).

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
- **The image is a control.** The frame is a real `<button>` (pointer *and* keyboard) whose
  accessible name is the caption; the caption is also the `alt`, so the description a
  screen-reader user hears is the one a sighted user reads.

## Storyline Assistant Panel (conversational, scope-aware editing)

The storyline create/edit page (`StorylineCreatorView`) replaced its one-shot "Build the
whole world" hero with a **three-column layout** (at `lg+`): a **left sidebar** holding the
new **Assistant** (`StorylineAgentPanel`), the **by-hand fields in the center**, and a
**right sidebar** holding the existing **Context** (`TriagePanel` + `ContextBudgetMeter`,
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
