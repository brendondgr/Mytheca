# Self-Triage: Default "Select" Category for Dropped Docs

## 1. Introduction

Currently, every file dropped into the New Storyline TriagePanel defaults to the `"other"` category — making the manual category dropdown misleading (the doc is already "classified" before the user has had a chance to look at it). This plan adds a **Self-Triage** flow: dropped docs start as `"select"` (uncategorized) so the user can categorize them by hand, or let the AI Triage button do it automatically.

The scope is **frontend-only**. No backend routes, schemas, or database columns change. The change touches three layers: the shared `DocCategory` type, the `storylineCreator` logic helpers, and the `TriagePanel` UI. At persist time `"select"` is silently mapped to `"other"` so the backend never sees the new value.

---

## 2. Gaps & Unanswered Questions

- **Category order in the dropdown:** user specified `Character / Other / Setting`. Plan uses that order.
- **Grouping trigger:** assumed to fire as soon as any doc has a non-`"select"` category (manual OR AI triage), not only after AI Triage runs. Docs still at `"select"` appear in an "Uncategorized" bucket at the top of the grouped view.
- **Persist behavior:** `"select"` → `"other"` at `docToContextInput` time. No complex gap — straightforward fallback.
- **Backend `DocCategory`:** the Python backend uses its own enum; it never receives `"select"`. No backend change required.

---

## 3. Hierarchical Step-by-Step Instructions

---

### Phase 1 — Type + Creator Logic

#### Step 1.1 — Extend `DocCategory`

- **Location:** `web/frontend/lib/types.ts`, line where `DocCategory` is defined (currently `"character" | "setting" | "other"`).
- **Change:** add `"select"` as a fourth member: `"character" | "setting" | "other" | "select"`.
- **Rationale:** every other layer derives from this type; add it here first so TypeScript can catch every downstream usage that needs updating.

#### Step 1.2 — Update `toCreatorDoc` default

- **Location:** `web/frontend/features/library/storylineCreator.ts`, `toCreatorDoc` function.
- **Change:** `category: "other"` → `category: "select"`.
- **Rationale:** freshly dropped docs should communicate "uncategorized" rather than pre-assigning Other.

#### Step 1.3 — Map `"select"` at persist time

- **Location:** `web/frontend/features/library/storylineCreator.ts`, `docToContextInput` function.
- **Change:** `category: d.category` → `category: d.category === "select" ? "other" : d.category`.
- **Rationale:** the backend only understands `character | setting | other`; `"select"` must never reach the API.

> **Action:** Run `npm run typecheck` and `npm test` in `web/frontend/`. Fix any type errors the new union member surfaces (selects / switches that exhaustively check `DocCategory`). Once green, commit:
> `[Self-Triage] (1/2) Complete: Added "select" DocCategory; toCreatorDoc defaults to unset; mapped to "other" at persist time.`

---

### Phase 2 — TriagePanel UI, Tests, Docs

#### Step 2.1 — Update the category `<select>` in `TriagePanel`

- **Location:** `web/frontend/components/feature/TriagePanel.tsx`, `DocRow` inner component, the `<select>` element.
- **Changes:**
  - Add `<option value="select">Select</option>` as the **first** option (the placeholder).
  - Reorder remaining options to match user spec: Character / Other / Setting.
  - The existing `onChange` handler (`onSetCategory`) already propagates any string value — no logic change needed there.

#### Step 2.2 — Update grouping trigger and add "Uncategorized" bucket

- **Location:** `web/frontend/components/feature/TriagePanel.tsx`.
- **Changes:**
  - Replace `const anyTriaged = docs.some((d) => d.triaged);` with:
    `const anyGrouped = docs.some((d) => d.triaged || d.category !== "select");`
  - Replace all uses of `anyTriaged` with `anyGrouped` in the render.
  - In the grouped view, add an **"Uncategorized" bucket** above the existing three groups that renders docs whose `category === "select"`:
    ```
    { docs.filter(d => d.category === "select").length > 0 && (
        <div>
          <header>UNCATEGORIZED · Not yet categorized</header>
          <ul> {docs.filter(d => d.category === "select").map(...)} </ul>
        </div>
    )}
    ```
  - Update `GROUPS` order to `[character, other, setting]` to match user spec (was `[character, setting, other]`).

#### Step 2.3 — Update `TriagePanel` tests

- **Location:** `web/frontend/components/feature/TriagePanel.test.tsx`.
- **Changes:**
  - The two existing tests use `toCreatorDoc` — they will now produce docs with `category: "select"`. Verify the tests still pass (the tests don't assert on category, only on button text and classifying badge).
  - Add a test: dropping a file and manually selecting "Character" from the dropdown triggers `onSetCategory` with `"character"`.
  - Add a test: after one doc is manually set to a non-`"select"` category, the grouped view appears (including an "Uncategorized" bucket for remaining `"select"` docs).

#### Step 2.4 — Update `StorylineCreatorView` tests (if needed)

- **Location:** `web/frontend/features/library/StorylineCreatorView.test.tsx`.
- **Check:** the "triages dropped files into grouped buckets" test calls `onTriage` which goes through the AI triage path. The mock should still classify to `"character"`. Confirm the grouped "Character details" text still appears. No change expected unless the mock returns data that relies on the old default.

#### Step 2.5 — Update `docs/checklist.md`

- **Location:** `docs/checklist.md`.
- **Change:** add a brief entry under Follow-up Work noting the Self-Triage feature (Self-Triage category select, done, this plan). Note the deferred in-browser a11y/responsive pass (same standing constraint).

> **Action:** Run `npm run typecheck`, `npm run lint`, `npm test`, and `npm run build` in `web/frontend/`. All must pass. Confirm: (1) a freshly dropped file shows "Select" in the dropdown, (2) changing the dropdown to "Character" groups it correctly, (3) AI Triage still works and overrides manual selection. Once green, commit:
> `[Self-Triage] (2/2) Complete: TriagePanel defaults to "Select"; grouped view adds Uncategorized bucket; GROUPS reordered Character/Other/Setting.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
|---|---|---|
| Extended `DocCategory` | Adds `"select"` as an unset placeholder | `web/frontend/lib/types.ts` |
| Updated `toCreatorDoc` | Defaults new docs to `"select"` | `web/frontend/features/library/storylineCreator.ts` |
| Persist mapper | Maps `"select"` → `"other"` at API boundary | `web/frontend/features/library/storylineCreator.ts` (`docToContextInput`) |
| TriagePanel dropdown | "Select" as first option; Character/Other/Setting order | `web/frontend/components/feature/TriagePanel.tsx` |
| Grouping logic | Trigger on any non-`"select"` category; Uncategorized bucket | `web/frontend/components/feature/TriagePanel.tsx` |
| Updated tests | Cover manual categorization + grouped view | `web/frontend/components/feature/TriagePanel.test.tsx` |
| Checklist update | Record done + deferred a11y pass | `docs/checklist.md` |
