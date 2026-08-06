# Typography Scale & Font-Size Settings

## 1. Introduction

Mytheca's UI uses heavily-hardcoded font sizes scattered across components, many of which are uncomfortably small — the `Eyebrow` component defaults to 10px and is frequently called at `size={8.5}` or `size={9}` (metadata labels, card eyebrows, "❖ Draft with Mytheca" section headers). The `Tag` component sits at `text-[9.5px]` and the `Button` text is `text-[11px]` uppercase — all technically valid for a dense manuscript aesthetic but routinely forcing users to squint. The body text on cards (`text-[14px]`) is workable but not generous.

The fix is two-layered: **(1)** introduce a CSS variable typography scale (`--fs-eyebrow`, `--fs-label`, `--fs-ui`, `--fs-body-sm`, `--fs-body`, `--fs-tag`) with four size presets (Compact / Default / Comfortable / Large) stored on `<html>` alongside the theme class and persisted to `localStorage`; **(2)** update the handful of primitive components (`Eyebrow`, `Tag`, `Button`) and the key card/modal call sites to consume those variables instead of hardcoded px values. Default preset ships at sizes that are visibly more readable than today's hardcoded values. The AppearanceTab in Options gains a font-size preset picker so users can choose their preferred density.

This is a **frontend-only** change (no backend, no schema, no API contract changes). Five phases, commit per phase, branched off `main`.

---

## 2. Gaps & Unanswered Questions

- **Default preset values** — the user wants "not huge, just not squinting." Default ships at `--fs-eyebrow: 11px` (up from 8.5–9px hardcoded), `--fs-ui: 12px`, `--fs-body-sm: 14px`, `--fs-body: 15px`, `--fs-tag: 10.5px`. This is a conservative bump; Comfortable adds another ~1–2px. Assumption is this is acceptable — user can adjust via the picker if not.
- **Display/heading sizes** — Cinzel headings (`text-[16px]`, `text-[19px]`, `text-[26px]`) are not part of the complaint and are already readable. They are **excluded** from the scale for now.
- **"Draft with Mytheca" label** — currently rendered as `<Eyebrow size={8.5}>` (8.5px uppercase mono). Will be fixed by removing the explicit `size` override so it inherits `--fs-eyebrow` (~11px). No need to change the element type.
- **Worktree** — a dedicated worktree at `.claude/worktrees/typography-scale/` is recommended to avoid conflict with any other session on `main`.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — CSS Typography Token Infrastructure

**Goal:** add `--fs-*` CSS variables and `.fs-*` preset classes to the theme system; map them into Tailwind.

#### Step 1.1: Add `--fs-*` defaults and preset classes to `styles/themes.css`

- **Location:** `web/frontend/styles/themes.css`
- **What:** Append a `:root` block defining six `--fs-*` variables at the **Default** preset values. Then add four named preset classes (`.fs-compact`, `.fs-default`, `.fs-comfortable`, `.fs-large`) that override those six variables. Preset classes sit on `<html>` alongside `.theme-*` — they do not conflict.
- **Values:**

  | Variable | compact | default (`:root`) | comfortable | large |
  |---|---|---|---|---|
  | `--fs-eyebrow` | 9px | 11px | 12.5px | 14px |
  | `--fs-label` | 11px | 12px | 13px | 14px |
  | `--fs-ui` | 11px | 12px | 13px | 14px |
  | `--fs-body-sm` | 13px | 14px | 15px | 16px |
  | `--fs-body` | 14px | 15px | 16px | 17px |
  | `--fs-tag` | 9px | 10.5px | 11.5px | 12.5px |

- **Rationale:** Separating defaults from preset overrides keeps the "Default" values visible and prevents accidental drift.

#### Step 1.2: Map `--fs-*` into Tailwind via `@theme inline` in `globals.css`

- **Location:** `web/frontend/app/globals.css` — inside the existing `@theme inline { ... }` block.
- **What:** Add six `--text-*` entries that reference the CSS vars. In Tailwind v4 `@theme inline`, the `--text-*` namespace controls font sizes — e.g. `--text-eyebrow: var(--fs-eyebrow)` generates the utility `text-eyebrow`.
- **Entries to add:** `--text-eyebrow`, `--text-label`, `--text-ui`, `--text-body-sm`, `--text-body`, `--text-tag`.
- **Rationale:** Gives component authors a clean `text-eyebrow` Tailwind class as an alternative to inline styles; also lets the `Eyebrow` component use `"var(--fs-eyebrow)"` as a string in its inline style.

**Validation & Commit:**
> Run `npm run typecheck && npm run lint && npm test` from `web/frontend/`. All 180+ existing tests must pass (no component code changed yet). Commit: `[Typography Scale] (1/5) Complete: CSS --fs-* variables + .fs-* preset classes + Tailwind mapping.`

---

### Phase 2 — Font-Size Model, Hook, and Layout Wiring

**Goal:** mirror the `lib/theme.ts` + `hooks/use-theme.tsx` + layout script pattern for font size.

#### Step 2.1: Create `lib/font-size.ts`

- **Location:** `web/frontend/lib/font-size.ts` (new file).
- **What:**
  - Export `type FontSize = "compact" | "default" | "comfortable" | "large"`.
  - `FONT_SIZE_KEYS`, `DEFAULT_FONT_SIZE = "default"`, `FONT_SIZE_STORAGE_KEY = "mytheca-font-size"`.
  - `FONT_SIZES` metadata array: `{ key: FontSize; label: string; description: string }[]` — labels are "Compact", "Default", "Comfortable", "Large"; short descriptions ("Dense labels, more on screen" / "Balanced readability" / "Relaxed spacing" / "Maximum legibility").
  - `isFontSize(value): value is FontSize` — type guard.
  - `fontSizeClass(fs: FontSize): string` → `"fs-" + fs`.
  - `applyFontSizeClass(fs: FontSize): void` — removes all `.fs-*` classes from `document.documentElement`, adds the new one.
  - `readFontSizeFromDocument(): FontSize | null`.
  - `fontSizeInitScript: string` — inline script (stringified IIFE), mirrors `themeInitScript` in `lib/theme.ts`. Reads `localStorage[FONT_SIZE_STORAGE_KEY]`, validates, and applies the class before paint.
- **Rationale:** Keeps all font-size logic in one module, exactly parallel to the theme system.

#### Step 2.2: Create `hooks/use-font-size.ts`

- **Location:** `web/frontend/hooks/use-font-size.ts` (new file).
- **What:** Mirror `hooks/use-theme.tsx` exactly — a `useSyncExternalStore` hook over a simple pub-sub singleton that listens for font-size class changes on `<html>`. Exports `{ fontSize, setFontSize }`.
- **Rationale:** Provides a React-idiomatic way for `AppearanceTab` (and any future consumer) to read/write the font size without a context provider.

#### Step 2.3: Wire init script into `app/layout.tsx`

- **Location:** `web/frontend/app/layout.tsx` — the server component that renders `<html>`.
- **What:** Import `fontSizeInitScript` from `lib/font-size.ts`. Add a second `<script dangerouslySetInnerHTML={{ __html: fontSizeInitScript }} />` tag immediately after the existing `themeInitScript` tag. Both run before paint.
- **Rationale:** Prevents a flash of the wrong font-size class on load, identical to the no-flash pattern already in place for themes.

**Validation & Commit:**
> Run `npm run typecheck && npm run lint && npm test`. Tests must still pass. Commit: `[Typography Scale] (2/5) Complete: Font-size model, useFontSize hook, layout init script.`

---

### Phase 3 — AppearanceTab Font-Size Picker

**Goal:** Surface font-size preset selection in the Appearance settings tab.

#### Step 3.1: Update `AppearanceTab.tsx`

- **Location:** `web/frontend/features/options/tabs/AppearanceTab.tsx`
- **What:** Add a new `<section aria-labelledby="fontsize-heading">` below the existing theme section (separated by a hairline `<hr>`). Inside:
  - An `<h2 id="fontsize-heading">` label: "Text size".
  - A brief `<p>` description: "Choose how large labels, card text, and UI elements appear. Saved to this browser."
  - A `role="radiogroup"` / `aria-label="Text size"` containing four `<button role="radio">` items — one per preset — showing the preset label and description. Active preset gets `border-accent bg-card2`; inactive gets `border-cardbd bg-card hover:bg-card2`.
  - Use `useFontSize()` to read/write the active preset.
- **Rationale:** Co-locates both visual settings (theme + density) in one place, consistent with existing patterns.

#### Step 3.2: Update `AppearanceTab.test.tsx`

- **Location:** `web/frontend/features/options/tabs/AppearanceTab.test.tsx`
- **What:** Add tests covering:
  - All four font-size preset buttons render.
  - The active preset button has `aria-checked="true"`.
  - Clicking a preset calls `setFontSize` (mock `use-font-size`).
  - The section has the correct `aria-label` on the radiogroup.

**Validation & Commit:**
> Run `npm run typecheck && npm run lint && npm test` — all tests including new AppearanceTab ones must pass. Commit: `[Typography Scale] (3/5) Complete: AppearanceTab font-size preset picker + tests.`

---

### Phase 4 — Component Updates (Readability Fixes)

**Goal:** Update primitive components and key call sites to consume the CSS variable scale instead of hardcoded pixel values. This is the phase that directly fixes the user's readability complaints.

This phase can be parallelized across independent file groups during implementation (Eyebrow + Tag + Button first; card components after; modal components after).

#### Step 4.1: Update `Eyebrow` component

- **Location:** `web/frontend/components/ui/Eyebrow.tsx`
- **What:**
  - Change `size` prop type from `number` to `number | string`.
  - Change default from `size = 10` to `size = "var(--fs-eyebrow)"`.
  - The existing `style={{ fontSize: size }}` already works with string values — no other change.
- **Impact:** All callers that do NOT pass an explicit `size` prop now scale with the user's preset. Callers that pass explicit sizes (for intentionally different contexts, e.g., a larger display eyebrow) continue to work unchanged.

#### Step 4.2: Update call sites that hardcode small `Eyebrow` sizes

Remove the explicit `size={8.5}` and `size={9}` props (and any other 8–10px overrides) at these locations, so they inherit `--fs-eyebrow`:

- `CharacterCard.tsx` — `<Eyebrow size={9} ...>{c.role}</Eyebrow>`
- `ScenarioCard.tsx` — `<Eyebrow size={9} ...>{s.genre} · {s.tone}</Eyebrow>`
- `SettingCard.tsx` — `<Eyebrow size={9} ...>{s.type}</Eyebrow>`
- `CharacterModal.tsx` — `<Eyebrow size={8.5} ...>❖ Draft with Mytheca</Eyebrow>`, plus the `size={8.5}` "Try" prompt label
- `EntityModal.tsx` — both `<Eyebrow size={8.5} ...>❖ Draft with Mytheca</Eyebrow>` and the `size={8.5}` "Try" label
- `SettingModal.tsx` — same pattern
- Any other `size={8.5}` or `size={9}` Eyebrow calls found in the scan

**Do not remove** explicit sizes from callers that intentionally use a different size (e.g., a `size={11}` or larger call that serves a distinct visual hierarchy purpose).

#### Step 4.3: Update `Tag` component

- **Location:** `web/frontend/components/ui/Tag.tsx`
- **What:** Replace `text-[9.5px]` with `text-tag` (the new Tailwind utility backed by `var(--fs-tag)`). The `text-tag` utility is valid because `@theme inline` defined `--text-tag` in Phase 1.
- **Rationale:** Tags ("Rising", "Intrigue", etc.) are among the hardest items to read.

#### Step 4.4: Update `Button` component text size

- **Location:** `web/frontend/components/ui/Button.tsx`
- **What:** Replace `text-[11px]` with `text-ui` (backed by `var(--fs-ui)`).
- **Rationale:** Button text is actionable; at 11px uppercase it is borderline for contrast compliance on small screens.

#### Step 4.5: Update card body text

- **Locations:**
  - `CharacterCard.tsx` — traits `<span>` at `text-[14px]` → `text-body-sm`
  - `ScenarioCard.tsx` — goal `<p>` at `text-[14px]` → `text-body-sm`; setting name `<span>` at `text-[13px]` → `text-body-sm`
  - `SettingCard.tsx` — desc `<p>` at `text-[14px]` → `text-body-sm`
- **Rationale:** At Default preset, `--fs-body-sm: 14px` so the visual result is unchanged. At Comfortable/Large, these scale up proportionally with the rest.

**Validation & Commit:**
> Run `npm run typecheck && npm run lint && npm test` — all tests must pass. Record the deferred live in-browser a11y pass in `docs/checklist.md`. Commit: `[Typography Scale] (4/5) Complete: Eyebrow/Tag/Button + card/modal call sites updated to CSS variable scale.`

---

### Phase 5 — Docs + Full Validation

**Goal:** update documentation, run the full suite, record deferred items.

#### Step 5.1: Update `docs/design-system.md`

- Add a **Typography Scale** subsection under the existing Typography section describing:
  - The six `--fs-*` CSS variables and their Default values.
  - The four `.fs-*` preset classes and their purpose.
  - The storage key (`mytheca-font-size`) and how it coexists with `mytheca-theme`.
  - The `lib/font-size.ts` module and `useFontSize()` hook as the API surface.

#### Step 5.2: Record deferred items in `docs/checklist.md`

- Add an entry for this plan's live in-browser a11y + responsive pass (same standing constraint as all prior UI work).
- Note that display/heading Cinzel sizes are intentionally excluded from the scale.

#### Step 5.3: Full suite run

- Run `npm run typecheck && npm run lint && npm test` from `web/frontend/`.
- All existing tests must pass; new tests (AppearanceTab) must pass.

**Validation & Commit:**
> All tests green. Commit: `[Typography Scale] (5/5) Complete: docs updated, full suite green.`

---

### Phase 6 — Merge into Main

- Merge the feature branch back into `main` (or open a PR if the user prefers review first).
- Resolve any conflicts (unlikely — this branch touches only frontend files that no other in-progress branch touches).
- Run `npm test` one final time on `main` after merge.

---

## 4. Deliverables Table

| Deliverable | Description | Location |
|---|---|---|
| CSS typography variables | `--fs-*` defaults + `.fs-compact/default/comfortable/large` classes | `web/frontend/styles/themes.css` |
| Tailwind `--text-*` mappings | Six `text-eyebrow` / `text-ui` / `text-body-sm` etc. utilities | `web/frontend/app/globals.css` |
| Font-size model | Types, constants, helpers, no-flash init script | `web/frontend/lib/font-size.ts` |
| `useFontSize()` hook | React hook to read/write the active font-size preset | `web/frontend/hooks/use-font-size.ts` |
| Layout wiring | `fontSizeInitScript` injected before paint | `web/frontend/app/layout.tsx` |
| AppearanceTab update | Four-preset font-size picker section | `web/frontend/features/options/tabs/AppearanceTab.tsx` |
| AppearanceTab tests | Preset render + aria-checked + click + radiogroup label | `web/frontend/features/options/tabs/AppearanceTab.test.tsx` |
| Eyebrow component update | `size` accepts `string`; default → CSS var | `web/frontend/components/ui/Eyebrow.tsx` |
| Tag component update | `text-[9.5px]` → `text-tag` | `web/frontend/components/ui/Tag.tsx` |
| Button component update | `text-[11px]` → `text-ui` | `web/frontend/components/ui/Button.tsx` |
| Card component updates | Card body/eyebrow text → CSS var utilities | `CharacterCard`, `ScenarioCard`, `SettingCard` |
| Modal call-site fixes | Remove hardcoded `size={8.5}` / `size={9}` from Draft labels | `CharacterModal`, `EntityModal`, `SettingModal` |
| Design system docs | Typography scale section | `docs/design-system.md` |
| Checklist update | Deferred a11y pass recorded | `docs/checklist.md` |
