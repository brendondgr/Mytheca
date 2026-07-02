# Velora — Design System & Design-Quality Brief

This is the design gate that must be satisfied before broad UI implementation. It follows `docs/skills/ui-frontend/ui/design-quality.md`. The visual language below is **locked** — it is derived from the reference designs in `docs/CharacterFrontpage/` (the "Embergate" front page, home, and live scene). Implement it with the project stack (Next.js + React + TypeScript + **Tailwind CSS** + **Framer Motion**); the tokens here are the source of truth, surfaced to Tailwind as CSS variables.

## Visual Motif

Velora is a **multi-character roleplay chat engine** styled as **a living manuscript — an illuminated codex / tome**. The reading surface is warm parchment; the chrome reads like the cover and rails of an old book; streamed story beats appear like a play script or annotated transcript. Narrator beats are set apart as marginalia/quotes, character lines as bubbles with wax-seal monogram avatars, the player's voice as an inked reply. Avoid sci-fi "AI" clichés entirely.

The recurring identity marks are the **❖ glyph** (`&#10070;`, the "Velora seal") and the **◆ diamond** (`&#9670;`) used as the bullet for branches, settings, and choices. Each **storyline** also carries a **customizable seal** — a simple shape glyph + hex color chosen in a dedicated **seal pop-up** (`SealModal`, opened from a compact Seal row in `StorylineModal`) — rendered left of its name in the switcher. The pop-up offers ~24 shapes, a curated color palette, and a native **color wheel** for any custom hex; the shape/color sets live in `web/frontend/lib/seals.ts` (default: gold `◆`).

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
| `--fs-eyebrow` | 11px | 9px | 12.5px | 14px | `Eyebrow` component (role tags, section kickers, "❖ Draft with Velora" labels) |
| `--fs-label` | 12px | 11px | 13px | 14px | `FieldLabel` headings, form section labels |
| `--fs-ui` | 12px | 11px | 13px | 14px | `Button` text, tab labels |
| `--fs-body-sm` | 14px | 13px | 15px | 16px | Card descriptions, modal body prose |
| `--fs-body` | 15px | 14px | 16px | 17px | Input fields, longer reading text |
| `--fs-tag` | 10.5px | 9px | 11.5px | 12.5px | `Tag` chips (genre, tone, role pills) |

The active preset is stored in `localStorage` key `velora-font-size` (default: `"default"`) and applied as a class on `<html>` (e.g., `.fs-comfortable`) by `lib/font-size.ts`'s no-flash inline script in `app/layout.tsx`. The hook is `useFontSize()` in `hooks/use-font-size.ts`. Tailwind utilities `text-eyebrow`, `text-label`, `text-ui`, `text-body-sm`, `text-body`, `text-tag` resolve from the live CSS variable via `@theme inline` in `globals.css`.

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
- **Character colors** — each character carries its own accent (chosen from a **12-color palette** in `web/frontend/lib/seed-data.ts` `PALETTE`: `#8E2B1C`, `#A8762A`, `#2F7D6B`, `#3A5A78`, `#6B4A8A`, `#5A534A`, `#1F8A5B`, `#B0506A`, `#C56A1F`, `#7E8A2B`, `#2C8E8E`, `#8E3B7A`) used for its monogram ring, name, and role tag.

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

A three-zone "open book": a **left cast rail** (At the table · turn order, portrait avatars), a **reading-first center column** (a `SceneIntro` "scene is set" band — setting, genre/tone, the player's aim, dramatis personae — then the transcript of beats + a bottom composer — whose input is flanked on the **left** by two compact labeled dropdowns (`SceneControlSelect`: "Max turns" 1–10, "Suggestions" 0–4) that set + persist the per-scene turn limit and follow-up count), and a **right director rail** (scenario goal · tone/tension meter · the storyline's **stat schema** with labeled bands · live scene-state stats · relationships). The transcript is the primary surface and stays centered at ≤720px; the `SceneIntro` band ensures the reading column carries the full scene context even on mobile, where the rails collapse to drawers. This is deliberately **not** a generic three-pane SaaS shell or a card grid.

### Event → component mapping (visual contract)

| Event | Rendering |
| --- | --- |
| `narration` | Teal left-border card (`#1F8A82`), faint teal tint, **upright** EB Garamond (not italic), mono "Narrator" eyebrow. |
| `character_dialogue` | Monogram avatar (character color) + Cinzel name in that color + chat bubble (`--card-bg`, asymmetric radius). |
| `character_action` | Short **upright** label (5–10 words, not italic) next to the name, in `--mute2` (e.g. "leans in, low"). |
| `internal_thought` | **Folded into the speaker's beat**, not a separate bubble: a muted "thinking" line (mono `thinks` tag + `--ink-soft`, ~13px — slightly smaller than the 15.5px speech) sits between the character's name and their spoken bubble, so one message shows what they think, then what they say. |
| player turn | Right-aligned bubble in `--accent` with `#F6ECDA` text, mono "You" eyebrow. |
| `state_update` (stats) | Updates the Director rail's **Scene-state chips** (label + signed value, colored by direction; the change `reason` rides as the chip's title) AND the open **character dossier's** stat sliders, which are value-aware: the thumb, floating readout, and band title track that character's live per-`characterId` value (falling back to the schema default until it first moves). No chat message. |
| `branch_choices` | Centered "Your move — choose a path" block of ◆ choice rows (**label + outcome only** — no dice/check, D11). 1–2 choices stack in a column; **3–4 lay out in a 2-column grid** (4 → a 2×2 grid). Selecting a row submits a real turn steered **open-endedly** by `guidance` (not a scripted play-out). |

### Turn Inspector (diagnostic panel)

A docked right-side column (opt-in `trace` frames) that shows, per message, what the turn
loop did and why. Turns are an **accordion** — the active (newest) turn is expanded, completed
turns collapse to a clickable header. Each step is a **colored dot on the left + a short tag +
title**, and clicking a step expands a dropdown to reveal its plain-language detail. The dot
colour categorises the step (Intent / Plan / Speaker / Thinks / Speaks / Stat / Bond / …) but
is always **paired with the text tag**, so meaning never rests on colour alone (WCAG 1.4.1).
Read-only — the panel never changes the scene.

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
character's own color — `.velora-glow` / `veloraGlowPulse` in `styles/themes.css`, driven by
a `--glow-color` custom property set inline per card), and its **active setting is brought
forward** in the Settings column (2px accent border + the same animated glow keyed to
`var(--accent)`) **and scrolled into view** within that column. The glow's own box-shadow
(outside the keyframes) is the animation's brighter frame, so the existing app-wide
`prefers-reduced-motion` rule — which strips `animation` under `.velora-themed *` — leaves a
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

**Implementation.** Framer Motion drives the signature **transcript beat entrances** (`StoryPlayerView`, opacity + 8px rise), wrapped in a `MotionConfig reducedMotion="user"` (`components/layout/MotionProvider`) so motion is dropped under `prefers-reduced-motion`. Simpler/continuous motion uses CSS keyframes from `styles/themes.css` — the modal (`embPop`/`embDim`, via Tailwind `motion-reduce:animate-none`), the scene loader (`embSpin`/`embDots`), the theme cross-fade (`.velora-page`/`.velora-card`/`.velora-row`), and the carousel slide. Keyboard focus is shown app-wide via a `:focus-visible` outline in `globals.css`. The full 3D page-flip is deferred.

### Real-time agentic authoring feedback

Every agentic authoring flow (the New Storyline **Build the whole world**, drafting/editing a Character or Setting/Scenario, and generating voice samples, starting stats, or portrait/scene-art prompts) shows **which field is being written at that exact moment**, where the process is, and any error:

- **Active-field highlight** — `.velora-field-active` (`styles/themes.css`) rings the field being authored now (`veloraFieldPulse` on the `--glow-color`, defaulting to `--accent`); the base `box-shadow` lives outside the keyframes so the app-wide `prefers-reduced-motion` rule leaves a **static** ring instead of nothing (same idiom as `.velora-glow`).
- **Choreographed reveal** — for the draft endpoints that return the whole result at once, `hooks/use-field-reveal.ts` (and the inline reveal loops in `useLibraryState`) fill fields **one at a time** on a ~150 ms cadence so the author watches them populate; under reduced motion everything appears at once. The world-build page drives the same highlight from its real NDJSON stream (`meta`/`primer` → left fields, `character`/`setting` → the active card in `WorldBuildPanel`).
- **Process progress** — `components/feature/ProcessProgress.tsx` is a compact done/active/pending stepper with a live `aria-live` "Now … · Next …" line, shown during a build/draft (build stages; character Identity → Voice & tone → Starting stats; setting fields as steps).
- **Notifications** — `components/ui/Toast.tsx` + `components/layout/ToastProvider.tsx` (`useToast`) render **top-right, stacking** toasts in a portal; errors are `role="alert"`, info/success `role="status"`, entrance via `embMsg` with `motion-reduce:animate-none`. Agentic errors across all surfaces raise an error toast (alongside the existing inline `role="alert"` copy).

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
