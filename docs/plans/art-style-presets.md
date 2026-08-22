# Art Style Presets — Painted · Anime · Photoreal

## 1. Introduction

Every image Mytheca generates today is locked to one look. The four image-writing agents
(`character_agent`, `setting_agent`, `scenario_agent`, `moment_agent`) hard-code the word
*watercolor* into their system prompts and end every positive prompt with painterly style
tags; the bundled ComfyUI workflow (`utils/workflows/ZiT-Workflow.json`) hard-wires
`zit_watercolor.safetensors` at strength 0.8 through node `72`
(`LoraLoaderModelOnly`); and the agents' example negative prompts actively push
`photorealistic, 3d render` away. There is no way to ask for a different look, and no way
to turn the LoRA off.

This plan introduces an **art style** as a first-class, three-value concept —
`painted` (the current watercolor/oil look, and the default), `anime`, and `photoreal` —
that reaches **every** image surface in the product: character portraits, setting scene
art, scenario establishing art, the in-play "Create image" moment, and the automatic
renders inside the world build. A style carries three things: the phrasing the
prompt-writing agent is told to aim for, the positive/negative tag set appended to the
finished prompt, and a LoRA decision. The style is chosen in two places — a **global
default** in `Options → Image generation`, and a **per-generation picker** on each image
surface that overrides it for that render. Each style's LoRA (file, strength, on/off) is
**editable in Options**, so `anime` can be pointed at a LoRA the moment one is installed
without a code change; out of the box `painted` keeps `zit_watercolor.safetensors` @ 0.8
and the other two bypass the LoRA node entirely.

The architecture follows Mytheca's existing shapes: a content catalog under
`web/backend/app/content/` (beside `graph_registry.py` and `stats/`), stored operator
overrides in the `comfy` `app_settings` row via `settings_store`, a surgical workflow
patch in `services/comfyui.py`, and a hand-mirrored TypeScript contract in
`web/frontend/lib/api.ts`.

---

## 2. Gaps & Unanswered Questions

**Resolved by the user (2026-08-22):**

- **Three styles, not four.** The painted look stays one option even though both
  `zit_watercolor.safetensors` and `zit_oilpainting.safetensors` are installed. The
  operator can swap `painted` onto the oil LoRA from Options if they prefer it.
- **LoRA is off for `anime` and `photoreal`, and editable per style.** No anime LoRA
  exists in `~/Models/ComfyUI/models/loras/`, and the base checkpoint
  (`zit_intorealism_zitV60.safetensors`) is already realism-leaning, so both non-painted
  styles ship prompt-only with node `72` bypassed. Every style's LoRA file/strength/enabled
  flag is stored in the `comfy` settings row and edited in Options.
- **Global default + per-generation override.** Both, everywhere.
- **All four surfaces**, not just characters: portraits, setting art, scenario art, and
  in-play scene images.

**Assumptions taken (simple gaps):**

- **Style ids are a persisted contract.** `painted` / `anime` / `photoreal` are stored in
  the `comfy` settings row and sent on request bodies. They are treated like
  `prompt_registry` keys: never renamed without a migration. An unknown or missing id
  resolves to the default rather than raising — an image request must never 400 because a
  stale client sent a retired style.
- **Bypass, don't delete.** Disabling a LoRA rewires the nodes that consume
  `["72", 0]` to consume node `72`'s own `model` input instead, leaving the node in the
  graph. This is generic (it reads the wiring rather than hard-coding `["66", 0]`), so a
  future workflow with a different loader still bypasses correctly. A workflow with no
  LoRA node is a no-op, not an error.
- **Style tags are appended defensively, not only by the agent.** The agent is told the
  style and writes matching tags, but `SceneImageModal`'s repaint path lets the player
  hand-write a positive prompt with no style tags at all. A single
  `art_styles.apply_style()` helper appends any missing tags at the service boundary, so
  all four surfaces are covered by one rule instead of four.
- **`GET /options/comfy/loras` is best-effort.** It proxies ComfyUI's
  `/object_info/LoraLoaderModelOnly` so the Options LoRA field can be a dropdown. If Comfy
  is unreachable the field degrades to a free-text input, exactly as the existing workflow
  picker does.
- **No new DB table and no migration.** Style config lives in the existing
  `app_settings["comfy"]` JSON blob, which `_comfy_defaults()` already merges under.

**No human intervention is required to start.**

---

## 3. Hierarchical Step-by-Step Instructions

Work happens on a feature branch `art-style-presets` cut from `main`, **in the existing
working directory — no worktree** (Mode B). Each phase ends with a local commit; the
branch merges into `main` at the end of Phase 8.

---

### Phase 1 — The art-style catalog and its settings contract

- **Locations:**
  - **New** `web/backend/app/content/art_styles.py` — the catalog. A frozen `ArtStyle`
    dataclass (`id`, `label`, `blurb`, `model_hint`, `portrait_tags`, `scene_tags`,
    `moment_tags`, `negative_tags`, `default_lora`, `default_lora_strength`), the ordered
    `ART_STYLES` tuple, `DEFAULT_STYLE_ID = "painted"`, and the lookups `ids()`,
    `catalog()`, `get(style_id)` (unknown → default). Also `apply_style(positive,
    negative, style, surface)` — appends whichever of the style's tags are not already
    present, case-insensitively, and returns the pair.
    - `painted` — model hint "a painterly watercolor/oil image model"; the exact tag
      strings currently hard-coded in the four agents, moved here verbatim so the default
      render is byte-identical to today's; negatives `photorealistic, 3d render`; LoRA
      `zit_watercolor.safetensors` @ 0.8.
    - `anime` — "an anime illustration model"; tags `anime illustration, cel shaded, clean
      bold linework, expressive eyes, vibrant flat colors, anime key visual`; negatives
      `photorealistic, 3d render, western cartoon`; no LoRA.
    - `photoreal` — "a photorealistic image model"; tags `photorealistic, photograph,
      natural skin texture, cinematic lighting, shallow depth of field, 85mm lens, high
      detail`; negatives `illustration, painting, anime, cartoon, 3d render`; no LoRA.
  - `web/backend/app/schemas/settings.py` — new `ArtStyleRead` (id, label, blurb,
    `loraName`, `loraStrength`, `loraEnabled`) and `ArtStyleOverride` (the writable
    triple). `ComfyConfigRead` gains `art_style: str = "painted"` and
    `styles: list[ArtStyleRead]`; `ComfyConfigUpdate` gains `art_style: str | None` and
    `styles: dict[str, ArtStyleOverride] | None`. New `ComfyLorasResponse`.
  - `web/backend/app/services/settings_store.py` — `_comfy_defaults()` gains `artStyle` and
    a `styleLoras` map keyed by style id; `get_comfy()` composes the catalog with stored
    overrides into `ArtStyleRead` rows; `update_comfy()` merges the `styles` patch
    (unknown ids ignored, mirroring `set_prompts_overrides`). New
    `resolve_art_style(db, style_id) -> ResolvedStyle` returning the `ArtStyle` plus its
    effective LoRA name/strength/enabled — the single place any caller asks "what look, and
    with which LoRA?".
  - `web/backend/app/routes/options.py` — extend the existing comfy section with
    `GET /options/comfy/loras`.
  - **New** `utils/tests/backend/services/test_art_styles.py` — catalog integrity (three
    ids, default present, every style has non-empty tags), `get()` falling back on an
    unknown id, and `apply_style()` being idempotent (running twice adds nothing).
  - `utils/tests/backend/api/test_settings_routes.py` — `artStyle` + `styles` round-trip
    through `GET`/`PATCH /options/settings`, and an unknown style id in a patch being
    ignored rather than 400-ing.
- **Rationale:** Everything downstream — the workflow patch, the services, the agents, the
  frontend — reads from this catalog and this resolver. Landing them first means every
  later phase is a consumer, not a co-designer, and the "byte-identical default" property
  is established before anything else can drift from it.
- **Validation & Commit:** *Run `uv run pytest utils/tests/backend/services utils/tests/backend/api`,
  plus `ruff check web/backend`. Once green, commit locally:
  `[Art Style Presets] (1/8) Complete: Added the three-style art catalog, its settings contract, and the per-style LoRA resolver.`
  Do not push or open a PR.*

---

### Phase 2 — Teach the ComfyUI client to patch or bypass the LoRA

- **Locations:**
  - `web/backend/app/services/comfyui.py` — new module constant `LORA_NODE = "72"`
    (documented in the module docstring's node map alongside the existing five).
    `build_prompt()` gains `lora_name`, `lora_strength`, `lora_enabled` keyword arguments:
    when enabled it patches `inputs.lora_name` / `inputs.strength_model`; when disabled it
    calls a new private `_bypass_node(wf, node_id, "model")` that repoints every input
    referencing `[node_id, 0]` at whatever `node_id` itself consumes on its `model` input,
    leaving the node orphaned but harmless. Absent node → no-op. `generate()` threads the
    three arguments through. New `list_loras(base_url)` — `GET
    /object_info/LoraLoaderModelOnly`, returning the declared `lora_name` enum, `[]` on a
    shape it does not recognise.
  - **New** `utils/tests/backend/services/test_comfyui_lora.py` — patching sets the name and
    strength; bypassing rewires the sampler chain so no input references the LoRA node;
    bypass on a workflow without node `72` leaves the graph untouched; `list_loras` parses
    a realistic `object_info` payload and survives a garbage one.
- **Rationale:** The LoRA decision is the one piece of the style that lives in the image
  graph rather than in text, and it is the piece most likely to break silently — a bypass
  that mis-wires produces a plausible-looking image from the wrong model. It gets its own
  phase and its own offline tests (the existing `MockTransport` pattern) before any caller
  depends on it.
- **Validation & Commit:** *Run `uv run pytest utils/tests/backend/services -k comfy`, then the
  full `uv run pytest utils/tests/backend/services`. Once green, commit locally:
  `[Art Style Presets] (2/8) Complete: build_prompt can now patch or generically bypass the workflow's LoRA node.`*

---

### Phase 3 — Apply the style in the three render services

- **Locations:**
  - `web/backend/app/services/portraits.py` — `generate_portrait()` gains
    `style: str | None = None`; resolves via `settings_store.resolve_art_style`, runs the
    prompts through `art_styles.apply_style(..., surface="portrait")`, and passes the LoRA
    triple to `comfyui.generate`. Module docstring loses the word "watercolor".
  - `web/backend/app/services/scene_art.py` — the same for `generate_scene_art()` with
    `surface="scene"`.
  - `web/backend/app/services/scene_moment.py` — `generate_moment()` gains `style`, applies
    it with `surface="moment"` (after `moment_agent.strip_names`, so the name guarantee that
    `EXP-2026-08-002` covers is unaffected), and passes the LoRA triple. The persisted
    `scene_image` event payload gains `style` so a beat records the look it was painted in.
  - `web/backend/app/events/envelope.py` + `web/frontend/lib/events.ts` — the mirrored
    `scene_image` payload gains the optional `style` field (mirror updated in this same
    phase, per the contract rule).
  - `utils/tests/backend/services/test_portraits.py`, `test_scene_art.py`,
    `test_scene_moment.py` (extend) — each asserts that an explicit style reaches
    `comfyui.generate` with the right LoRA arguments, that `None` falls back to the stored
    default, and that a hand-written prompt with no style tags comes out carrying them.
- **Rationale:** These three functions are the only places raw bytes are requested from
  ComfyUI, which makes them the correct and complete choke point for "every image in the
  product obeys the style" — including the world build, which calls
  `portraits.generate_portrait` / `scene_art.generate_scene_art` directly and therefore
  inherits the behaviour with no change of its own.
- **Validation & Commit:** *Run `uv run pytest utils/tests/backend/services utils/tests/backend/api`.
  Once green, commit locally:
  `[Art Style Presets] (3/8) Complete: Portrait, scene-art and moment renders resolve, apply and record an art style.`*

---

### Phase 4 — Style-aware prompt-writing agents, schemas and routes

- **Locations:**
  - `web/backend/app/agents/character_agent.py` — `_PORTRAIT_SYSTEM` becomes
    `_portrait_system(style: ArtStyle) -> str`, interpolating the style's `model_hint` and
    `portrait_tags` where the literal "watercolor" strings are today; the example negative
    line draws from `style.negative_tags` so `photoreal` no longer tells the model to avoid
    photorealism. `generate_portrait_prompts()` gains `style: str | None = None`.
  - `web/backend/app/agents/setting_agent.py` and `scenario_agent.py` — same treatment for
    their `_SCENE_ART_SYSTEM` constants and `generate_scene_art_prompts()` signatures.
  - `web/backend/app/agents/moment_agent.py` — `_MOMENT_SYSTEM` becomes
    `_moment_system(style)`; step 4 of its numbered prompt takes the style's `moment_tags`,
    which keep `LANDSCAPE_TAG` in place for every style. `DEFAULT_NEGATIVE` is composed from
    the style's negatives plus the style-independent list. `write_moment_prompt()` gains
    `style`.
  - `web/backend/app/schemas/character.py` (`PortraitPromptRequest`,
    `PortraitGenerateRequest`), `schemas/setting.py` (`SceneArtPromptRequest`,
    `SceneArtGenerateRequest`), `schemas/scenario.py` (`ScenarioSceneArtPromptRequest`,
    its generate counterpart), `schemas/play.py` (`MomentRequest`) — each gains an optional
    `art_style: str | None = None`.
  - `web/backend/app/routes/characters.py`, `routes/settings.py`, `routes/scenarios.py`,
    `routes/play.py` — pass `data.art_style` through to the agent and to the render service.
    Docstrings stop saying "watercolor".
  - `utils/tests/backend/agents/test_image_prompt_styles.py` (**new**) — for each of the four
    agents, assert the system prompt carries the requested style's tags and hint and carries
    neither of the other two styles' tags.
  - `utils/tests/backend/api/` — extend the character/setting/scenario/play route tests so an
    `artStyle` on the body reaches the agent and the render service.
- **Rationale:** The agent writes the prompt; if it is not told the style, the service's
  appended tags fight the agent's own trailing "watercolor, soft washes". Both halves must
  change together, and the request schemas are what carry the per-generation override the
  user asked for. Doing schemas and routes in the same phase keeps the API contract
  consistent at every commit boundary.
- **Validation & Commit:** *Run `uv run pytest` (full backend suite — this phase touches four
  routes and four agents), plus `ruff check web/backend`. Update `docs/api-contract.md` for the
  four request bodies and the `scene_image` payload in this same commit. Once green, commit locally:
  `[Art Style Presets] (4/8) Complete: The four image-prompt agents, their schemas and routes are style-aware end to end.`*

---

### Phase 5 — Frontend contract, the shared style hook, and the picker

- **Locations:**
  - `web/frontend/lib/api.ts` — `ArtStyleId` (`"painted" | "anime" | "photoreal"`),
    `ArtStyleRead`; `ComfyConfig` gains `artStyle` and `styles`; `artStyle?` added to the
    bodies of `generatePortraitPrompts`, `generateCharacterPortrait`,
    `generateSettingSceneArtPrompts`, `generateSettingSceneArt`,
    `generateScenarioSceneArtPrompts`, `generateScenarioSceneArt`, and `streamMoment`; new
    `fetchComfyLoras()`.
  - **New** `web/frontend/hooks/use-art-styles.ts` — fetches the comfy settings once,
    module-level cached (the same shape as `use-model-health`), exposing
    `{ styles, defaultStyle, loading }`. Both the library and the story player read it, so
    the global default pre-selects the picker everywhere without four separate fetches.
  - **New** `web/frontend/components/feature/ArtStylePicker.tsx` + co-located
    `ArtStylePicker.test.tsx` — a `fieldset`/`legend` radio group (roving arrow-key
    navigation comes free with native radios), a `compact` variant for the in-play bar, each
    option labelled and described by its blurb. Visible focus ring and AA contrast from the
    existing tokens; no new tokens.
  - `web/frontend/test/api-mock.ts` — mock the new endpoints and the extended comfy shape.
- **Rationale:** One picker component and one source of the default, built and tested on
  their own, before four call sites start importing them. Building the surfaces first would
  mean four near-identical inline radio groups and four chances to get the focus behaviour
  wrong.
- **Validation & Commit:** *Run `cd web/frontend && npm test -- ArtStylePicker use-art-styles`,
  then `npm run typecheck && npm run lint`. Run the accessibility pass on the picker in
  isolation (keyboard: Tab into the group, arrows between options; visible focus; the
  legend announced as the group name). Once green, commit locally:
  `[Art Style Presets] (5/8) Complete: Added the art-style frontend contract, the shared default hook, and the accessible ArtStylePicker.`*

---

### Phase 6 — Wire the four image surfaces

- **Locations:**
  - `web/frontend/features/library/useLibraryState.ts` — three pieces of style state
    (portrait, setting art, scenario art), each seeded from `use-art-styles`' default and
    passed on both the prompt call and the render call, so the written prompt and the
    render never disagree about the look. Exposed on the hook's return alongside the
    existing generate handlers.
  - `web/frontend/components/feature/PortraitModal.tsx` — an `ArtStylePicker` above the
    prompt fields, with `style` / `onStyleChange` props; **character portraits**.
  - `web/frontend/components/feature/SceneArtModal.tsx` — the same props; this component is
    used by **both** `SettingModal` (setting scene art) and `EntityModal` (scenario
    establishing art), so both surfaces are covered by one change, wired through in
    `SettingModal.tsx` and `EntityModal.tsx`.
  - `web/frontend/features/story-player/useScenePlay.ts` — `createImage(style)` threads the
    style into `streamMoment`; the repaint path from `SceneImageModal` carries it too.
  - `web/frontend/components/feature/CreateImageBar.tsx` — a `compact` `ArtStylePicker` in
    the idle row beside **Go**, so the player picks the look before painting; hidden while
    running.
  - `web/frontend/components/feature/SceneImageModal.tsx` — a picker beside the repaint
    action, seeded from the beat's recorded `style`.
  - Co-located tests updated/added: `PortraitModal.test.tsx`, `SceneArtModal.test.tsx`,
    `CreateImageBar.test.tsx`, `SceneImageModal.test.tsx`,
    `useLibraryState.character.test.ts`, `useLibraryState.setting.test.ts`,
    `useScenePlay.test.ts` — each asserting the chosen style reaches the API call.
  - `docs/component-map.md` — the new component and the changed props.
- **Rationale:** This is the phase that delivers the user's actual ask — the choice being
  available *throughout the site*, on settings and scene images as much as on characters.
  Landing all four together (rather than one per phase) keeps the product from shipping in
  a state where the control exists for characters and mysteriously does not for places.
- **Validation & Commit:** *Run `cd web/frontend && npm test`, `npm run typecheck`, `npm run lint`.
  Full accessibility + responsive pass per `accessibility-mobile` and `ada-compliance`:
  keyboard operability of every picker, visible focus, AA contrast, and layout at
  320 / 375 / 768 / 1024 px — the in-play picker sharing the `CreateImageBar` row is the
  narrow-viewport risk. Once green, commit locally:
  `[Art Style Presets] (6/8) Complete: Portraits, setting art, scenario art and in-play scene images all offer a per-render style picker.`*

---

### Phase 7 — Options → Image generation

- **Locations:**
  - `web/frontend/features/options/tabs/ImageModelsTab.tsx` — two additions inside the
    existing form: a **Default art style** `ArtStylePicker`, and a **Style LoRAs** fieldset
    with one row per style (an `Enabled` checkbox, a LoRA select populated by
    `fetchComfyLoras()` with a free-text fallback when Comfy is unreachable, and a strength
    number input bounded 0–2). Both fold into the existing `save()` → `opts.saveComfy` call.
  - `web/frontend/features/options/useOptionsSettings.ts` — `saveComfy` carries `artStyle`
    and `styles`.
  - `web/frontend/features/options/tabs/ImageModelsTab.test.tsx` — the default-style radio
    saves; toggling a style's LoRA off and saving sends `loraEnabled: false`; an unreachable
    Comfy leaves the LoRA field usable as text.
  - `docs/design-system.md` — the picker's visual treatment if it introduces a pattern worth
    recording; otherwise no change.
- **Rationale:** The per-style LoRA control is what makes the user's "adjusted, disabled, or
  whatever accordingly" true without a code change — and it is the one place where the
  answer to "why does anime look wrong?" is fixable by the operator. It comes after the
  surfaces so the global default it sets already has consumers.
- **Validation & Commit:** *Run `cd web/frontend && npm test -- ImageModelsTab useOptionsSettings`,
  then `npm run typecheck && npm run lint`, plus an accessibility + responsive pass on the tab
  (the per-style LoRA rows must reflow, not overflow, at 320 px). Once green, commit locally:
  `[Art Style Presets] (7/8) Complete: Options exposes the default art style and each style's LoRA file, strength and on/off.`*

---

### Phase 8 — Documentation, full gate, and merge

- **Locations:**
  - `docs/comfyui-image-generation.md` — the styles, the node-`72` patch/bypass rule, the
    per-style LoRA settings, and the updated node map.
  - `docs/api-contract.md` — `artStyle` on the six authoring bodies and the moment stream
    body; `style` on the `scene_image` payload; `GET /options/comfy/loras`; the extended
    comfy settings shape.
  - `docs/data-flow.md` — where the style is resolved on the render path.
  - `docs/component-map.md`, `docs/routes.md` (if the Options tab's described contents
    change), `docs/architecture.md` (the catalog's home under `content/`).
  - `CLAUDE.md` — the `content/` row gains `art_styles.py`; the feature-module and
    domain-UI counts updated; a "facts that override stale assumptions" line noting that
    image generation is no longer watercolor-only.
  - `docs/checklist.md` — close the item and record anything deliberately deferred (e.g. no
    anime LoRA is installed, so `anime` is prompt-only until one is dropped in).
  - `docs/plans/art-style-presets.md` — this file, marked complete.
- **Rationale:** The docs rule is same-change, and four of the phases above each touch a doc
  in their own commit; this phase reconciles the whole picture and catches the cross-cutting
  files (`CLAUDE.md`, `architecture.md`) that no single phase owns.
- **Validation & Commit:** *Run the complete gate: `uv run pytest`; `cd web/frontend && npm test &&
  npm run typecheck && npm run lint`; `node utils/scripts/check_frontend_css.mjs`. No theme tokens
  change, so `check_contrast.py` is not required — say so explicitly if that turns out false.
  Commit locally: `[Art Style Presets] (8/8) Complete: Reconciled the docs and the checklist against the
  three-style image pipeline.` Then merge `art-style-presets` into `main`, resolve any conflicts, and
  re-run the gate on `main` before the merge commit is final. No worktree was created, so there is
  nothing to clean up. Do not push.*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Art-style catalog | Three styles: hint, tags per surface, negatives, default LoRA; plus `apply_style()` | `web/backend/app/content/art_styles.py` |
| Settings contract | `artStyle` + per-style LoRA on the comfy config | `web/backend/app/schemas/settings.py` |
| Style resolver | `resolve_art_style()` — catalog ∪ stored overrides | `web/backend/app/services/settings_store.py` |
| LoRA patch/bypass | `build_prompt(lora_name, lora_strength, lora_enabled)` + `_bypass_node`; `list_loras` | `web/backend/app/services/comfyui.py` |
| LoRA listing route | `GET /options/comfy/loras` | `web/backend/app/routes/options.py` |
| Styled renders | Style resolved and applied on all three render paths | `web/backend/app/services/{portraits,scene_art,scene_moment}.py` |
| Styled prompts | Four style-aware system prompts | `web/backend/app/agents/{character,setting,scenario,moment}_agent.py` |
| Request contract | `artStyle` on six authoring bodies + the moment body | `web/backend/app/schemas/{character,setting,scenario,play}.py` |
| Event payload | `scene_image.style`, and its hand-kept TS mirror | `web/backend/app/events/envelope.py` · `web/frontend/lib/events.ts` |
| FE contract | Types + the extended call bodies + `fetchComfyLoras` | `web/frontend/lib/api.ts` |
| Default hook | Cached global-default fetch | `web/frontend/hooks/use-art-styles.ts` |
| Picker | Accessible radio-group style picker (+ compact variant) | `web/frontend/components/feature/ArtStylePicker.tsx` |
| Surface wiring | Portraits · setting art · scenario art · in-play images | `PortraitModal.tsx` · `SceneArtModal.tsx` (via `SettingModal`/`EntityModal`) · `CreateImageBar.tsx` · `SceneImageModal.tsx` · `useLibraryState.ts` · `useScenePlay.ts` |
| Options UI | Default style + per-style LoRA file/strength/enabled | `web/frontend/features/options/tabs/ImageModelsTab.tsx` |
| Backend tests | Catalog, LoRA patch/bypass, styled renders, styled prompts, route passthrough | `utils/tests/backend/services/test_art_styles.py` · `test_comfyui_lora.py` · `test_portraits.py` · `test_scene_art.py` · `test_scene_moment.py` · `utils/tests/backend/agents/test_image_prompt_styles.py` · `utils/tests/backend/api/` |
| Frontend tests | Picker, hook, four surfaces, Options tab — all co-located | `ArtStylePicker.test.tsx` · `use-art-styles.test.ts` · `PortraitModal.test.tsx` · `SceneArtModal.test.tsx` · `CreateImageBar.test.tsx` · `SceneImageModal.test.tsx` · `ImageModelsTab.test.tsx` · `useLibraryState.*.test.ts` · `useScenePlay.test.ts` |
| Docs | ComfyUI guide, API contract, data flow, component map, architecture, CLAUDE.md, checklist | `docs/` · `CLAUDE.md` |
