# Character Card Preview Modal

## 1. Introduction

Currently, clicking a `CharacterCard` in the Library's Characters column expands an inline detail section showing Voice, Goal, and Secret. This plan replaces that inline-expand with the same `CharacterProfileModal` popup used when clicking cast monograms in the Scenarios panel. The modal is also updated to a structured 2-column layout so all character fields — Appearance, Background, Personality, Voice, Goal, Secret — are presented at a glance in a readable grid.

This is a frontend-only change. No backend routes, schema, or data layer are touched. The `CharacterProfileModal` already exists and is already wired into `LibraryView`/`useLibraryState` via `openProfile`/`profileChar`/`closeProfile`; the work is to redirect the CharacterCard click to call `openProfile` rather than `toggleExpand`, and to redesign the modal body as a 2-column row-pair grid.

## 2. Gaps & Unanswered Questions

- **Modal width:** the current modal is `sm:w-[440px]`. Two columns of text need more room — assume `sm:w-[560px]` (fits within the `max-w-[92vw]` guard). _Simple gap — proceed._
- **Empty fields:** Appearance, Background, Personality are nullable. Cells with no value are omitted; if both cells in a row are empty the row is skipped entirely. _Simple gap — proceed._
- **`expandedCharId` / `toggleExpand`:** used only in `CharacterColumn` / `LibraryColumns`. After removing the inline expand these become dead state. Remove them from `useLibraryState` and the return object. `resetForStoryline` references `setExpandedCharId(null)` — remove that line too. _Simple gap — proceed._

## 3. Hierarchical Steps

---

### Phase 1 — Update `CharacterProfileModal` to 2-column layout

**Locations:** `web/frontend/components/feature/CharacterProfileModal.tsx`, `web/frontend/components/feature/CharacterProfileModal.test.tsx`

**Changes:**

1. Widen the modal: change `sm:w-[440px]` → `sm:w-[560px]`.
2. Replace the single `flex-col` body with a 2-column CSS grid (`grid grid-cols-2 gap-x-[20px] gap-y-[14px]`).
3. Lay out field pairs row by row:
   - **Row 1:** Appearance (col 1) | Background (col 2)
   - **Row 2:** Personality (col 1) | Voice (col 2)
   - **Row 3:** Goal (col 1) | Secret (col 2)
4. Each cell renders a labelled block (`<div>` with `<Eyebrow>` label + body text). Keep the accent color convention (gold `#A8762A` for all except Secret which uses `var(--accent)`).
5. If both cells in a row are null/empty, hide the entire row (`null`). If only one cell is empty, render the other cell spanning both columns (`col-span-2`) so the layout stays clean.
6. The italic traits line moves into the modal header area (below the name/role, above the grid separator).
7. **Row 4 (full-width):** `Edit Character` button spanning both columns (`col-span-2`), shown only when `onEdit` is provided. Use `justify-self-end` to right-align it.
8. Update `CharacterProfileModal.test.tsx`: add a test asserting the 2-column row structure (Appearance/Background pair visible, Goal/Secret pair visible, empty row omitted).

**Validation & Commit:**
> Run `npm test -- --reporter=verbose` (Vitest) scoped to `CharacterProfileModal.test.tsx`; also `npm run typecheck` and `npm run lint`. Once green, commit: `[Character Card Preview Modal] (1/3) Complete: CharacterProfileModal redesigned to 2-column row-pair layout.`

---

### Phase 2 — Wire CharacterCard click to open the profile modal

**Locations:**
- `web/frontend/components/feature/CharacterCard.tsx`
- `web/frontend/components/feature/CharacterColumn.tsx`
- `web/frontend/features/library/LibraryColumns.tsx`
- `web/frontend/features/library/useLibraryState.ts`

**Changes:**

#### `CharacterCard.tsx`
- Remove the `expanded: boolean` prop.
- Rename `onToggle: () => void` → `onPreview: () => void`.
- Remove `aria-expanded={expanded}` from the card button.
- Remove the `{expanded ? <div>…</div> : null}` inline detail block entirely.
- The card button `onClick` calls `onPreview()` instead of toggling.

#### `CharacterColumn.tsx`
- Remove `expandedId: string | null` from props.
- Rename `onToggle: (id: string) => void` → `onPreview: (id: string) => void`.
- Remove `expanded={expandedId === c.id}` from `<CharacterCard>`.
- Pass `onPreview={() => onPreview(c.id)}` to each card.

#### `LibraryColumns.tsx`
- Remove `expandedId={lib.expandedCharId}` from `<CharacterColumn>`.
- Change `onToggle={lib.toggleExpand}` → `onPreview={lib.openProfile}`.

#### `useLibraryState.ts`
- Remove `const [expandedCharId, setExpandedCharId] = useState<string | null>(null);`.
- Remove `function toggleExpand(id: string) { … }`.
- In `resetForStoryline`: remove the `setExpandedCharId(null)` line.
- Remove `expandedCharId, toggleExpand` from the returned object.

**Validation & Commit:**
> Run `npm test` (full Vitest suite) plus `npm run typecheck` and `npm run lint`. Confirm no references to `expandedCharId` or `toggleExpand` remain. Once green, commit: `[Character Card Preview Modal] (2/3) Complete: CharacterCard click opens profile modal; inline expand removed.`

---

### Phase 3 — Validation gate + docs update

**Locations:** `docs/checklist.md`, `docs/component-map.md`

**Changes:**

1. Run the full frontend suite: `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`.
2. Accessibility reasoning check (deferred live pass — same standing dev-server constraint):
   - The `CharacterProfileModal` is already focus-trapped via `Modal`; the 2-column grid adds no new interactive elements.
   - Cards still have a single `<button>` as their interactive element (no change to keyboard operability).
   - `onEdit` button in the modal is a standard `<Button>` with visible label.
   - Document the deferred in-browser a11y pass in `docs/checklist.md`.
3. Update `docs/component-map.md`: note that `CharacterCard` no longer has inline expand; it now opens `CharacterProfileModal` on click.
4. Update `docs/checklist.md`: add this feature as complete with the deferred a11y note.

**Validation & Commit:**
> Full suite green; `next build` clean. Commit: `[Character Card Preview Modal] (3/3) Complete: Docs + validation gate; ready to merge.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
|---|---|---|
| `CharacterProfileModal.tsx` | 2-column row-pair layout (Appearance/Background · Personality/Voice · Goal/Secret · Edit button) | `web/frontend/components/feature/CharacterProfileModal.tsx` |
| `CharacterCard.tsx` | Inline expand removed; click calls `onPreview` | `web/frontend/components/feature/CharacterCard.tsx` |
| `CharacterColumn.tsx` | `expandedId`/`onToggle` replaced by `onPreview` | `web/frontend/components/feature/CharacterColumn.tsx` |
| `LibraryColumns.tsx` | `onPreview` wired to `lib.openProfile` | `web/frontend/features/library/LibraryColumns.tsx` |
| `useLibraryState.ts` | `expandedCharId` / `toggleExpand` removed | `web/frontend/features/library/useLibraryState.ts` |
| `CharacterProfileModal.test.tsx` | Updated tests for 2-column layout + row-omission logic | `web/frontend/components/feature/CharacterProfileModal.test.tsx` |
| `docs/checklist.md` | Feature entry + deferred a11y note | `docs/checklist.md` |
| `docs/component-map.md` | CharacterCard behavior update | `docs/component-map.md` |
