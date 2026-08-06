# Plan: Triage Panel Sidebar Polish

## 1. Introduction

The right-hand Context sidebar on `/storylines/new` (`TriagePanel`) has three usability problems: the Upload dropzone and Triage button scroll away as the file list grows; section headers (Characters / Settings / Other) are rendered at 9 px and are indistinguishable from body text; and the `ContextBudgetMeter` displays tiny, muted token numbers that are hard to read.

The approach is purely frontend: two component files change (`TriagePanel.tsx`, `ContextBudgetMeter.tsx`). No backend, no contract, no new dependencies. Work is split into two phases so each commit is independently reviewable: (1) budget meter legibility + token formatting, (2) panel layout restructure + section header upgrades.

---

## 2. Gaps & Unanswered Questions

- **Token formatting precision:** User's examples ("1K, 7.5K, 94.2K") imply one decimal place kept only when non-zero. Assumed: show at most one decimal, strip trailing ".0". Under 1 000 show raw integer. This fits a simple inline helper — no shared util file needed.
- **Budget meter position:** User says Context (file list) is "at the bottom" with Upload+Triage stickied at top. The `ContextBudgetMeter` logically belongs with the file list area. Assumed: meter stays at the bottom of the scrollable file-list section.
- **Mobile (< lg) layout:** Below `lg` the panel is already full-width stacked. The sticky-top pattern works fine on mobile too (sticky relative to the scroll container). No separate handling needed.

---

## 3. Hierarchical Step-by-Step Instructions

---

### Phase 1 — Budget Meter: legibility + token approximations

**Files:** `web/frontend/components/feature/ContextBudgetMeter.tsx`

**What to change:**

1. **Add `fmtTokens` helper** (inline at top of file, ~6 lines):
   - Under 1 000 → raw integer string.
   - 1 000+ → divide by 1 000, round to 1 decimal, strip trailing `.0`, append "K".
   - Examples: 500 → "500", 1 000 → "1K", 7 500 → "7.5K", 94 200 → "94.2K".

2. **Header row** (eyebrow + total-tokens badge):
   - Total-tokens badge: replace `text-[10px]` with `text-[12px]` and swap `text-mute` classes per level for their `-soft`/darker equivalents so they pass contrast at small sizes. Apply `fmtTokens` to `budget.totalTokens`.

3. **`<dl>` rows** (Primer / Draft doc breakdown):
   - Current: `font-mono text-[10px] text-mute`. Change to `text-[12px] text-ink-soft` on `<dt>` and `text-ink` on `<dd>` (values need to be easy to scan).
   - Apply `fmtTokens` to both `budget.primerTokens` and `budget.draftDocsTokens`.
   - Wrap each `<dt>`/`<dd>` pair in a `<div class="flex justify-between gap-[8px]">` (already done — keep structure, just update sizes).

4. **Status note** (`LEVEL_NOTE` paragraph):
   - Current: `font-body text-[11.5px]`. Bump to `text-[13px]` so the advisory message is readable.

5. **`aria-valuemax`** on the progressbar: already correct. No change needed.

**Rationale:** These are purely typographic / colour tweaks within one component. Shipping them first means Phase 2 can be reviewed in isolation.

**Validation & Commit:**
> Run `npm run build` (or `tsc --noEmit`) from `web/frontend/` to verify no TS errors. Run the `ContextBudgetMeter` snapshot/unit test if it exists (search `utils/tests/` + `web/frontend/`); if absent, do a visual spot-check via the dev server. Perform an accessibility pass: colour-contrast check on the muted text at 12 px (WCAG AA for UI components), keyboard nav through the panel unchanged. Once green, commit: `[Triage Panel Polish] (1/2) Complete: ContextBudgetMeter — larger text, darker values, fmtTokens approximations.`

---

### Phase 2 — TriagePanel: sticky top, scrollable bottom, bolder section headers

**Files:** `web/frontend/components/feature/TriagePanel.tsx`

**What to change:**

1. **`<aside>` outer container** — remove `lg:overflow-y-auto` and `gap-[12px]`; keep everything else. The aside is already `flex flex-col lg:self-stretch`; it must *not* scroll itself so the inner regions can own their own scroll context.

2. **New sticky-top div** — immediately inside `<aside>`, wrapping the header row + dropzone + Triage button:
   ```
   <div class="sticky top-0 z-10 bg-card flex flex-col gap-[12px]
               p-[18px_20px] border-b border-hair-strong">
     {header row: Eyebrow + file-count badge}
     {drag-drop zone}
     {Triage button}
   </div>
   ```
   The `border-b` provides visual separation from the scrolling list below.

3. **New scrollable-body div** — immediately after the sticky top, flex-1 + overflow-y-auto:
   ```
   <div class="flex-1 overflow-y-auto flex flex-col gap-[12px] p-[18px_20px] pt-[14px]">
     {empty-state text OR flat doc list OR grouped doc list}
     {<ContextBudgetMeter>}
   </div>
   ```
   This section scrolls independently when the file list grows.

4. **Section headers** (inside the `anyTriaged` branch, the per-group heading):
   - Current: `<Eyebrow size={9}>` + a `text-[9px]` hint span — looks like a footnote.
   - New: replace with a plain `<h3>` or styled `<div>` at `font-mono text-[11.5px] font-semibold tracking-[0.12em] text-ink uppercase` for the label, and a slightly smaller `text-[10.5px] text-mute` span for the hint. This makes "CHARACTERS", "SETTINGS", "OTHER" read as real headings without adding a heavy visual weight that fights with the left pane.
   - Keep the `mb-[6px]` gap between the header and the `<ul>` that follows.
   - Add a `pt-[4px]` to each group `<div>` except the first to give breathing room between groups.

5. **Mobile check:** below `lg`, the aside is in normal block flow; `sticky top-0` will still work relative to the scrolling page, so the dropzone stays accessible. Verify the panel doesn't feel squished at 375 px.

**Rationale:** The structural change (sticky top / scrollable body) requires separating the aside into two independently scoped scroll regions, which is a bigger diff; keeping it in its own phase ensures the Phase 1 commit isn't entangled.

**Validation & Commit:**
> Run `tsc --noEmit` and `eslint` (frontend). Smoke-test the page at 1280 px (two-pane) and 375 px (stacked): drop a file, confirm Upload + Triage stay visible while the list scrolls, confirm section headers are clearly legible after Triage runs. Keyboard-nav: Tab through the panel, confirm focus order is Upload → Browse → Triage → doc rows. Check contrast on the new `text-[11.5px] text-ink` section headers. Once green, commit: `[Triage Panel Polish] (2/2) Complete: sticky Upload/Triage top, scrollable doc list, clearer section headers.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
|---|---|---|
| `fmtTokens` helper | Formats raw token ints as 1K / 7.5K / 94.2K | `ContextBudgetMeter.tsx` (inline) |
| Budget meter legibility | Larger + darker text for all meter labels | `web/frontend/components/feature/ContextBudgetMeter.tsx` |
| Sticky panel top | Upload dropzone + Triage button fixed at top | `web/frontend/components/feature/TriagePanel.tsx` |
| Scrollable doc list | File list + budget meter in own scroll region | `web/frontend/components/feature/TriagePanel.tsx` |
| Section header upgrade | Characters / Settings / Other at 11.5 px semibold | `web/frontend/components/feature/TriagePanel.tsx` |
