# Storyline UI Tweaks + Draft-502 Fix

## 1. Introduction

Three targeted changes to the storyline Library surface and the storyline authoring agent:

1. **Smooth scroll to the active setting.** When a scenario is selected the Settings column already brings the active setting into view, but it *jumps* (`scrollIntoView({ block: "nearest" })`). Make it animate smoothly, while honoring `prefers-reduced-motion`.
2. **Wider scenario "scene art".** The recent-scenario hero carousel reserves a fixed `200px`, full-height art panel on the right (portrait). Reframe it to a **16:9** region so future generated scene art shows wide and uncropped.
3. **Fix the `502 Bad Gateway` on `POST /api/storylines/draft`.** Reproduced live: the configured model (`gemma-4-26B-it-q4km`) is a **reasoning model** that emits `reasoning_content` and consumes the entire `max_tokens=512` budget thinking, returning empty `content` with `finish_reason: "length"` → `chat_complete` raises `502 upstream_error "empty response"`. The authoring agent (multi-paragraph output) needs far more token headroom; the proxy should also report a token-limit truncation actionably.

Areas touched: `web/frontend/components/feature/SettingColumn.tsx`, `web/frontend/components/feature/ScenarioCarousel.tsx`, `web/backend/app/agents/storyline_agent.py`, `web/backend/app/services/llm.py`, plus tests under `utils/tests/`.

## 2. Gaps & Unanswered Questions

- **"Seed art" naming.** The user said "seed art"; the only scenario art region in the codebase is the carousel's `scene art` placeholder. *Assumption:* that is the target.
- **16:9 sizing vs. small breakpoints.** A full-height (246px) 16:9 panel is ~437px wide — too wide to coexist with the hero text at the `sm` (640px) breakpoint where the panel currently appears. *Assumption:* show the wide 16:9 panel from `lg` (≥1024px) and let the text take the full width below that (the panel is a placeholder today).
- **Token floor value.** *Assumption:* floor authoring generations at `2048` `max_tokens` (verify empirically against the live reasoning model; raise if it still truncates). User config (512) is left untouched; the floor is applied per authoring call.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Fix the draft 502 (backend)
- **Locations:** `web/backend/app/agents/storyline_agent.py` (add a `_gen_params` token-floor helper; apply it in `draft_storyline` + `generate_world_primer`), `web/backend/app/services/llm.py` (`chat_complete`: read `finish_reason`; when `content` is empty and the reason is `"length"`, raise an actionable `upstream_error` pointing at Max tokens / reasoning headroom), tests in `utils/tests/backend/agents/test_storyline_agent.py`.
- **Rationale:** Floors the budget so the reasoning model reaches its visible reply (the actual fix); the proxy change turns the remaining truncation case into a clear, actionable error instead of a bare "empty response".
- **Action:** Run `uv run pytest utils/tests/backend/agents utils/tests/backend/api/test_llm.py`. Validate live against the running backend/LLM (restart backend, POST a real draft). Once green, commit: `[Storyline UI Tweaks + Draft Fix] (1/3) Complete: floor authoring max_tokens + actionable token-limit error so reasoning models draft.`

### Phase 2 — Smooth scroll to active setting (frontend)
- **Locations:** `web/frontend/components/feature/SettingColumn.tsx` (the `useEffect` scroll); update the explanatory comment.
- **Rationale:** Replaces the instant jump with `behavior: "smooth"`, gated by a `prefers-reduced-motion` check to stay ADA-compliant.
- **Action:** Run `npm test` (Vitest), `npm run typecheck`, `npm run lint`. Live a11y/responsive check via preview (keyboard-select scenarios; confirm reduced-motion falls back to instant). Once green, commit: `[Storyline UI Tweaks + Draft Fix] (2/3) Complete: smooth (motion-safe) scroll to the active setting.`

### Phase 3 — Widen scenario scene art to 16:9 (frontend)
- **Locations:** `web/frontend/components/feature/ScenarioCarousel.tsx` (the art panel `div`: `w-[200px] … sm:flex` → `aspect-[16/9] h-full … lg:flex`; update the overlay/dots right-offsets that hard-code `sm:right-[212px]` to match the new width at `lg`).
- **Rationale:** Gives a true 16:9 frame for wide generated art while keeping the hero text readable at smaller widths.
- **Action:** Run `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`. Live responsive pass via preview at 320/375/768/1024/1280 (no overflow; 16:9 frame at ≥1024; overlays clear the panel). Once green, commit: `[Storyline UI Tweaks + Draft Fix] (3/3) Complete: 16:9 scenario scene-art frame in the hero carousel.`

### Phase 4 — Docs + merge
- **Locations:** `docs/checklist.md` (record the work + any deferred item), `docs/design-system.md` if the art ratio is worth noting; merge the feature branch into `main` (`--no-ff`), resolving any conflicts. **No push.**
- **Action:** Final `uv run pytest` + frontend `npm test`/typecheck/lint/build green on the merged tree. Commit doc updates with the merge.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Token-floor + actionable error | Authoring floors `max_tokens`; proxy reports `finish_reason: length` clearly | `web/backend/app/agents/storyline_agent.py`, `web/backend/app/services/llm.py` |
| Backend tests | Token floor reaches the upstream body; `length`-truncation → actionable 502 | `utils/tests/backend/agents/test_storyline_agent.py` |
| Smooth setting scroll | Motion-safe `behavior: "smooth"` scroll to the active setting | `web/frontend/components/feature/SettingColumn.tsx` |
| 16:9 scene art | Wide 16:9 art frame in the hero carousel + overlay offsets | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Docs | Checklist entry + any design-system note | `docs/checklist.md`, `docs/design-system.md` |
