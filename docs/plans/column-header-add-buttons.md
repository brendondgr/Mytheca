# Column Header "+" Add Buttons

## 1. Introduction

The Library view has three open columns (Scenarios · Characters · Settings), each with a `ColumnHeader`. Currently, creating new entities requires navigating to the global "**+ Create ▾**" dropdown in the app header. The goal here is to add a small, accessible **"+"** button to the top-right of each column header so the user can open the corresponding Create modal directly from the column they are looking at — a faster, more contextual affordance.

The change is entirely in the frontend presentation layer. No API or backend changes are needed because `lib.openCreate(type: EntityType)` already exists in `useLibraryState` and is wired to the correct modal for each entity type. The work fans from `ColumnChrome.tsx` (primitive) upward through each column component to `LibraryColumns` (where `lib` is available).

---

## 2. Gaps & Unanswered Questions

- **Visual style of the "+" button** — Assumption: use a small round `+` symbol styled with existing design tokens (`text-mute` / `hover:text-ink`, `text-[14px]`, `font-mono`, cursor-pointer, visible focus ring via `outline-accent`). Should be subtle against the header so it doesn't compete with the column title; becomes prominent on hover.
- **"+" label** — Assumption: use the literal `+` character (not an SVG icon) to stay consistent with the current `IconButton` approach elsewhere. Provide a screen-reader `aria-label` of `"Add scenario"` / `"Add character"` / `"Add setting"`.
- No backend, schema, or contract changes required.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Extend `ColumnHeader` with an optional `onAdd` button

**Location:** `web/frontend/components/feature/ColumnChrome.tsx`

**Rationale:** `ColumnHeader` is the single place that renders the column title bar. Adding the prop here means the change is composable and every column picks it up the same way.

**Changes:**
1. Add `onAdd?: () => void` to the `ColumnHeader` props type.
2. Wrap the `border-b` inner row in a `flex items-start justify-between gap-[8px]` container so the left side (title + count) stays on the left and the button lands on the right, vertically aligned to the title baseline.
3. Render the button **only when `onAdd` is provided**:
   ```
   <button
     type="button"
     aria-label="Add ..."  // passed as a prop (addLabel) or derived from title
     onClick={onAdd}
     className="..."
   />
   ```
   Use a simple `+` text character. Style with `font-mono text-[16px] leading-none text-mute cursor-pointer rounded-[4px] px-[3px] hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent transition-colors`.
4. Add `addLabel?: string` prop (defaults to `"Add ${title.toLowerCase()}"`) so callers can supply a custom screen-reader label without having to know about internals.

**Hint block** stays below the title+button row (unchanged).

**Validation & Commit:**
> Run `npm run typecheck` in `web/frontend/`. Once green, commit: `[Column Header + Buttons] (1/3) Complete: Extend ColumnHeader with optional onAdd button.`

---

### Phase 2 — Thread `onAdd` through the three column components

**Locations:**
- `web/frontend/components/feature/ScenarioColumn.tsx`
- `web/frontend/components/feature/CharacterColumn.tsx`
- `web/frontend/components/feature/SettingColumn.tsx`

**Rationale:** Each column component owns the `ColumnHeader` call site. They must accept an optional `onAdd` prop and forward it to `ColumnHeader`, plus supply the correct `addLabel`.

**Changes (same pattern in all three):**
1. Add `onAdd?: () => void` to the component's props interface.
2. Pass `onAdd={onAdd}` and `addLabel="Add <noun>"` to `<ColumnHeader>`.
   - ScenarioColumn: `addLabel="Add scenario"`
   - CharacterColumn: `addLabel="Add character"`
   - SettingColumn: `addLabel="Add setting"`

**Validation & Commit:**
> Run `npm run typecheck` in `web/frontend/`. Once green, commit: `[Column Header + Buttons] (2/3) Complete: Thread onAdd through ScenarioColumn, CharacterColumn, SettingColumn.`

---

### Phase 3 — Wire `LibraryColumns` to call `lib.openCreate`

**Location:** `web/frontend/features/library/LibraryColumns.tsx`

**Rationale:** `LibraryColumns` already receives the full `lib` object (which exposes `lib.openCreate(type)`). No changes to `LibraryView` are required — it already passes `lib` down. We just supply the `onAdd` callbacks from `lib.openCreate` to each column component.

**Changes:**
1. Pass `onAdd={() => lib.openCreate("scenario")}` to `<ScenarioColumn>`.
2. Pass `onAdd={() => lib.openCreate("character")}` to `<CharacterColumn>`.
3. Pass `onAdd={() => lib.openCreate("setting")}` to `<SettingColumn>`.

**Validation & Commit:**
> Run `npm run typecheck` and `npm test` in `web/frontend/`. Perform a manual browser check: clicking `+` in each column header opens the correct Create modal; keyboard Tab + Enter also triggers it; focus ring is visible (AA contrast); layout holds at 320/375/768/1024 px. Once green, commit: `[Column Header + Buttons] (3/3) Complete: Wire LibraryColumns to open Create modal per column.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
|---|---|---|
| `ColumnHeader` `onAdd` prop | Optional `+` button in column header top-right | `web/frontend/components/feature/ColumnChrome.tsx` |
| `ScenarioColumn` `onAdd` | Forwards prop to `ColumnHeader` | `web/frontend/components/feature/ScenarioColumn.tsx` |
| `CharacterColumn` `onAdd` | Forwards prop to `ColumnHeader` | `web/frontend/components/feature/CharacterColumn.tsx` |
| `SettingColumn` `onAdd` | Forwards prop to `ColumnHeader` | `web/frontend/components/feature/SettingColumn.tsx` |
| `LibraryColumns` wiring | Calls `lib.openCreate` per column | `web/frontend/features/library/LibraryColumns.tsx` |
| Accessibility pass | Keyboard, focus ring, ARIA label, responsive | Manual browser check (320/375/768/1024 px) |
