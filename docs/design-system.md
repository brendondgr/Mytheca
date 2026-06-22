# Velora — Design System & Design-Quality Brief

This is the design gate that must be satisfied before broad UI implementation. It follows `docs/skills/ui-frontend/ui/design-quality.md`. The visual language below is **locked** — it is derived from the reference designs in `docs/CharacterFrontpage/` (the "Embergate" front page, home, and live scene). Implement it with the project stack (Next.js + React + TypeScript + **Tailwind CSS** + **Framer Motion**); the tokens here are the source of truth, surfaced to Tailwind as CSS variables.

## Visual Motif

Velora is a **multi-character roleplay chat engine** styled as **a living manuscript — an illuminated codex / tome**. The reading surface is warm parchment; the chrome reads like the cover and rails of an old book; streamed story beats appear like a play script or annotated transcript. Narrator beats are set apart as marginalia/quotes, character lines as bubbles with wax-seal monogram avatars, the player's voice as an inked reply. Avoid sci-fi "AI" clichés entirely.

The recurring identity marks are the **❖ glyph** (`&#10070;`, the "Velora seal") and the **◆ diamond** (`&#9670;`) used as the bullet for branches, settings, and choices.

## Domain Vocabulary (use in copy)

storyline · character · setting · scenario · scene · event · beat · turn · narrator · cast · stat · branch · tone/tension · session. Replace vague phrases ("AI-powered storytelling") with concrete actions: "Begin Scene", "Forge Character", "Add Setting", "New Scenario", "Choose a path", "Speak, or describe what you do".

## Typography

Three families, each with a fixed role. Load via Google Fonts (or self-host equivalently).

| Role | Family | Usage |
| --- | --- | --- |
| Display / headings | **Cinzel** (500/600/700) | Wordmark, storyline/scenario titles, character names, section headers. Letterspaced (`.16em`–`.2em`) for the wordmark and small caps headers. |
| Body / reading | **EB Garamond** (400/500/600 + italic) | All story prose, descriptions, card body, inputs. Narrator prose is **italic**. Line height 1.45–1.55. |
| Labels / metadata | **IBM Plex Mono** (400/500) | Eyebrow labels, role tags, counts, stat values, check labels — uppercase, letterspaced (`.1em`–`.22em`), small (8–11px). |

Rules: body story text ≥ 16px on mobile; reading measure capped (~720px transcript column). Distinguish narrator beats, character turns, and player turns by **typography + layout + a left-accent**, never by color alone.

## Themes & Color Tokens

Three themes ship from day one, switched by a `ThemeSwitcher` and persisted (`localStorage` key `velora-theme`). Themes are CSS-variable token sets on a root class (`.theme-light` / `.theme-dark` / `.theme-slate`); Tailwind colors reference the variables so components are theme-agnostic.

| Token | Parchment (`light`) | Ember (`dark`) | Slate (`slate`) | Purpose |
| --- | --- | --- | --- | --- |
| `--page-bg` | `#E7DBC2` | `#14100A` | `#0F141A` | App background |
| `--page-img` | warm radial wash | ember radial wash | cool radial wash | Subtle page glow (two `radial-gradient`s) |
| `--card-bg` | `#F4ECDA` | `#241C13` | `#1A2129` | Card / bubble surface |
| `--card-bg2` | `#F8F1E0` | `#2E2417` | `#222B35` | Selected / raised surface |
| `--card-bd` | `#D8C7A0` | `#463A24` | `#303C47` | Card border |
| `--hair` | `#E0D2AE` | `#3A2E1E` | `#2A333C` | Hairline divider |
| `--hair-strong` | `#CBB78E` | `#3A2E1E` | `#2A333C` | Stronger divider / rail edge |
| `--ink` | `#2A2016` | `#F1E5CC` | `#E7EDF3` | Primary text |
| `--ink-soft` | `#6B5B45` | `#C3B191` | `#A0B1BF` | Secondary text |
| `--mute` | `#8E7A56` | `#9C875D` | `#6F8495` | Muted labels |
| `--mute2` | `#9A875F` | `#8C774F` | `#5F7384` | Faint labels / placeholders |
| `--field-bg` | `#FBF6EA` | `#1D160F` | `#141A21` | Inputs / icon buttons |
| `--field-bd` | `#CBB78E` | `#463A24` | `#303C47` | Input border |
| `--header-grad` | `linear-gradient(#EFE5CF,#E8DCC3)` | `linear-gradient(#221A11,#1A140C)` | `linear-gradient(#1A222B,#141A21)` | Header / composer bar |
| `--rail-grad` | `linear-gradient(#EBE0C8,#E6DAC0)` | `linear-gradient(#1F1810,#1A140D)` | `linear-gradient(#161D25,#11171E)` | Side rails |
| `--accent` | `#8E2B1C` | `#CC5A41` | `#E0654A` | Primary accent (ember) |

**Theme-agnostic semantic colors** (used across all themes):

- **Gold** `#C8862A` / `#A8762A` — secondary highlight, eyebrow accents, featured tags, check chips.
- **Narrator teal** `#1F8A82` — the narrator card's left border + label; tint `rgba(31,138,130,.12)` for its background.
- **Success / "now" green** `#1F8A5B`.
- **Failure / danger** `#9A3520` (and the accent for "secret"/warning labels).
- **Character colors** — each character carries its own accent (e.g. `#8E2B1C`, `#A8762A`, `#2F7D6B`, `#3A5A78`, `#6B4A8A`, `#5A534A`) used for its monogram ring, name, and role tag.

All text must meet WCAG AA contrast (4.5:1 body, 3:1 large/non-text) **in every theme** — verify Parchment, Ember, and Slate. Status and stat changes are never conveyed by color alone (pair with a label, sign, or icon).

**Frontend implementation.** The three token sets live in `web/frontend/styles/themes.css` as `.theme-light` / `.theme-dark` / `.theme-slate`; the active class sits on `<html>`, applied pre-paint by a no-flash inline script (`themeInitScript` in `lib/theme.ts`). `app/globals.css` maps the variables to Tailwind utilities via `@theme inline` — e.g. `bg-page`, `bg-card`, `bg-card2`, `text-ink`, `text-ink-soft`, `text-mute`, `border-cardbd`, `border-hair`, `text-accent`, plus theme-agnostic `text-gold` / `text-narrator` / `text-success` / `text-danger`. Gradient surfaces (page glow, header, rails) use the `.velora-page` / `.velora-header` / `.velora-rail` helper classes. The current theme is read via `useTheme()` (a `useSyncExternalStore` over the `<html>` class + `localStorage['velora-theme']`, so no provider is needed) and toggled by `ThemeSwitcher`.

## Geometry, Elevation, Icon, Spacing

- **Radius:** cards/inputs/buttons `2–3px` (manuscript-flat); chat bubbles use asymmetric `3px 11px 11px 11px` (character) and `11px 3px 11px 11px` (player); pills/chips `11–20px`; modals/hero `4–6px`; avatars are circles.
- **Borders:** hairline `1px` in `--card-bd`/`--hair`; selected state is a `2px` accent border on `--card-bg2`. Section headers use a thin double rule (`border-top:1px solid ink; border-bottom:1px solid hair-strong`).
- **Elevation:** subtle, warm shadows — cards `0 1px 2px rgba(20,14,6,.06)`, hover `0 6px 16px rgba(40,30,16,.12)`, frames `0 6px 22px rgba(40,30,16,.16)`, modals `0 24px 60px rgba(14,9,4,.55)`. No glassmorphism, no neon glow.
- **Avatars:** monogram circles — character initials in **Cinzel 700**, background `#EDE3CD` (light), `2px` ring in the character's color, text in the character's color. Sizes ~24–62px by context.
- **Icons:** the ❖ seal and ◆ diamond are the brand glyphs; otherwise a single coherent line-icon family. Avoid generic AI brain / sparkle / network-node iconography.
- **Spacing:** consistent rhythm — rails ~16–18px padding, cards ~11–14px, transcript column max-width **720px** centered with 16px gaps between beats.

## Story-Player Layout (the signature surface)

A three-zone "open book": a **left cast rail** (At the table · turn order), a **reading-first center column** (the transcript of beats + a bottom composer), and a **right director rail** (scenario goal · tone/tension meter · scenario state stats · relationships). The transcript is the primary surface and stays centered at ≤720px. On mobile the rails collapse to drawers; the transcript stays primary. This is deliberately **not** a generic three-pane SaaS shell or a card grid.

### Event → component mapping (visual contract)

| Event | Rendering |
| --- | --- |
| `narration` | Teal left-border card (`#1F8A82`), faint teal tint, **italic** EB Garamond, mono "Narrator" eyebrow. |
| `character_dialogue` | Monogram avatar (character color) + Cinzel name in that color + chat bubble (`--card-bg`, asymmetric radius). |
| `character_action` | Inline italic emote next to the name (e.g. *leans in, low*), in `--mute2`. |
| player turn | Right-aligned bubble in `--accent` with `#F6ECDA` text, mono "You" eyebrow. |
| `state_update` (stats) | Updates the right-rail **scenario state chips** (label + signed value, colored by direction) and the tension meter; no chat message. |
| `branch_choices` | Centered "Your move — choose a path" block of ◆ choice rows (label + outcome + optional check tag). |
| check (dice, optional later) | Gold-bordered "d20 check" card with the roll in a gold tile and a Success/Failure pill (`#1F8A5B` / `#9A3520`). |

### Stats & tension display

- **Scenario state chips:** a label (EB Garamond) + a mono value; positive/neutral/negative colored by `--ink-soft`/green/accent. Hidden-visibility stats are omitted from the player's view.
- **Tension/tone meter:** a thin bar with a gold→ember gradient fill and a mono label ("Rising — the room is taut").
- **Relationships:** short lines keyed by character color (relationships and mood are just stats with a relational target).

## Library Layout (the front page)

The Library makes the **Storyline** the organizing object. The header wordmark is followed
by a prominent **storyline switcher** — an outlined button rendering the active storyline in
large Cinzel small-caps (echoing the `VELORA` wordmark) with a ◆ seal and a rotating chevron,
so it reads unmistakably as a dropdown. It lists every storyline (✓ active, with per-storyline
counts) plus "New Storyline"; switching swaps the whole working set. Below the recent-scenario
hero, the body is **three open columns** — **Scenarios** (one per row) · **Characters** (two
per row) · **Settings** (one per row) — shown side-by-side on desktop with hairline dividers.
On `< lg` they collapse to a single column chosen by a 3-tab section switcher (the same ARIA
tablist, `lg:hidden`); each column is rendered exactly once (CSS-only visibility), never
duplicated.

The page is **self-contained** (`h-dvh`, no page scroll): on desktop the column row is pinned
to the viewport and **each column scrolls independently**; on mobile the single active column
scrolls. Each column header is **sticky** so its identity stays visible while its cards scroll.
The columns sit on a **solid `--page-bg`** that spans the full container width — the page's
radial glow (`--page-img`) is never allowed to show through behind the scrolling cards.

Selecting a scenario in the Scenarios column drives the rest: the hero reflects it, its
**cast lights up** in the Characters column (accent border on `--card-bg2`), and its
**active setting is brought forward** in the Settings column (2px accent border + raised
surface) **and scrolled into view** within that column. Per the not-color-alone rule, both
highlights also carry a mono **"◆ In this scene"** label, and the active setting sets
`aria-current`. A storyline with no scenarios
shows empty-state columns and an empty hero ("No scenarios yet"). This is deliberately a
manuscript "index" surface — not a generic SaaS card grid.

## Motion (Framer Motion)

Purposeful only, and always with a near-instant `prefers-reduced-motion` fallback.

- **Beat entrance:** new narration/dialogue/choice beats animate in (`opacity 0 → 1`, `translateY(8px) → 0`, ~0.25s).
- **Card/list entrance:** fade + small rise (~0.18–0.2s).
- **Theme switch:** slow cross-fade of themed surfaces (background/border/color ~0.6s); buttons stay snappy (~0.16s) with a small hover lift (`translateY(-1px)` + soft shadow).
- **Hover affordances:** cards lift `translateY(-2px)`; rows nudge `translateX(2–3px)`.
- **Scenario load:** a centered ❖ spinner with "Conjuring the scene…" then a content reveal; navigation between library/scene may use the page-flip transition from the reference (optional, reduced-motion → instant).

**Implementation.** Framer Motion drives the signature **transcript beat entrances** (`StoryPlayerView`, opacity + 8px rise), wrapped in a `MotionConfig reducedMotion="user"` (`components/layout/MotionProvider`) so motion is dropped under `prefers-reduced-motion`. Simpler/continuous motion uses CSS keyframes from `styles/themes.css` — the modal (`embPop`/`embDim`, via Tailwind `motion-reduce:animate-none`), the scene loader (`embSpin`/`embDots`), the theme cross-fade (`.velora-page`/`.velora-card`/`.velora-row`), and the carousel slide. Keyboard focus is shown app-wide via a `:focus-visible` outline in `globals.css`. The full 3D page-flip is deferred.

## Meaningful Imagery

Near the top of key pages show **real artifacts**: a live/sample scene transcript, a teal narrator card, a stat/tension panel, a character card with monogram and role — not abstract orbs, mesh gradients, or fake dashboards. The landing page should preview an actual narrator-card + dialogue exchange.

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
