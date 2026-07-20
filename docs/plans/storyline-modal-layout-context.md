# Storyline Modal — Wider Layout + Context Selection

## 1. Introduction

The create/edit-world modal (`web/frontend/components/feature/StorylineModal.tsx`) currently stacks every authoring field in a single left column (Seal → Title → Genre → Tagline → Premise → World Primer) with a narrow right rail holding the context-files drop zone and the "Draft with Mytheca" seed. The author has asked for a wider, better-balanced layout and a richer context model:

- **Wider modal** with a two-column authoring head and a **full-width World Primer row** at the very bottom.
- **Seal + color picker** relocated to the header, right-justified on the "Edit this World" title row.
- **Title + Genre** on one row; **Tagline** full-width below; **Premise** below that.
- The drop zone keeps its drag-and-drop behavior, but each dropped context becomes a **showcased, selectable item** with toggles for the three downstream uses: **Draft** (grounds Mytheca's drafting), **RAG** (retrieval corpus), and **KG** (knowledge-graph source document).

This is a **frontend-only** change. The RAG and KG systems are deferred (per `docs/checklist.md`), so their per-file toggles are **forward-looking seams** stored on the in-memory draft and **not yet persisted or wired** to a backend — exactly the pattern already used for the context files (which ground a single generation and are never uploaded). Only the **Draft** toggle is functional: it filters which dropped files ground the `draftStoryline` / `generatePrimer` calls that already exist.

The approach: first extend the in-memory context model (`ReadDoc` usage flags + a `docsForDraft` filter) and wire the draft/primer grounding to honor the Draft toggle; then restructure the modal's JSX into the requested layout and add the per-context toggle UI.

## 2. Gaps & Unanswered Questions

- **Default toggle state (assumption):** newly dropped files default to **all three uses ON** (`useDraft`, `useRag`, `useKg` = true). This preserves today's behavior (dropped files ground generation by default) and lets the author opt *out*. The existing test asserting a dropped file's text reaches generation stays green.
- **RAG/KG wiring (assumption):** these toggles are UI seams only — not persisted (files themselves are never persisted today) and not sent to any endpoint. They are labeled as forward-looking, consistent with the deferred RAG plan. No human input required.
- **"Column to the right" placement (assumption):** the showcased context list lives in the right rail (the column to the right of the authoring form), beneath the drop zone. At `lg`, the drop zone and the list sit side-by-side; below `lg` they stack. This honors "a column to the right that showcases the contexts" without risking overflow on narrow modals.
- **Mobile mode toggle (assumption):** the existing By-hand / Agentically toggle is retained. By-hand shows the form + World Primer + submit; Agentically shows the rail (seed + context). World Primer and the submit footer are full-width on desktop and part of the by-hand view on mobile.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1: Context usage model + draft grounding

- **Locations:** `web/frontend/lib/readDocs.ts` (extend `ReadDoc`; add `docsForDraft`), `web/frontend/features/library/useLibraryState.ts` (`draftStoryline`, `generatePrimer` grounding), `web/frontend/lib/readDocs.test.ts` (helper tests).
- **Work:**
  - Add optional `useDraft?`, `useRag?`, `useKg?` flags to the `ReadDoc` interface. Keep `readDocFiles` pure (still returns `{ name, text }`); defaults are applied where files enter the draft (Phase 2's `addFiles`).
  - Add `docsForDraft(docs: ReadDoc[]): ReadDoc[]` returning files with `useDraft !== false` (treats undefined as on, for backward compatibility), and document that `concatDocs` should be fed this filtered list for generation grounding.
  - In `useLibraryState`, change both grounding sites to `concatDocs(docsForDraft(draft._docFiles ?? []))` so only Draft-enabled files ground the metadata draft and the World Primer.
  - Tests: `docsForDraft` includes undefined/true and excludes `false`; `concatDocs(docsForDraft(...))` drops a `useDraft:false` file's text.
- **Rationale:** the data/filter seam must exist before the toggle UI can drive it, and wiring the Draft toggle now keeps the one functional path correct.
- **Action:** Run `npm test` (Vitest) + `npm run typecheck` for the frontend. Once green, commit: `[Storyline Modal Layout + Context] (1/2) Complete: context usage flags + Draft-only grounding helper.`

### Phase 2: Modal layout restructure + context toggles UI

- **Locations:** `web/frontend/components/feature/StorylineModal.tsx`, `web/frontend/features/library/LibraryView.editors.test.tsx` (extend storyline-modal coverage), `docs/component-map.md` / `docs/design-system.md` (note the new modal layout if they describe it), `docs/checklist.md` (status).
- **Work:**
  - **Width:** widen the modal panel (e.g. `sm:w-[560px] md:w-[980px] lg:w-[1100px]`).
  - **Header:** keep the eyebrow + title on the left; move the **Seal preview + symbol grid + color swatches** into a right-justified cluster on the same row, with the `CloseButton` pinned top-right. The cluster wraps below the title on narrow widths.
  - **Authoring form column (left of the upper body):** Title + Genre in a two-up row (`grid grid-cols-1 sm:grid-cols-2`), then full-width Tagline, then full-width Premise (taller).
  - **Right rail (context column):** "Draft with Mytheca" seed + button (kept), then the **Context files** drop zone (drag-and-drop unchanged), then the **showcased context list** — each item shows the file name + three toggle chips (Draft / RAG / KG) with `aria-pressed`, plus the existing remove control. Drop zone + list sit side-by-side at `lg`, stacked below.
  - **World Primer:** move out of the left column into its **own full-width row** spanning the modal beneath both columns (eyebrow + Generate button + description + a taller `TextArea`).
  - **Footer:** error + Cancel / Create World, full-width and right-justified.
  - **Toggle handler:** add a small `setDocFlag(name, key)` in the modal that flips the flag on the matching `_docFiles` entry via `lib.setDraft`. `addFiles` seeds new docs with all three flags ON.
  - **Tests:** extend the editors test — assert Title/Genre/Tagline/Premise and World Primer remain reachable in the new layout; assert a dropped file shows Draft/RAG/KG toggles; toggling **Draft off** then generating the primer omits that file's text from `docsOverview`.
  - **a11y/responsive:** labelled toggle buttons (`aria-pressed`), keyboard-operable; verify no horizontal overflow and a sane layout at 320 / 375 / 768 / 1024.
- **Rationale:** the layout and the toggle UI are one cohesive visual change; splitting them would leave the modal half-restructured between commits.
- **Action:** Run `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`; perform the accessibility + responsive pass (keyboard, focus, contrast, 320/375/768/1024) via the dev preview if the working dir is free, else document the structural verification. Once green, commit: `[Storyline Modal Layout + Context] (2/2) Complete: wider two-column head, header seal, full-width World Primer, per-context Draft/RAG/KG toggles.`

### Finalization: merge to main

- After both phases are committed and green, merge `feat/storyline-modal-layout-context` into `main` (resolving any conflicts), update `docs/checklist.md`, and commit the merge. **Do not push** unless asked.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Context usage flags | `useDraft`/`useRag`/`useKg` on `ReadDoc` + `docsForDraft` filter | `web/frontend/lib/readDocs.ts` |
| Draft-only grounding | Generation grounds with Draft-enabled files only | `web/frontend/features/library/useLibraryState.ts` |
| Helper tests | `docsForDraft` / filtered `concatDocs` coverage | `web/frontend/lib/readDocs.test.ts` |
| Modal layout | Wider modal, header seal, Title+Genre row, full-width Premise + World Primer | `web/frontend/components/feature/StorylineModal.tsx` |
| Context toggles UI | Showcased per-file Draft/RAG/KG selection | `web/frontend/components/feature/StorylineModal.tsx` |
| Modal tests | New-layout reachability + toggle-driven grounding | `web/frontend/features/library/LibraryView.editors.test.tsx` |
| Docs | Layout note + status | `docs/component-map.md`, `docs/design-system.md`, `docs/checklist.md` |
