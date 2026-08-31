# Mytheca — Website Overhaul

**Status:** in progress · branch `claude/website-overhaul-22b48a` · started 2026-08-31
**Baseline audit:** `docs/audit/audit-report.md` · **Profile:** `docs/audit/audit-profile.yaml`

## 1. Introduction

The owner's brief: the site should look cleaner and more modern, work well on small screens, and gain
the "pizazz" of a modern site — strong structure, and content that loads in visually appealing ways.
The current design language is explicitly **liked** and stays; what is missing is structure. Keyboard
operability is a welcome bonus rather than a gate, and SEO is out of scope.

The baseline audit found the mechanism. Across 136 component files there are **625 arbitrary font
sizes over 30 distinct values** and **1,335 arbitrary spacing values over 165 distinct values**, while
only **29 of 136** files use the type tokens the project already ships. Every component was tuned to
look right in isolation, so nothing aligns across components — which is exactly the "polished parts,
unpolished whole" the owner described. The same habit produces the mobile failures: **776** form
controls render below the 16px iOS floor and **184** text findings sit below 14px.

The approach is therefore **foundation-first, not screen-first**. Phases 1–3 build the scales, the page
frame and the motion system; phases 4–6 rebuild each surface onto them, deleting arbitrary values at
their source; phase 7 is the keyboard pass; phases 8–9 add the multi-provider LLM layer; phase 10
re-audits as a diff. Every route and every feature survives unchanged — this is a restructuring of how
the UI is *expressed*, not a change to what the app *does*.

## 2. Gaps & Unanswered Questions

**Simple gaps — assumption stated, proceeding.**

- **Density will change.** Raising type to the 16px form floor and a ≥14px body floor makes the app
  visibly larger. *Assumption:* meet the floors, keep the manuscript aesthetic, and retain the four
  existing `.fs-*` presets so the **Compact** preset lands near today's density. The floors are
  enforced on form controls and body copy; decorative eyebrows and tags may stay small where they are
  genuinely secondary and pass contrast at their size.
- **Routes and IA are unchanged.** All 8 routes in `docs/routes.md`, every feature, every component's
  behaviour. *Assumption:* the owner wants the frame rebuilt, not the app redesigned.
- **LLM scope.** "Multiple options for the LLM output" is read as **multiple providers and live model
  choice**. *Assumption:* make the already-stored-but-inert `provider` field load-bearing and ship
  adapters for OpenAI-compatible (the current path), Anthropic, Gemini and Ollama.
- **`web/shared/contracts/` stays empty**; the FE↔BE mirror stays hand-maintained in
  `lib/events.ts` + `lib/types.ts`, per the global rules.

**Complex gap — human intervention is needed to answer this question.**

- **Per-role model routing** ("cheap model for the planner, strong model for prose") is the main
  practical reason to support several providers at once, and the audit found there is currently no seam
  for it: one global model id serves ~25 agent call sites via a positional `LlmConn` 4-tuple. Phase 8
  builds the seam that would make it possible, but **does not** ship per-role routing — that is a
  product decision about how the engine spends money and latency, not an implementation detail.
  Recorded in `docs/checklist.md`.

## 3. Step-by-Step Instructions

### Phase 1 — The scales

- **Locations:** `web/frontend/styles/themes.css` (type scale, spacing scale, radius scale, elevation,
  per-entity accent *on-surface* variants), `web/frontend/app/globals.css` (`@theme inline` mapping),
  `web/frontend/lib/graphColors.ts` + `lib/cardArt.ts` + `lib/seals.ts` (decorative palettes gain
  AA-safe text variants), `utils/scripts/check_contrast.py` (extend the gate to cover the entity
  palettes and every theme, not only the declared theme tokens).
- **Rationale:** every later phase deletes arbitrary values by replacing them with a token. The tokens
  have to exist first, and the contrast gate has to cover them or M-2 recurs silently. This phase adds
  tokens and changes no component, so it is independently verifiable.
- **Fixes:** the root cause of M-1, M-2, M-3.
- *Action: run `uv run python utils/scripts/check_contrast.py`, `node utils/scripts/check_frontend_css.mjs`, and `npm test`. Once green, commit: `[Website Overhaul] (1/10) Complete: type, spacing, radius and accent scales, with the contrast gate extended to cover them.`*

### Phase 2 — The page frame

- **Locations:** `web/frontend/app/layout.tsx` (`export const viewport` with per-theme `themeColor`;
  root `title.template`), `web/frontend/components/layout/AppShell.tsx` (`<main id="main">`, skip
  link), new `web/frontend/components/ui/{Page,Section,Stack,Cluster}.tsx`, new
  `web/frontend/components/layout/HeaderBar.tsx` (shared chassis for `AppHeader` + `SceneHeader`),
  `web/frontend/styles/themes.css` (declare the real `--header-h`), `app/globals.css` (consume it in
  the `scroll-margin-block-start` rule and as `scroll-padding-top`), new `app/loading.tsx`,
  `app/error.tsx`, `app/not-found.tsx`.
- **Rationale:** the frame is what makes a page feel structured, and nothing below it can supply one.
  Doing this before the surface rebuilds means each surface is rebuilt *into* a frame rather than
  around a gap.
- **Fixes:** B-2, M-4, N-1, N-3; sets up B-1.
- *Action: run `npm test`, `npm run typecheck`, `npm run lint`, and a responsive pass at 320/375/768/1024. Once green, commit: `[Website Overhaul] (2/10) Complete: viewport + theme-color, the main landmark and skip link, layout primitives, a shared header chassis and a real --header-h.`*

### Phase 3 — The motion system

- **Locations:** `web/frontend/lib/motion.ts` (one source for durations, easings, distances and
  stagger), `web/frontend/styles/themes.css` (`@keyframes reveal-in`, double-gated reveal rules), new
  `web/frontend/components/ui/Reveal.tsx` + `hooks/use-reveal.ts` (IntersectionObserver fallback),
  `web/frontend/components/layout/MotionProvider.tsx`.
- **Rationale:** this is the "pizazz". It must be built once, correctly, before it is applied 40 times.
  The **fail-open rule is blocker-severity**: the hidden state lives in a `@keyframes from` block applied
  by `animation-fill-mode: both`, never as a static `opacity: 0`, and reveal styling is positively gated
  by **both** `@media (prefers-reduced-motion: no-preference)` **and** `@supports (animation-timeline: view())`,
  with the JS path scoped under a `.js-reveal` root class — so losing any single gate leaves content
  visible. One-shot observers must `unobserve` in the callback, use `threshold: 0` + `rootMargin`, and
  handle bfcache via `pageshow`.
- **Fixes:** the `expressive` fit gap; N-5 (batch reads before writes).
- *Action: run `npm test` plus `audit_motion.py` against `/` and the player route — it runs the reduced-motion and JS-disabled passes itself and diffs them. Confirm zero fail-open findings. Once green, commit: `[Website Overhaul] (3/10) Complete: a centralised motion system and a fail-open scroll-reveal primitive.`*

### Phase 4 — Library and storyline surfaces

- **Locations:** `web/frontend/features/library/**`, `web/frontend/components/feature/{CharacterColumn,SettingColumn,ScenarioColumn,ColumnChrome,LibraryTabs,CharacterCard,SettingCard,ScenarioCard,ScenarioCarousel}.tsx`, `web/frontend/components/layout/AppHeader.tsx`.
- **Rationale:** the front door, and the simplest surface — it proves the foundation before the player
  depends on it. Every arbitrary type/spacing/radius/hex value in these files is replaced by a token.
- *Action: run the co-located tests for every touched component, `npm run typecheck`, and `audit_responsive.py` + `audit_a11y.py --all` against `/` and `/embergate`. Once green, commit: `[Website Overhaul] (4/10) Complete: the library and storyline surfaces rebuilt on the scales and the page frame.`*

### Phase 5 — Story player

- **Locations:** `web/frontend/features/story-player/**`, `web/frontend/components/feature/{TranscriptBeat,Composer,DirectionRow,TurnStatusStrip,SceneIntro,SceneLoader,CastRail,CastRailContent,DirectorRail,DirectorRailContent,CharacterDossier,CharacterDossierContent,SceneRailBar,SceneMenu,SceneConfigMenu,JumpToLatest,PlaythroughTray,BeatControls,TranscriptFootBar}.tsx`, `web/frontend/components/layout/SceneHeader.tsx` (extract its menu composition and its two inline sub-components).
- **Rationale:** the largest and most-used surface, and the one carrying B-1 (`"Play-throughs"` lost at
  320px) and the composer's `aria-allowed-attr` violation. It depends on phases 1–3 and on the
  `SegmentedGroup` primitive the header extraction produces.
- **Fixes:** B-1 (player), M-1 (composer), N-4.
- *Action: run the co-located tests for every touched component plus the story-player feature tests, then `audit_responsive.py` + `audit_a11y.py --all` against `/embergate/salt`, confirming the 320px content-loss blocker is cleared. Once green, commit: `[Website Overhaul] (5/10) Complete: the story player rebuilt — 320px content loss cleared and the composer brought to the 16px floor.`*

### Phase 6 — Options, editor, documents, creator

- **Locations:** `web/frontend/features/options/**`, `web/frontend/features/documents/**`, `web/frontend/features/library/{StorylineCreatorView,useStorylineCreator}.tsx`, `web/frontend/components/feature/{DocumentsTable,ContextFilesPanel,StatsEditor,ScenarioForm,PromptOverridesEditor,TriagePanel,SourceDocumentsPanel}.tsx`, `web/frontend/components/ui/{TextField,TextArea,MultiSelect}.tsx`.
- **Rationale:** these carry the overwhelming majority of the 776 auto-zoom findings (465 on `/…/edit`
  and 232 on `/options` alone) and the three remaining 320px content-loss blockers. Form primitives are
  fixed here once so every consumer inherits the floor.
- **Fixes:** B-1 (docs, edit, new), M-1 (bulk), M-5, N-4.
- *Action: run the co-located tests, `npm run typecheck`, and `audit_responsive.py` + `audit_a11y.py --all` against `/options`, `/storylines/new`, `/storylines/embergate/edit` and `/storylines/embergate/documents`. Confirm zero `ios-input-autozoom` and zero `reflow-content-loss`. Once green, commit: `[Website Overhaul] (6/10) Complete: the options, editor, documents and creator surfaces rebuilt; the 16px form floor enforced in the primitives.`*

### Phase 7 — Keyboard and accessibility pass

- **Locations:** `web/frontend/hooks/use-focus-trap.ts`, `web/frontend/components/ui/{Modal,Drawer}.tsx`, `web/frontend/components/layout/AppShell.tsx` (route-change focus), `web/frontend/components/feature/{MentionMenu,SceneMenu,CoachMark,TranscriptAnnouncer}.tsx`, `web/frontend/hooks/use-scene-shortcuts.ts`.
- **Rationale:** the owner's explicit bonus. Runs after the rebuilds so it is done once against final
  markup. Scope is the seven-item minimum pass plus: focus moves into and returns from every dialog,
  Shift+Tab exits in both directions, focus is never entirely obscured by sticky chrome, live regions
  exist in the initial DOM *before* content is injected, and single-key shortcuts are gated so they do
  not fire while typing.
- **Fixes:** M-6, and the minimum pass.
- *Action: run `npm test` and a manual keyboard pass over the player and one form end to end. Once green, commit: `[Website Overhaul] (7/10) Complete: keyboard operability — focus management, dialog contract, live regions and shortcut gating.`*

### Phase 8 — LLM provider layer (backend)

- **Locations:** new `web/backend/app/services/llm_providers/` (`base.py`, `openai_compatible.py`, `anthropic.py`, `gemini.py`, `ollama.py`, `registry.py`), `web/backend/app/services/llm.py` (dispatch `_completion_request`, `_headers`, the SSE parser, `_prompt_tokens`/`_cached_tokens`/`_reasoning_field` through the adapter), `web/backend/app/services/llm_backend.py` (capability discovery per provider), `web/backend/app/agents/_common.py` (`LlmConn` becomes a frozen dataclass carrying provider), `web/backend/app/agents/{reflection_agent,recap_agent}.py` (drop the duplicate aliases), `web/backend/app/agents/{planner_agent,task_agent,lookup_agent}.py` + `storyline_edit/core.py` (one `schema=` kwarg replaces four hand-written structured-output dialects), `web/backend/app/services/settings_store.py` + `schemas/settings.py` (multi-endpoint config with per-provider credentials), `web/backend/app/routes/options.py`.
- **Rationale:** the `provider` field is already stored, returned and displayed but dispatched on
  nowhere — it is the seam, and it must become load-bearing rather than gain a parallel field. Doing
  the adapter before the UI means the Options page has something real to talk to. Retries with backoff
  and `Retry-After` handling land here too: hosted providers rate-limit where local ones do not.
- **Tests:** `utils/tests/backend/services/test_llm_providers.py` (per-adapter request shaping and
  response parsing against mock transports), `utils/tests/backend/services/test_llm_dispatch.py`.
- *Action: run `uv run pytest utils/tests/backend/{services,agents,api}`. Once green, commit: `[Website Overhaul] (8/10) Complete: a provider adapter layer — the stored provider field is now load-bearing, with OpenAI-compatible, Anthropic, Gemini and Ollama adapters.`*

### Phase 9 — Provider and model selection UI

- **Locations:** `web/frontend/features/options/tabs/` (provider picker + live model picker), `web/frontend/lib/api.ts` + `lib/types.ts` (contract mirror), `web/backend/app/routes/options.py` (discovery endpoint returning **200 with `ok: false`** on an unreachable endpoint rather than raising).
- **Rationale:** discovery must never raise into a UI path — an unreachable local server is a normal
  state, not an exception. The three empty states (no provider configured · provider unreachable ·
  provider reachable but serving no models) are distinct and must read differently. Connect and read
  timeouts are separated: a local server that is not running fails in under two seconds, while local
  generation legitimately takes minutes.
- **Tests:** co-located tests for the pickers covering all three empty states; `utils/tests/backend/api/test_options_llm_discovery.py`.
- *Action: run `uv run pytest utils/tests/backend/api`, `npm test`, and an a11y + responsive pass on `/options`. Once green, commit: `[Website Overhaul] (9/10) Complete: provider and live model selection in Options, with honest empty states.`*

### Phase 10 — Re-audit and documentation

- **Locations:** `docs/audit/audit-report.md` (re-audit as a **diff** against the retained baseline JSON), `docs/audit/audit-profile.yaml` (`motion.scroll_reveals: true`, `reduced_motion_handled` verified, `stack.rendering` recorded), `docs/design-system.md`, `docs/component-map.md`, `docs/routes.md`, `docs/architecture.md`, `docs/api-contract.md`, `docs/data-flow.md`, `docs/workflow.md`, `docs/deployment.md`, `.env.example`, `docs/checklist.md`.
- **Rationale:** the completion standard: docs updated in the same change, remaining gaps recorded.
- *Action: run the full gate — `uv run pytest`, `npm test`, `npm run typecheck`, `npm run lint`, `check_contrast.py`, `check_frontend_css.mjs`, and the four audit scripts across all seven sampled routes. Once green, commit: `[Website Overhaul] (10/10) Complete: re-audited against the baseline and every affected doc updated.`*

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Audit profile | The scoping gate every routing decision keys off | `docs/audit/audit-profile.yaml` |
| Baseline audit | Evidence-backed findings + retained JSON | `docs/audit/audit-report.md` |
| Scales | Type, spacing, radius, elevation, accent-on-surface | `web/frontend/styles/themes.css`, `app/globals.css` |
| Contrast gate | Extended to entity palettes and every theme | `utils/scripts/check_contrast.py` |
| Layout primitives | `Page` `Section` `Stack` `Cluster` | `web/frontend/components/ui/` |
| Header chassis | One bar, one height, one gutter | `web/frontend/components/layout/HeaderBar.tsx` |
| Frame | viewport + themeColor, `<main>`, skip link, route states | `web/frontend/app/` |
| Motion system | Tokens + fail-open `Reveal` | `web/frontend/lib/motion.ts`, `components/ui/Reveal.tsx` |
| Rebuilt surfaces | Library, player, options, editor, documents, creator | `web/frontend/features/`, `components/feature/` |
| Provider adapters | OpenAI-compatible · Anthropic · Gemini · Ollama | `web/backend/app/services/llm_providers/` |
| Provider config | Multi-endpoint settings + per-provider credentials | `web/backend/app/services/settings_store.py`, `schemas/settings.py` |
| Provider UI | Provider + live model pickers, three empty states | `web/frontend/features/options/tabs/` |
| Backend tests | Adapter shaping, dispatch, discovery | `utils/tests/backend/{services,api}/` |
| Frontend tests | Co-located beside each touched component | `web/frontend/**/*.test.tsx` |
