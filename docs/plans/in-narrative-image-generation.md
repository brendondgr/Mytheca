# In-Narrative Image Generation

## 1. Introduction

Mytheca can already render two kinds of authored art through ComfyUI — character
portraits (`services/portraits.py`, 832×1216) and setting/scenario establishing
shots (`services/scene_art.py`, 1024×576). Both are **authoring-time** actions
taken in the Library. Nothing lets a *player* capture the moment they are living
through: the story player has no image affordance at all.

This plan adds a **Create image** control at the foot of the live transcript. It
is a two-stage action: a new `moment_agent` reads the scene's recent beats, the
present cast, and the setting, and writes a ComfyUI prompt that *describes what is
happening* — appearance-first, never by character name — then that prompt is
rendered at a **landscape** frame, converted to WebP, persisted, and emitted as a
new **`scene_image` story event** so it takes its place in the transcript, in the
session record, in the export, and on reload. Rendering streams as NDJSON
(prompt → render → the event) so the UI can show honest staged progress across a
render that takes tens of seconds, reusing the same `with_keepalive` protection
the world build already relies on.

In the transcript the image renders **centered**, in a landscape frame styled like
the existing scene-art preview, and is **clickable** — opening an enlarged
lightbox built on the shared `Modal` primitive, matching the visual language of
`PortraitModal` / `SceneArtModal`. The style is deliberately open-ended: the
prompt writer inherits the world's own look rather than forcing a fixed genre, and
only the *composition* (landscape, in-frame subjects) is fixed.

## 2. Gaps & Unanswered Questions

Resolved by assumption (each is stated, not silently chosen):

1. **Persistence shape.** The image becomes an 8th story event, `scene_image`,
   rather than a column on a table. It is a narrative beat with a position in the
   transcript; the events table already gives it ordering, session scoping,
   rehydration, and export for free.
2. **Aspect ratio.** The request asks for wider-than-tall. The Options default
   (`ComfyParams`, 1024×1024, and whatever the author has set — 9:16 today) is
   *not* used for moments: `scene_moment.py` pins its own landscape frame,
   **1216×832** (≈3:2, both divisible by 64, ~1 MP for Z-Image-Turbo), exactly as
   `scene_art.py` pins 1024×576. Callers may override.
3. **Storage location.** A third media subdirectory, `media/moments/`, served at
   `/media/moments/<uuid>.webp`. Reusing `scenes/` would blur the cleanup
   bookkeeping between authored scene art and in-play captures.
4. **Cleanup safety.** `media_cleanup` currently derives "referenced" from
   `Character.portrait` / `Setting.image` / `Scenario.image` only. Moments are
   referenced by *event rows*, so without a change the 24-hour sweep would delete
   every generated moment. `_referenced_basenames` must also read `scene_image`
   event payloads, and the scan must cover the new directory.
5. **Name suppression.** LLMs leak proper nouns no matter how the system prompt is
   worded. The agent instruction forbids names, **and** a deterministic
   post-processing guard replaces any cast name still present with that
   character's own visual tag (derived from `portrait_positive`/appearance). The
   guard is what makes the requirement testable.
6. **Who is in frame.** Characters who are `present` **and** appear in the recent
   beat window (spoke, acted, or were acted upon by name). A cast member who is in
   the scenario but silent for the last dozen beats is not painted into the shot.
   The player's own POV character counts as present when POV is active.
7. **Trigger position.** The control lives below the transcript's last beat, above
   the composer, inside the scrolling column — so it is literally "at the very
   bottom of the chat", and scrolls with it.

No question here needs human intervention.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The `scene_image` contract

- **Locations:** `web/backend/app/schemas/base.py` (`EventType`),
  `web/backend/app/events/envelope.py` (`SceneImageData`, `SceneImageEvent`, union
  + `__all__`), `web/frontend/lib/events.ts` (the hand-mirrored contract),
  `docs/api-contract.md`.
- **Payload:** `url` (relative `/media/moments/…`), `prompt`, `negative`,
  `caption` (short alt text — accessibility, and the enlarged view's label),
  `characterIds` (who is depicted).
- **Rationale:** Backend and frontend must agree on the wire shape before either
  can emit or render it. The union is validated by construction in `build_event`,
  so this step is what makes every later emission type-safe. `docs/api-contract.md`
  changes in the same step per the docs rule.
- **Tests:** `utils/tests/backend/services/test_scene_image_event.py` — building
  the event through `build_event` validates, round-trips camelCase, and defaults
  `visibility` to `public`.
- *Action: Run `uv run pytest utils/tests/backend` and `npm run typecheck`. Once
  green, commit: `[In-Narrative Images] (1/6) Complete: Added the scene_image story
  event to the envelope and its frontend mirror.`*

### Phase 2 — The moment-prompt agent

- **Locations:** new `web/backend/app/agents/moment_agent.py`; response schema in
  `web/backend/app/schemas/play.py` (`MomentPromptResponse`).
- **Inputs:** world genre/tone, setting name + atmosphere + current state, the last
  N transcript beats rendered as plain lines, and a **cast block** — for each
  character in frame: role, species/appearance prose, and their locked
  `portrait_positive` phrases (their established visual identity, already in
  ComfyUI phrase form).
- **System prompt requirements (the hard part):** short comma-separated phrases;
  lead with the composition and the moment's action; describe every figure by
  appearance (age, build, hair, distinguishing marks, attire, expression) and by
  **what they are doing right now**; never emit a proper name; include the setting
  and its light/weather/mood; end with style tags that follow the world's own look
  and an explicit `wide landscape composition`. Returns
  `{"positive","negative","caption"}`.
- **Guard:** `strip_names(text, replacements)` — word-boundary, case-insensitive
  replacement of each cast name (full name and each name token ≥3 chars) with that
  character's visual tag; applied to `positive` only — the `caption` is alt text
  read by a person, never sent to the image model, so names *help* there. Exported
  and independently unit-tested.
- **Rationale:** The prompt is the feature's substance; isolating it (and its
  guard) in an agent module keeps it testable offline and re-tunable without
  touching the render path or the route.
- **Tests:** `utils/tests/backend/agents/test_moment_agent.py` — a stubbed LLM
  returning a name-laden prompt is scrubbed; appearance phrases survive; missing
  context raises a 400; the cast block includes only in-frame characters.
- *Action: Run `uv run pytest utils/tests/backend/agents`. Once green, commit:
  `[In-Narrative Images] (2/6) Complete: Added the moment-prompt agent and its
  name-suppression guard.`*

### Phase 3 — Render service, route, cleanup, export

- **Locations:** new `web/backend/app/services/scene_moment.py`;
  `web/backend/app/core/config.py` (`moments_dir`);
  `web/backend/app/routes/play.py` (`POST /play/{scenarioId}/moment/stream`);
  `web/backend/app/schemas/play.py` (`MomentRequest`, `MomentStageFrame`);
  `web/backend/app/services/media_cleanup.py`;
  `web/backend/app/services/session_export.py`; `web/backend/app/main.py` only if
  the `/media` mount needs the new subdirectory (it is a whole-tree mount, so it
  should not).
- **Service:** gather scenario + session + recent events + presence + cast → call
  `moment_agent` → `comfyui.generate(...)` at 1216×832 with a fresh random seed →
  `save_webp(moments_dir, …)` → `build_event("scene_image", …)` at the session's
  next seq → `persist_story_event` + `touch_session`. Yields staged progress so the
  route can stream it.
- **Route:** pre-stream validation (unknown scenario → 404, unknown/missing session
  → 404/400, unconfigured ComfyUI → 400) then NDJSON: `moment_stage` frames
  (`prompt` → `render`), the terminal `scene_image` event, `error` on failure, all
  wrapped in `with_keepalive` emitting a `render` heartbeat.
- **Cleanup:** `_referenced_basenames` also collects `Event.data["url"]` for
  `type == "scene_image"`; `scan_orphans`/`delete_orphans` cover `moments_dir`; the
  report and its Options response schema gain a `moments` block.
- **Export:** `session_export` renders the image as a Markdown image line with its
  caption, and includes it in the JSON record.
- **Rationale:** This is the whole server-side path; doing cleanup in the same
  phase is not optional — shipping the writer without teaching the sweeper about it
  would silently delete players' images a day later.
- **Tests:** `utils/tests/backend/services/test_scene_moment.py` (offline: stubbed
  agent + stubbed `comfyui.generate`, asserts landscape dimensions, WebP written,
  event persisted with the right seq/session),
  `utils/tests/backend/api/test_play_moment_route.py` (frame order, pre-stream
  errors, mid-stream error frame), and additions to the existing media-cleanup
  tests proving a `scene_image`-referenced file is never an orphan.
- *Action: Run `uv run pytest utils/tests/backend`. Once green, commit:
  `[In-Narrative Images] (3/6) Complete: Rendered, persisted, and swept moments
  behind a streaming play route.`*

### Phase 4 — Frontend contract + scene state

- **Locations:** `web/frontend/lib/api.ts` (`postSceneMoment`),
  `web/frontend/features/story-player/scene-data.ts` (`SceneMessage` gains an
  `image` kind + payload), `web/frontend/features/story-player/turn-stream.ts`
  (`mergeFrame` appends the image beat; `rehydrateFromHistory` folds it on reload),
  `web/frontend/features/story-player/useScenePlay.ts` (a second `useEventStream`
  for the moment stream + `imageStage`/`imageError`/`createImage`).
- **Rationale:** Making the reducer own the beat means the live stream and reload
  path produce identical transcripts — the same invariant the rest of the player
  relies on — before any pixel is styled.
- **Tests:** additions to `turn-stream.test.ts` (fold live + rehydrate) and
  `useScenePlay.test.ts` (stage transitions, error surfacing, in-flight guard).
- *Action: Run `npm test` (story-player) + `npm run typecheck`. Once green, commit:
  `[In-Narrative Images] (4/6) Complete: The story player folds scene images live
  and on reload.`*

### Phase 5 — The UI: control, beat, lightbox

- **Locations:** new `web/frontend/components/feature/CreateImageBar.tsx` (the
  bottom-of-chat control: label, **Go**, staged progress animation), new
  `web/frontend/components/feature/SceneImageBeat.tsx` (centered landscape frame,
  clickable) and `web/frontend/components/feature/SceneImageModal.tsx` (the
  enlarged view, built on `components/ui/Modal`, showing the image, its caption,
  and the prompt behind a disclosure),
  `web/frontend/components/feature/TranscriptBeat.tsx` (route `kind: "image"`),
  `web/frontend/features/story-player/StoryPlayerView.tsx` (render the bar below
  the last beat, own the lightbox state).
- **Design:** reuse the scene-art visual language — `rounded-[6px]`,
  `border-cardbd`, `bg-field`, landscape aspect, `Eyebrow` caption — so a moment
  reads as the same family of object as a setting's establishing shot. Motion via
  Framer Motion only; the progress animation is a base style plus keyframes, which
  the global `.velora-themed *` reduced-motion rule already disables.
- **Accessibility:** the beat is a real `<button>` with an accessible name from the
  caption; the image carries the caption as `alt`; the progress region is
  `aria-live="polite"` and the control is `aria-busy` while running; the lightbox
  inherits `Modal`'s focus trap and Escape handling; layout verified at
  320/375/768/1024.
- **Tests:** co-located `CreateImageBar.test.tsx`, `SceneImageBeat.test.tsx`,
  `SceneImageModal.test.tsx`, plus a `StoryPlayerView.test.tsx` case that the bar
  renders after the last beat.
- *Action: Run `npm test` + `npm run typecheck` + `npm run lint`, and an
  accessibility + responsive pass. Once green, commit: `[In-Narrative Images] (5/6)
  Complete: Added the Create image control, the centered clickable beat, and its
  enlarged view.`*

### Phase 6 — Live end-to-end verification + docs

- **Locations:** `docs/research/experiments/EXP-2026-08-002-moment-prompt-style/`
  (the prompt-shaping run, per `docs/research/AGENT_INSTRUCTIONS.md`),
  `docs/comfyui-image-generation.md`, `docs/api-contract.md`, `docs/data-flow.md`,
  `docs/component-map.md`, `docs/structure.md`, `docs/routes.md` (no new route, but
  the player's affordances change), `docs/checklist.md`, `CLAUDE.md` (file map).
- **Rationale:** The request is explicit that the prompt "will take a lot of
  experimentation", and the repository's research contract says any comparison of
  variants is recorded, not narrated in chat. The live run drives the real ComfyUI
  server (up at `:8199`) and the real LLM relay (`:4000`) through the actual
  service, records the prompts and the rendered dimensions, and keeps the images as
  artifacts.
- **Verification:** at least one real end-to-end call producing a landscape WebP
  under `media/moments/`, from a real (or seeded) session; confirm the prompt
  carries no cast names and does carry appearance + action phrases.
- *Action: Run `uv run pytest`, `npm test`, and `make validate-research`. Once
  green, commit: `[In-Narrative Images] (6/6) Complete: Verified moment generation
  against the live ComfyUI server and documented it.`*

## 4. Outcome (all six phases shipped, 2026-08-11)

Built as planned, with three things worth recording because they differ from the plan:

1. **The keep-alive heartbeat had to become stage-aware.** The first live run showed
   `stage: "render"` ticks arriving while the prompt was still being written — the route
   now mirrors the stage actually running (`routes/play.py`), covered by a test.
2. **The name guard is applied to the positive prompt only**, not the caption: the caption
   is read by a person and never sent to the image model, so names help there.
3. **The live verification is recorded as `EXP-2026-08-002`** (3 runs against the real LLM
   relay and the real ComfyUI: `name_leak` 0.0, `appearance_coverage` 1.0, `landscape` 1.0,
   1216×832, ~38 s/image). It is a single-arm *functional* verification — no baseline, one
   scene — and `RESULTS.md` §5 says so; no claim in `CLAIMS.md` moved.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Event variant | `scene_image` on the story-event union | `web/backend/app/events/envelope.py`, `web/backend/app/schemas/base.py` |
| TS mirror | Hand-maintained frontend contract | `web/frontend/lib/events.ts` |
| Prompt agent | Scene → appearance-first ComfyUI prompt + name guard | `web/backend/app/agents/moment_agent.py` |
| Render service | Landscape ComfyUI render → WebP → persisted event | `web/backend/app/services/scene_moment.py` |
| Route | `POST /play/{scenarioId}/moment/stream` (NDJSON) | `web/backend/app/routes/play.py` |
| Media dir | `media/moments/`, served at `/media/moments/…` | `web/backend/app/core/config.py` |
| Cleanup | Moments counted as referenced + swept | `web/backend/app/services/media_cleanup.py` |
| Export | Images in the JSON/Markdown session record | `web/backend/app/services/session_export.py` |
| Client API | `postSceneMoment` NDJSON helper | `web/frontend/lib/api.ts` |
| Scene state | Image beat folded live + on reload | `web/frontend/features/story-player/{scene-data,turn-stream,useScenePlay}.ts` |
| Control | Bottom-of-chat **Create image** + **Go** + progress | `web/frontend/components/feature/CreateImageBar.tsx` |
| Beat | Centered, clickable landscape image beat | `web/frontend/components/feature/SceneImageBeat.tsx` |
| Enlarged view | Lightbox on the shared `Modal` primitive | `web/frontend/components/feature/SceneImageModal.tsx` |
| Backend tests | Envelope, agent, service, route, cleanup | `utils/tests/backend/{services,agents,api}/` |
| Frontend tests | Reducers, hook, three components, view | co-located `*.test.tsx` / `*.test.ts` |
| Research record | Live prompt-shaping run | `docs/research/experiments/EXP-2026-08-002-moment-prompt-style/` |
| Docs | Pipeline, contract, data flow, components, structure | `docs/comfyui-image-generation.md` + the files listed in Phase 6 |
