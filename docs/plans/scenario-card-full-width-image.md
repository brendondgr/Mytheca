# Scenario Card Full-Width Image Fix

## 1. Introduction

`ScenarioCard` currently uses a negative-margin trick to make scenario images span the full inner width of the card (`-mx-[16px] -mt-[15px] w-[calc(100%+32px)]`). This approach is fragile and has off-by-one errors in both the normal and featured card states:

- **Normal card** (`border` = 1px, `p-[16px]`): the top offset is `-mt-[15px]` but top padding is 16px — leaves a 1px gap where the card background bleeds through. The card also lacks `overflow-hidden`, so the image's top-left/top-right corners are not clipped to the card's `rounded-[4px]`.
- **Featured card** (`border-2` = 2px, `p-[15px]`): `-mx-[16px]` oversteps the 15px padding by 1px on each side, causing the image to bleed into the 2px accent border. The width calc (`100%+32px`) is computed from the content area but the math doesn't account for the wider border, leaving minor edge artifacts.

The fix restructures `ScenarioCard` to match the `SettingCard` pattern already used elsewhere in the codebase: `overflow-hidden` on the card container with the image placed at the top (no padding), and a separate inner div holding the padded text content. This is a zero-risk, single-file change with no layout regressions.

## 2. Gaps & Unanswered Questions

- **Padding values after image:** The original image had `mb-[12px]` (gap below image). In the new structure we preserve that gap as `pt-[12px]` on the content div (instead of the full `pt-[16px]`/`pt-[15px]`). Assumption: keep the same visual gap.
- **No other files need changes:** `ScenarioColumn`, `LibraryColumns`, and `LibraryView` only compose `ScenarioCard` and are unaffected.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 (1/1) — Restructure ScenarioCard image layout

**File:** `web/frontend/components/feature/ScenarioCard.tsx`

**Rationale:** This is the only component with the problematic negative-margin image pattern. All changes are isolated to this file.

#### Step 1a: Remove padding from the outer card `div` and add `overflow-hidden`

The card `div` currently sets `p-[16px]` (normal) or `p-[15px]` (featured). Remove both. Add `overflow-hidden` so the image's corners are clipped to the card's `rounded-[4px]`. The `relative` class stays for the absolute-positioned button and edit icon.

Before:
```
"mytheca-card relative rounded-[4px] ..."
featured ? "border-2 border-accent bg-card2 p-[15px] ..." : "border border-cardbd bg-card p-[16px]"
```
After:
```
"mytheca-card relative overflow-hidden rounded-[4px] ..."
featured ? "border-2 border-accent bg-card2 ..." : "border border-cardbd bg-card"
```

#### Step 1b: Simplify the image element

Remove the negative-margin hack (`-mx-[16px] -mt-[15px] mb-[12px] w-[calc(100%+32px)]`). Replace with a simple `w-full h-[96px] object-cover` — `overflow-hidden` on the parent handles corner clipping. Keep `pointer-events-none relative z-[1]`.

Before:
```
className="pointer-events-none relative z-[1] -mx-[16px] -mt-[15px] mb-[12px] h-[96px] w-[calc(100%+32px)] object-cover"
```
After:
```
className="pointer-events-none relative z-[1] h-[96px] w-full object-cover"
```

#### Step 1c: Wrap existing text content in a padded inner `div`

The text content (`h3`, `Eyebrow`, `p`, cast row, setting name) currently lives directly inside the padded card. Wrap it in a `div` whose padding matches the original card padding but with a reduced top (`pt-[12px]`) when an image is present to preserve the original vertical gap.

- `featured && image`: `p-[15px] pt-[12px]`
- `featured && no image`: `p-[15px]`
- `normal && image`: `p-[16px] pt-[12px]`
- `normal && no image`: `p-[16px]`

This can be expressed cleanly as:
```
cn(
  "pointer-events-none relative z-[1]",
  featured ? "p-[15px]" : "p-[16px]",
  s.image && "pt-[12px]",
)
```

The `pointer-events-none relative z-[1]` classes that already wrap the text content are kept — just add the padding classes.

**Validation & Commit:**

> *Action: Run frontend component tests for ScenarioCard (`npm test -- ScenarioCard`) and the full frontend test suite (`npm test`) from `web/frontend/`. Run TypeScript type check (`npm run typecheck`). Do an accessibility + responsive pass: verify the image is visible and flush with card edges at 320/375/768/1024px viewports; confirm focus ring on the scenario select button is unaffected; confirm `overflow-hidden` doesn't clip the absolute-positioned edit `IconButton`. Once green, commit locally:*
> `[Scenario Card Image Fix] (1/1) Complete: Restructure ScenarioCard to use overflow-hidden + w-full image`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| ScenarioCard restructure | `overflow-hidden` card, `w-full` image, padded inner content div | `web/frontend/components/feature/ScenarioCard.tsx` |
| Existing tests pass | `ScenarioCard.test.tsx` suite continues green (no rendered markup changes that break selectors) | `web/frontend/components/feature/ScenarioCard.test.tsx` |
