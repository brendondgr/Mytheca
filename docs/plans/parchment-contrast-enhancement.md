# Parchment Light Theme Contrast Enhancement

## Introduction

The Parchment (`.theme-light`) theme currently lacks visual hierarchy — all surfaces share nearly identical warm-tan values, making it difficult to distinguish structural chrome (header bar, side rails) from the reading content area (cards, transcript). The goal is to introduce darker warm-brown tones for chrome surfaces, drawing from Ember's deep-brown palette but using lighter, mid-range values so the result is a richly contrasted manuscript look rather than a second dark theme. Borders and hair dividers are also strengthened throughout to make column and card boundaries clearly legible.

The approach: (1) strengthen card borders and hair dividers across the board — immediate visible improvement with no component changes; (2) add a `--chrome-ink` family of tokens for text on dark surfaces and map them as Tailwind utilities; (3) darken the header gradient to a rich book-spine brown and update the five header-bearing components accordingly; (4) darken the rail gradient to a medium warm-brown and update rail component text; (5) validate WCAG AA contrast, run tests, and update docs.

## Gaps & Unanswered Questions

- **Rail tone selection**: Ember's rail is `#1F1810` (near-black). We target `linear-gradient(#7A5A38, #6A4C2C)` — medium dark warm brown (luminance ≈ 0.09–0.13). Body text directly on this rail background requires light chrome-ink tokens (≥ 4.5:1). *Assumption: this level is acceptable and mirrors how Ember handles its rails.*
- **Accent color on dark header**: `--accent: #8E2B1C` (dark red) is invisible on the new dark header. The ❖ decorative seal and "‹ Library" button currently use `text-accent` in header contexts. These are changed to `text-chrome-ink` for base state; hover accent fills are preserved as-is. *No change to `--accent` itself — it works fine on parchment card surfaces.*
- **Modal bg**: `--modal-bg` is the modal panel background (not the overlay). Modal content uses `text-ink`/`text-ink-soft` extensively, so it must remain light. New value: `#E8D9BA` (slightly richer amber tan, still light).
- **Composer**: Uses `mytheca-header` as a bottom tray. All interactive elements inside it have explicit `bg-field`/`bg-accent` backgrounds. No bare text sits on the header background — *no component changes needed for Composer.*

---

## Phase 1 — Core contrast tokens + chrome-ink family

No component changes. Only CSS token files.

### 1a. `web/frontend/styles/themes.css` — `.theme-light` block (lines 10–30)

Strengthen borders and dividers:
- `--card-bd`: `#D8C7A0` → `#A88860`
- `--field-bd`: `#CBB78E` → `#A88860`
- `--hair`: `#E0D2AE` → `#C8A070`
- `--hair-strong`: `#CBB78E` → `#8A6A3C`

Enrich modal and page glow:
- `--modal-bg`: `#EEE3CC` → `#E8D9BA`
- `--page-img`: change top radial stop to `rgba(255,248,230,0.75)` and bottom stop to `rgba(140,100,44,0.12)`

Add new chrome-ink tokens (text for dark chrome backgrounds):
- `--chrome-ink: #F0E4C8`
- `--chrome-ink-soft: #DCC290`

### 1b. `web/frontend/styles/themes.css` — `.theme-dark` and `.theme-slate` blocks

Add matching chrome-ink tokens so the Tailwind utilities resolve correctly on dark themes (values mirror existing `--ink`/`--ink-soft`):

In `.theme-dark`:
- `--chrome-ink: #F1E5CC`
- `--chrome-ink-soft: #C3B191`

In `.theme-slate`:
- `--chrome-ink: #E7EDF3`
- `--chrome-ink-soft: #A0B1BF`

### 1c. `web/frontend/app/globals.css` — `@theme inline` block

After the `--color-tab-ink` line, add:
```
--color-chrome-ink: var(--chrome-ink);
--color-chrome-ink-soft: var(--chrome-ink-soft);
```

This surfaces `text-chrome-ink` and `text-chrome-ink-soft` as Tailwind utilities.

**Validation & Commit**
> Run `npm run typecheck` to confirm CSS compiles. Once green, commit:
> `[Parchment Contrast] (1/4) Complete: Core border/hair tokens, page-img richer, chrome-ink family added`

---

## Phase 2 — Dark header gradient + header component updates

### 2a. `web/frontend/styles/themes.css` — `.theme-light`

- `--header-grad`: `linear-gradient(#EFE5CF, #E8DCC3)` → `linear-gradient(#3E2C18, #302110)`

### 2b. Component updates — mytheca-header surfaces

All four header-bearing components need their on-header text classes updated (Composer is excluded — see Gaps).

**`web/frontend/components/layout/AppHeader.tsx`**
- ❖ seal (decorative, `text-accent`) → `text-chrome-ink`
- MYTHECA wordmark (`text-ink`) → `text-chrome-ink`
- Search icon is inside a `bg-field` input container — no change needed.

**`web/frontend/components/layout/SceneHeader.tsx`**
- ‹ Library button: `border-field-bd text-accent` → `border-chrome-ink text-chrome-ink`
  (hover/focus: `hover:bg-accent hover:text-[#F6ECDA]` stays unchanged — accent fill looks good on dark bg)
- Vertical separator `bg-hair-strong` — no text, fine as-is
- Scene title (`text-ink`) → `text-chrome-ink`
- Setting subtitle (`text-mute`) → `text-chrome-ink-soft`
- "Narrator active" status text (`text-mute`) → `text-chrome-ink-soft`

**`web/frontend/features/options/OptionsView.tsx`** (header block only, ~lines 48–58)
- ❖ seal (`text-accent`) → `text-chrome-ink`
- MYTHECA wordmark (`text-ink`) → `text-chrome-ink`
- "Options" label (`text-mute`) → `text-chrome-ink-soft`

**Validation & Commit**
> Run `npm run typecheck` and `npm test`. Once green, commit:
> `[Parchment Contrast] (2/4) Complete: Dark header gradient, chrome-ink text on AppHeader + SceneHeader + OptionsView`

---

## Phase 3 — Dark rail gradient + rail component updates

### 3a. `web/frontend/styles/themes.css` — `.theme-light`

- `--rail-grad`: `linear-gradient(#EBE0C8, #E6DAC0)` → `linear-gradient(#7A5A38, #6A4C2C)`

### 3b. `web/frontend/components/feature/CastRail.tsx`

Text elements on the rail background (not inside `bg-card` buttons):
- `TurnOrder` Eyebrow "Turn order" (~line 15): add `color="var(--chrome-ink-soft)"`
- CastRail Eyebrow "At the table" (~line 60): add `color="var(--chrome-ink-soft)"`
- Character row buttons have explicit `bg-card`/`bg-card2` — no text changes needed.

### 3c. `web/frontend/components/feature/DirectorRail.tsx`

Text elements directly on the rail background:
- `TensionMeter` label (`text-accent` ~line 34): `text-accent` → `text-chrome-ink`
  (accent dark red `#8E2B1C` is invisible on dark rail; label describes the meter, not a status)
- DirectorRail Eyebrow "Scene goal" (~line 89): add `color="var(--chrome-ink-soft)"`
- Goal paragraph `text-ink italic` (~line 92): `text-ink` → `text-chrome-ink`
- Eyebrow "Tension" (~line 94): add `color="var(--chrome-ink-soft)"`
- Eyebrow "Scene state" (~line 99): add `color="var(--chrome-ink-soft)"`
- Eyebrow "Relationships" (~line 104): add `color="var(--chrome-ink-soft)"`
- `Relationships` paragraph `text-ink-soft` (~line 62): `text-ink-soft` → `text-chrome-ink-soft`
- `StateChips` items have explicit `bg-card border-cardbd` — no text changes needed.

**Validation & Commit**
> Run `npm run typecheck` and `npm test`. Once green, commit:
> `[Parchment Contrast] (3/4) Complete: Dark rail gradient, chrome-ink text in CastRail + DirectorRail`

---

## Phase 4 — Contrast audit, final validation, docs update

### 4a. WCAG AA contrast verification

Manually verify these critical pairs in the Parchment theme using browser devtools or a contrast checker:

| Text token | Value | Background | Approx BG value | Required | Expected |
|---|---|---|---|---|---|
| `--ink` | `#2A2016` | `page-bg` | `#E7DBC2` | 4.5:1 | ~12:1 ✓ |
| `--ink` | `#2A2016` | `card-bg` | `#F4ECDA` | 4.5:1 | ~13:1 ✓ |
| `--ink-soft` | `#6B5B45` | `card-bg` | `#F4ECDA` | 4.5:1 | ~5.5:1 ✓ |
| `--chrome-ink` | `#F0E4C8` | `header-grad` | ~`#3E2C18` | 4.5:1 | ~5.0:1 ✓ |
| `--chrome-ink` | `#F0E4C8` | `rail-grad` | ~`#7A5A38` | 4.5:1 | ~4.7:1 ✓ |
| `--chrome-ink-soft` | `#DCC290` | `rail-grad` | ~`#7A5A38` | 4.5:1 | ~4.5:1 ✓ |
| `--accent` | `#8E2B1C` | `card-bg` | `#F4ECDA` | 3:1 (UI) | ~5.5:1 ✓ |

If any pair fails, adjust the token value to the minimum passing level before committing.

### 4b. Test suite

- `npm test` — all Vitest component/route tests pass
- `npm run typecheck` — no TypeScript errors

### 4c. `docs/design-system.md`

Update the **Themes & Color Tokens** table (the markdown table starting "| Token | Parchment..."):
- Update `--card-bd`, `--hair`, `--hair-strong`, `--header-grad`, `--rail-grad`, `--modal-bg` values for the Parchment column
- Add new rows for `--chrome-ink` and `--chrome-ink-soft` (all three themes)
- Add a note under the table: *`--chrome-ink` / `--chrome-ink-soft` are used for text that sits directly on dark chrome surfaces (header bar, side rails) in all three themes. In Ember and Slate, they equal `--ink` / `--ink-soft` since those themes already use light text everywhere.*
- Update the "Frontend implementation" paragraph to mention `text-chrome-ink` / `text-chrome-ink-soft` alongside existing utilities.

**Validation & Commit**
> Run `npm test` and `npm run typecheck` for final green. Commit:
> `[Parchment Contrast] (4/4) Complete: WCAG audit, full test pass, design-system.md updated`

---

## Deliverables Table

| Deliverable | Description | Location |
|---|---|---|
| Theme token updates | Stronger borders/hair, richer page-img, dark header-grad, dark rail-grad, modal-bg | `web/frontend/styles/themes.css` |
| Chrome-ink tokens | `--chrome-ink` + `--chrome-ink-soft` in all three themes | `web/frontend/styles/themes.css` |
| Tailwind utility additions | `text-chrome-ink`, `text-chrome-ink-soft` mapped from tokens | `web/frontend/app/globals.css` |
| AppHeader chrome | MYTHECA wordmark + ❖ seal on dark header | `web/frontend/components/layout/AppHeader.tsx` |
| SceneHeader chrome | Scene title, setting subtitle, ‹ Library button on dark header | `web/frontend/components/layout/SceneHeader.tsx` |
| OptionsView chrome | MYTHECA wordmark, ❖ seal, "Options" label on dark header | `web/frontend/features/options/OptionsView.tsx` |
| CastRail chrome | Section eyebrow labels on dark rail | `web/frontend/components/feature/CastRail.tsx` |
| DirectorRail chrome | Goal text, tension label, relationship text, all eyebrows on dark rail | `web/frontend/components/feature/DirectorRail.tsx` |
| Design system docs | Updated token table + chrome-ink entries + frontend impl note | `docs/design-system.md` |
