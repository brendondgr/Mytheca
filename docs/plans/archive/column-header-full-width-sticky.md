# Column Header Full-Width Sticky Fix

## 1. Introduction

The Library's three columns (Scenarios, Characters, Settings) each have a `ColumnHeader` component that is intended to act as a sticky section header. The component uses `sticky top-0 z-[10] bg-page` — but the column wrapper (`<section>` in `LibraryColumns.tsx`) is simultaneously the scroll container (`overflow-y-auto`) **and** the horizontal-padding source (`lg:px-[24px]`). Because sticky children inherit their containing block's padding, the header's `bg-page` background only covers the inset content area (column_width − 48 px), leaving a 24 px transparent strip on each side. As users scroll, card content (text, borders, shadows) slides up through these side strips and is visible behind the header.

The fix restructures the padding responsibility: the `Column` wrapper becomes a clean, padding-free scroll container; the padding is moved down to the inner content div of `ColumnHeader` and to each column component's card-list wrapper, threaded via a `padX` prop. The first/last column asymmetry (`lg:first:pl-0 / lg:last:pr-0`) is expressed per-column in `LibraryColumns.tsx` and passed as a Tailwind class string — keeping `ColumnHeader` and the column components position-agnostic. This is a pure layout change: no API, no schema, no new dependencies.

---

## 2. Gaps & Unanswered Questions

- **`scroll-mt` value (simple gap):** `SettingColumn` uses `scroll-mt-[68px]` to clear the sticky header when auto-scrolling to the active setting. The sticky header's visual height does not change (only its width coverage changes), so `68px` remains correct. No update needed.
- **Mobile padding (simple gap):** The column wrapper has no mobile padding (all padding is `lg:`-prefixed). The outer grid container supplies mobile gutters (`px-[20px] sm:px-[28px]`). The new `padX` prop values are all `lg:`-prefixed, so mobile behavior is unchanged.
- **`ColumnEmpty` padding (simple gap):** `ColumnEmpty` renders a centered `<p>`. Wrapping the non-header section of each column in a `<div className={padX}>` covers both the `ColumnEmpty` and the card grid in a single wrapper, avoiding any change to the `ColumnEmpty` component itself.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Restructure Column Padding (single phase)

This is a single-phase change across five files.

#### Step 1.1 — Remove horizontal padding from `Column` wrapper in `LibraryColumns.tsx`

- **Location:** `web/frontend/features/library/LibraryColumns.tsx` — the `Column` inner component, line 28.
- **Change:** Remove `lg:px-[24px] lg:first:pl-0 lg:last:pr-0` from the `<section>` className. Keep all other classes (`outline-none lg:block lg:h-full lg:min-h-0 lg:overflow-y-auto lg:border-l lg:border-hair lg:pb-[28px] lg:first:border-l-0`).
- **Rationale:** The scroll container must not apply horizontal padding so that its sticky child covers the full column width. Border, height, and overflow classes remain.

#### Step 1.2 — Pass `padX` prop to each column component in `LibraryColumns.tsx`

- **Location:** `web/frontend/features/library/LibraryColumns.tsx` — the three `<ScenarioColumn>`, `<CharacterColumn>`, `<SettingColumn>` usages (lines 74–105).
- **Change:** Add a `padX` prop to each:
  - `ScenarioColumn`: `padX="lg:pr-[24px]"` — first column: right pad only (no left).
  - `CharacterColumn`: `padX="lg:px-[24px]"` — middle column: both sides.
  - `SettingColumn`: `padX="lg:pl-[24px]"` — last column: left pad only (no right).
- **Rationale:** These mirror the previous CSS `first:pl-0 / last:pr-0` logic, now expressed explicitly per column so the column components stay position-agnostic.

#### Step 1.3 — Add `className` prop to `ColumnHeader` in `ColumnChrome.tsx`

- **Location:** `web/frontend/components/feature/ColumnChrome.tsx` — `ColumnHeader` component.
- **Change:**
  - Add `className?: string` to the props interface.
  - Apply it to the **inner** content div (the `border-b border-hair-strong pb-[8px]` div), not the sticky outer wrapper: `className={cn("border-b border-hair-strong pb-[8px]", className)}`.
  - The sticky outer wrapper stays as `"sticky top-0 z-[10] bg-page pb-[12px]"` — full-width, no horizontal padding, covering the entire column.
- **Rationale:** The inner div receives the padding so its content aligns with the cards below. The outer sticky wrapper remains padding-free to cover the column edge-to-edge.

#### Step 1.4 — Add and wire `padX` in `ScenarioColumn.tsx`

- **Location:** `web/frontend/components/feature/ScenarioColumn.tsx`.
- **Change:**
  - Add `padX?: string` to the props interface (default: no value needed — callers always pass it from LibraryColumns).
  - Pass `padX` as `className` to `<ColumnHeader>`.
  - Wrap the content section (both the `<ColumnEmpty>` path and the card `<div>`) in a single `<div className={padX}>`.
- **Rationale:** Both the header's inner content and the card list must use the same horizontal padding so they align.

#### Step 1.5 — Add and wire `padX` in `CharacterColumn.tsx`

- **Location:** `web/frontend/components/feature/CharacterColumn.tsx`.
- **Change:** Same as Step 1.4 — add `padX?: string`, pass to `ColumnHeader` as `className`, wrap content in `<div className={padX}>`.

#### Step 1.6 — Add and wire `padX` in `SettingColumn.tsx`

- **Location:** `web/frontend/components/feature/SettingColumn.tsx`.
- **Change:** Same pattern — add `padX?: string`, pass to `ColumnHeader` as `className`, wrap the `settings.length === 0` / card-list block in `<div className={padX}>`.
- Note: `scroll-mt-[68px]` on the active setting `<div>` does not need updating (header height unchanged).

#### Step 1.7 — Validation

Run from `web/frontend/`:
```
npm test          # Vitest — all component/route tests
npm run typecheck # tsc --noEmit
npm run lint
```

Confirm:
- `LibraryColumns.test.tsx` passes (cross-column highlight + storyline switcher).
- TypeScript reports no errors on the five changed files.
- ESLint clean.

**Web/UI a11y + responsive pass** (required per global-project-rules):
- At 320 / 375 / 768 / 1024 px: no horizontal overflow; header border extends edge-to-edge within its column; cards remain at correct inset.
- Keyboard: Tab reaches the `+` button in each column header; Enter/Space fires `onAdd`.
- Focus ring visible on the `+` button at all breakpoints.
- No contrast regression (`SCENARIOS` / `CHARACTERS` / `SETTINGS` headings remain on `bg-page`).

**Action:** Once all checks are green, commit:
> `[Column Header Full-Width Sticky] (1/1) Complete: Restructure column padding so sticky header covers full column width — no side gaps.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `LibraryColumns.tsx` | Remove `lg:px-[24px]` from Column wrapper; pass `padX` to each column | `web/frontend/features/library/LibraryColumns.tsx` |
| `ColumnChrome.tsx` | `ColumnHeader` accepts `className` applied to inner content div | `web/frontend/components/feature/ColumnChrome.tsx` |
| `ScenarioColumn.tsx` | `padX` prop wired to `ColumnHeader` + content wrapper | `web/frontend/components/feature/ScenarioColumn.tsx` |
| `CharacterColumn.tsx` | `padX` prop wired to `ColumnHeader` + content wrapper | `web/frontend/components/feature/CharacterColumn.tsx` |
| `SettingColumn.tsx` | `padX` prop wired to `ColumnHeader` + content wrapper | `web/frontend/components/feature/SettingColumn.tsx` |
