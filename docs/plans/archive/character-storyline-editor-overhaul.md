# Character & Storyline Editor Overhaul

## 1. Introduction

This plan restructures Mytheca's create/edit modals — the agentic **Character Creator**
(`CharacterModal.tsx`), the write-first **Storyline editor** (`StorylineModal.tsx`), and the
shared **setting/scenario** editor (`EntityModal.tsx`) — to address a batch of UX complaints.
The work is **frontend-only** (`web/frontend/`): no backend, schema, or API changes. We tighten
the shared editing chrome (bolder/larger field labels, tighter spacing, independent scroll areas
for the edit column vs. the Context Files column), collapse the redundant double titles into one,
relocate the storyline seal picker and the character portrait editor, drop the Character editor's
Goal/Secret fields, add a non-functional voice-sample upload affordance beside the speech field,
and move the portrait prompt/render flow into its own pop-up reached by an **Edit image** button.

The data model is untouched: `goal`/`secret` stay on the `Character` wire shape and in the read-only
profile — they're only removed from the *editor form*. The portrait pipeline, stat proposal, and
agentic draft handlers in `useLibraryState` are reused as-is; only their presentation moves.

## 2. Gaps & Unanswered Questions

- **Goal/Secret removal scope (assumption):** remove only from the Character *editor form*. Keep the
  fields on the `Draft`/`Character` types, in `DEFAULT_DRAFTS`, in `submit()` (defaulting to `"—"`),
  and in `CharacterProfileModal` so existing data and the agent draft are preserved. No backend change.
- **Voice-sample upload (assumption):** non-functional placeholder for a future text-to-speech feature.
  Render a compact, clearly-disabled drop/upload affordance to the right of the speech field with a
  "coming soon" hint. No state, no file reading, no persistence.
- **Portrait "own page" (assumption):** a nested in-app **Modal** (sub-dialog, raised z-index), not a
  new route. Triggered by an **Edit image** button under a compact portrait preview that lives at the
  top of the right column (above "Draft with Mytheca"). The pop-up holds the preview + positive/negative
  prompts + "Generate prompts" + "Generate portrait".
- **Promoted title styling (assumption):** the eyebrow text ("Edit Character"/"New Character",
  "Edit Storyline"/"New Storyline", "Edit Setting", etc.) becomes the single modal title at the current
  main-title size (`font-display text-[22px] font-bold text-ink`); the descriptive second line
  ("Forge a Character", "Edit this World", …) is removed. The `*-modal-title` id moves to the kept line.
- **Independent scroll areas (assumption):** applied at `lg+` (where the two columns sit side by side)
  via an opt-in `Modal` prop; below `lg` the whole dialog keeps scrolling (stacked columns, no nested
  scroll on phones). Live in-browser responsive pass remains deferred per the standing shared-dir
  constraint (see `docs/checklist.md`).

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Shared chrome: bold/larger labels + independent scroll seam
- **Locations:** `web/frontend/components/ui/FieldLabel.tsx`, `web/frontend/components/ui/Modal.tsx`.
- **Work:**
  - `FieldLabel`: bump the `Eyebrow` size (≈9 → ≈11) and add `font-bold`, slightly looser line so the
    field headers read clearly. This improves every editor at once (it backs `TextField`/`TextArea`).
  - `Modal`: add an opt-in `splitScroll?: boolean`. When set, the dialog uses
    `overflow-hidden lg:flex` (instead of `overflow-auto`) so inner columns own their own
    `lg:overflow-y-auto lg:min-h-0` scroll; below `lg` it falls back to whole-dialog `overflow-auto`.
    Default false → all other modals unchanged.
- **Rationale:** these are the shared primitives; doing them first lets the per-modal phases just opt in.
- **Action:** Run `npm test` (Vitest) + `npm run typecheck` + `npm run lint` + `npm run build`. Once green,
  commit: `Editor Overhaul (1/5) Complete: bolder field labels + split-scroll Modal seam.`

### Phase 2 — Character editor: fields (Goal/Secret out, voice upload in) + scroll opt-in
- **Locations:** `web/frontend/components/feature/CharacterModal.tsx`.
- **Work:**
  - Remove the Goal/Secret `grid` row from the form (keep the fields in `editor.ts`/`useLibraryState`).
  - Wrap the "Voice / speech style" `TextField` in a row with a compact, disabled **voice-sample upload**
    affordance to its right (dashed box / "Upload" label, `aria-disabled`, "coming soon" hint) — purely
    presentational for the future TTS feature.
  - Opt the modal into `splitScroll`; give the main editing column `lg:overflow-y-auto lg:min-h-0` and
    pass the same to `ContextFilesPanel` (Phase 4 wires the panel side). Tighten inter-field spacing.
- **Rationale:** isolates the Character form-field edits before the larger portrait restructure.
- **Action:** Run `npm test` + typecheck + lint + build. Once green, commit:
  `Editor Overhaul (2/5) Complete: Character form — drop Goal/Secret, add voice-sample upload, split scroll.`

### Phase 3 — Character editor: portrait → compact preview + Edit-image pop-up; single title
- **Locations:** `web/frontend/components/feature/CharacterModal.tsx`, new
  `web/frontend/components/feature/PortraitModal.tsx`.
- **Work:**
  - Collapse the header to one promoted title ("Edit Character"/"New Character"); move the
    `character-modal-title` id onto it; remove "Forge a Character"/"Edit this Character".
  - New `PortraitModal`: a nested `Modal` (`z=70`, `labelledBy`) holding the existing portrait UI —
    positive/negative prompt `TextArea`s, "❖ Generate prompts" (uses prior context), "❖ Generate
    portrait", and the rendered-WebP/monogram preview. Controlled `open`/`onClose` from `CharacterModal`
    local state (`useState`); all generate handlers stay on `lib`.
  - In the right column, **above** "Draft with Mytheca", add a compact portrait preview (full image or
    monogram placeholder) + an **Edit image** button that opens `PortraitModal`. Remove the old
    full-width Portrait section.
- **Rationale:** the largest structural move; done after the field edits so diffs stay reviewable.
- **Action:** Run `npm test` + typecheck + lint + build (update `CharacterModal.test.tsx` to open the
  pop-up before exercising prompts/portrait). Once green, commit:
  `Editor Overhaul (3/5) Complete: Character portrait pop-up + single title.`

### Phase 4 — Storyline editor: single title, relocate seal, split scroll
- **Locations:** `web/frontend/components/feature/StorylineModal.tsx`,
  `web/frontend/components/feature/ContextFilesPanel.tsx`.
- **Work:**
  - Collapse the header to one promoted title ("Edit Storyline"/"New Storyline"); move
    `storyline-modal-title` onto it; remove "Forge a New World"/"Edit this World".
  - Move the seal cluster (preview + symbol grid + color grid) out of the header into the right column,
    **above** "❖ Draft with Mytheca", under a "Seal" `FieldLabel`.
  - Opt into `splitScroll`; main column `lg:overflow-y-auto lg:min-h-0`. Add an optional
    `scroll?: boolean` (or `className` passthrough) to `ContextFilesPanel` so it gets
    `lg:overflow-y-auto lg:min-h-0` too — used by both Storyline and Character modals.
- **Rationale:** mirrors the Character header/scroll treatment; the seal move is storyline-specific.
- **Action:** Run `npm test` + typecheck + lint + build (existing editors tests select the seal by its
  button names, which survive the move). Once green, commit:
  `Editor Overhaul (4/5) Complete: Storyline single title + seal relocated + split scroll.`

### Phase 5 — EntityModal (setting/scenario) title consistency + docs
- **Locations:** `web/frontend/components/feature/EntityModal.tsx`, `docs/checklist.md`,
  `docs/component-map.md` (if the new `PortraitModal` warrants a row).
- **Work:**
  - Collapse the setting/scenario editor header to one promoted title
    ("Edit Setting"/"New Setting", "Edit Scenario"/"New Scenario"); drop the `meta.create`/`meta.edit`
    descriptive line; move `entity-modal-title` onto the kept line.
  - Update docs: add a checklist entry for this work (with the deferred live a11y pass), and note
    `PortraitModal` in the component map.
- **Rationale:** brings the last editor into line and records the change per the documentation gate.
- **Action:** Run `npm test` + typecheck + lint + build. Once green, commit:
  `Editor Overhaul (5/5) Complete: EntityModal single title + docs.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Bolder field labels | Larger, bold `FieldLabel` across all editors | `web/frontend/components/ui/FieldLabel.tsx` |
| Split-scroll seam | Opt-in `Modal` prop for independent column scroll | `web/frontend/components/ui/Modal.tsx` |
| Character form | Goal/Secret removed; disabled voice-sample upload beside speech | `web/frontend/components/feature/CharacterModal.tsx` |
| Portrait pop-up | Nested portrait prompt/render dialog + compact preview & Edit-image trigger | `web/frontend/components/feature/PortraitModal.tsx`, `CharacterModal.tsx` |
| Storyline editor | Single title; seal picker relocated above Draft-with-Mytheca; split scroll | `web/frontend/components/feature/StorylineModal.tsx` |
| Context panel scroll | Optional independent-scroll classes on the shared panel | `web/frontend/components/feature/ContextFilesPanel.tsx` |
| Entity editor | Single promoted title for setting/scenario | `web/frontend/components/feature/EntityModal.tsx` |
| Tests | Updated character modal + editors tests for the new structure | `web/frontend/features/library/CharacterModal.test.tsx`, `LibraryView.editors.test.tsx` |
| Docs | Checklist + component-map updates | `docs/checklist.md`, `docs/component-map.md` |
