# Scenario Editor — Three-Column Layout

## 1. Introduction

The `EntityModal` (scenario editor) currently uses a two-column layout — a by-hand form on the left and an agentic aside (Scene art + Draft with Mytheca) on the right — with no context-files upload column. `CharacterModal` and `SettingModal` both follow a richer three-column pattern: (1) main edit form, (2) image + draft aside, and (3) a detached `ContextFilesPanel` for dropping `.txt`/`.md` reference files that ground the "Draft with Mytheca" call.

This plan restructures `EntityModal` to match that established pattern exactly. No backend or data-layer changes are needed — `draft._docFiles → draftScenario` is already wired in `useLibraryState` (lines 628–629); only the UI needs updating. The result: authors can now drop a pre-written scenario draft as a context file and use "Draft with Mytheca" to shape it into a fully-structured scenario.

---

## 2. Gaps & Unanswered Questions

- **Footer placement** — currently the delete/cancel/save footer lives *inside* the form column. `SettingModal` places it *outside* the inner `md:flex` as a full-width block. This plan moves the footer out to match, so it stays visible in both manual and agentic modes on desktop. *Assumption: matching the established pattern is correct; confirmed by reading the existing CharacterModal/SettingModal structure.*
- **`md:gap-[26px]` on the inner flex** — the current EntityModal uses an explicit gap; CharacterModal/SettingModal omit it and instead use `md:pr-[26px]` on the form column and `md:pl-[26px]` on the aside. This plan adopts that spacing style. *Assumption: consistent with the rest of the codebase.*
- **No backend or schema changes** — `Draft._docFiles?: ReadDoc[]` already exists in `editor.ts:56`; `draftScenario()` in `useLibraryState.ts:628–634` already reads it. *No changes needed outside the frontend.*

---

## 3. Phases

### Phase 1 — Restructure `EntityModal.tsx` to three-column layout

**Goal:** Bring `EntityModal` to structural parity with `CharacterModal`/`SettingModal`.

**Locations:**
- `web/frontend/components/feature/EntityModal.tsx`

**Changes (in order):**

1. **Import `ContextFilesPanel`** — add to the import block alongside the existing feature imports.

2. **Update `Modal` props** — add `externalClose` and `splitScroll` to the `<Modal>` element (same as `CharacterModal`/`SettingModal`).

3. **Replace outer padding div with the `lg:flex` wrapper pattern:**
   - Replace `<div className="p-[22px_26px_24px]">` with two nested divs:
     - Outer: `className="lg:flex lg:min-h-0 lg:flex-1 lg:items-stretch"`
     - Inner (main column): `className="min-w-0 p-[22px_26px_24px] lg:flex-1 lg:min-h-0 lg:overflow-y-auto"`
   - All existing header/toggle/divider/form/aside content moves into the main column div.

4. **Fix inner `md:flex` container** — remove `md:gap-[26px]` from `<div className="md:flex md:items-stretch md:gap-[26px]">` (spacing is now handled by the columns' padding, matching Setting/CharacterModal).

5. **Add `md:pr-[26px]` to the form column** — change `md:min-w-0 md:flex-1` to `md:min-w-0 md:flex-1 md:pr-[26px]` on the form column div. This takes up the removed gap.

6. **Adjust agentic aside** — change aside width from `md:w-[330px]` to `md:w-[300px]` and add `mt-[18px] md:mt-0` (matching Setting/CharacterModal's aside sizing). The interior (Scene art section + Draft with Mytheca) stays unchanged.

7. **Move footer outside inner flex** — extract the `<div className="mt-[22px] flex items-center justify-between gap-[10px]">` footer (delete + cancel + save) and the error `<p role="alert">` out of the form column and place them after the closing `</div>` of the `md:flex` container, wrapped in `<div className={cn(agentic && "hidden md:block")}>` (matching SettingModal's footer pattern). Adjust spacing to `mt-[20px]`.

8. **Add `ContextFilesPanel` as third column** — directly before the closing `</div>` of the `lg:flex` outer wrapper, add:
   ```tsx
   <ContextFilesPanel
     docFiles={d._docFiles ?? []}
     setDocFiles={(docs) => lib.setDraft("_docFiles", docs)}
     inputId="scenario-docs-input"
     show={agentic}
     scroll
   />
   ```

**Rationale:** `_docFiles` is already read by `draftScenario()` in `useLibraryState`; adding the panel wires the UI to the existing data path with no further changes. The `show={agentic}` prop hides it on small screens when in manual mode, consistent with the other modals. The `scroll` prop enables independent vertical scroll on `lg+` via the `splitScroll` modal behaviour.

> *Action: Run `npm run typecheck` and `npm test` (Vitest) to confirm the restructured component renders and no type errors are introduced. Also run `npm run build` to verify the production build is clean. Once green, commit: `[Scenario Editor Three-Column] (1/2) Complete: Restructure EntityModal to 3-column layout — form, scene-art/draft aside, and ContextFilesPanel.`*

---

### Phase 2 — Tests + docs update

**Goal:** Update `EntityModal.test.tsx` to cover the new ContextFilesPanel column; update `docs/component-map.md` to record the change.

**Locations:**
- `web/frontend/components/feature/EntityModal.test.tsx`
- `docs/component-map.md`
- `docs/checklist.md`

**Changes:**

1. **Update `makeLib` helper in `EntityModal.test.tsx`** — add `_docFiles: []` to the `draft` baseline so the ContextFilesPanel receives its required prop without type errors.

2. **Add test: ContextFilesPanel renders in agentic mode** — render with `modal.mode === "agentic"` (the existing default) and assert that the "Context files" eyebrow and "Browse files" label are present in the document.

3. **Add test: ContextFilesPanel is hidden in manual mode at small viewport** — render with `modal.mode === "manual"` and assert the context files section has the `hidden` class (the CSS-only hide; no viewport resize needed in Vitest since it's a class check).

4. **Existing tests stay green** — the scene-art and modal render tests should be unaffected. Confirm them in the same run.

5. **Update `docs/component-map.md`** — under `EntityModal`, note that it now uses `externalClose`/`splitScroll` Modal props and includes a `ContextFilesPanel` column (matching Setting/Character).

6. **Update `docs/checklist.md`** — add an entry for this plan (done) and carry forward the standing a11y/responsive deferred note.

> *Action: Run the full frontend suite (`npm test`) and typecheck (`npm run typecheck`) plus `npm run build`. Once green, commit: `[Scenario Editor Three-Column] (2/2) Complete: Tests + docs — ContextFilesPanel column coverage and component-map update.`*

---

## 4. Deliverables

| Deliverable | Description | Location |
|---|---|---|
| Restructured EntityModal | 3-column layout: form / scene-art+draft aside / context-files | `web/frontend/components/feature/EntityModal.tsx` |
| ContextFilesPanel wired | Upload column grounding `draftScenario` | Same file (imports + JSX) |
| Updated tests | ContextFilesPanel presence + hidden-in-manual-mode coverage | `web/frontend/components/feature/EntityModal.test.tsx` |
| Component-map update | EntityModal entry updated | `docs/component-map.md` |
| Checklist entry | Plan logged with a11y defer noted | `docs/checklist.md` |
