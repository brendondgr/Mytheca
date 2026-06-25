# Plan — ComfyUI Image Generation

## 1. Introduction

This plan adds an image-generation system to Velora that drives a local **ComfyUI** server (OpenAI-style, but Comfy's own HTTP + WebSocket protocol). The goal is a server-side ComfyUI client that loads a saved workflow (`utils/workflows/ZiT-Workflow.json`), patches the prompt/params, queues the job, waits for completion over the Comfy WebSocket, and downloads the rendered image — plus an **Options menu** surface to configure the endpoint/workflow/params and run a connection (status) check.

The approach mirrors the existing **Options / Language Models** slice end-to-end: a backend service (`services/comfyui.py`, the analogue of `services/llm.py`) with an injectable HTTP/WS client for offline tests; settings persisted through `settings_store` into the `app_settings` row; routes under the `/options` prefix; and a new **Image Generation** tab in `features/options/` that parallels `LanguageModelsTab`. The full generate pipeline is implemented and validated end-to-end against the live ComfyUI; per the product decision the Options tab's *test* button is a **status check only** (no GPU spend in the UI), while the generate capability lives in the service for the story engine and is proven during validation.

## 2. Gaps & Unanswered Questions

- **UI placement (resolved):** a **new dedicated "Image Generation" tab** beside Language Models.
- **UI test behavior (resolved):** **status check only** (`/system_stats`); full generation is implemented in the service and exercised in validation, not wired to a UI button.
- **HTTP/WS libraries (assumption):** reuse **`httpx`** for all HTTP (consistent with `llm.py`, mockable via `MockTransport`) and add **`websocket-client`** for the synchronous WebSocket wait (httpx has no sync WS). The guide's `requests` is intentionally *not* added — `httpx` already covers HTTP, and "no speculative dependencies" applies.
- **ComfyUI base URL (assumption):** default `http://localhost:8199` (the running instance), overridable via `COMFYUI_BASE_URL` env and the Options config row.
- **Workflows directory (assumption):** `utils/workflows/` resolved relative to repo root; `ZiT-Workflow.json` is the default workflow. Only `*.json` files are listed.
- **No auth / per-owner scoping:** config is global, matching the existing `app_settings` model (consistent with the LLM config).

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — ComfyUI client service + dependency

- **Locations:** `pyproject.toml` (+`uv add websocket-client`), `web/backend/app/core/config.py`, `.env.example`, `docs/deployment.md`, `web/backend/app/services/comfyui.py`, `utils/tests/backend/api/test_comfyui.py`.
- **Work:**
  - Add `websocket-client` dependency.
  - `config.py`: add `comfyui_base_url` (default `http://localhost:8199`) and a `comfyui_workflows_dir` resolver (repo-root `utils/workflows`). Document `COMFYUI_BASE_URL` in `.env.example` + `docs/deployment.md`.
  - `services/comfyui.py` implementing the 7-step pipeline, errors mapped to the contract `APIError` envelope, with **injectable** `get_http_client()` and `open_ws()` factories (patched in tests, mirroring `llm.get_http_client`):
    - `check_connection(base_url)` → `GET /system_stats` (raises a readable `502`/`400` on failure).
    - `list_workflows()` / `load_workflow(name)` → enumerate / read `utils/workflows/*.json`.
    - `build_prompt(workflow, *, positive, negative, seed, steps, cfg, width, height, batch_size)` → `deepcopy` + surgical node patch (nodes `67` positive, `71` negative, `70` KSampler, `68` latent size; documented node map in the docstring).
    - `queue_prompt(base_url, workflow, client_id)` → `POST /prompt`; treats a JSON `error` body on HTTP 200 as a failure.
    - `wait_for_completion(base_url, prompt_id, client_id)` → WS at `/ws?clientId=…`, blocks until `executing` with `node: null`; skips binary preview frames.
    - `get_output_info(base_url, prompt_id)` → `GET /history/{id}`, pulls `filename/subfolder/type` from the `SaveImage` node (`77`); surfaces a real error on failed status.
    - `download_image(base_url, filename, subfolder, type)` → `GET /view…` returns `bytes`.
    - `generate(...)` orchestrator → returns image `bytes` + output info (used by the route + validation).
  - Tests (offline): `build_prompt` patch correctness; `queue_prompt` error-body handling; `check_connection` success + transport-error → envelope; `get_output_info` parsing; using `MockTransport` + a fake WS.
- **Rationale:** the service is the foundation everything else (routes, UI, story engine) builds on; it must be testable without a live server.
- **Action:** Run `uv run pytest utils/tests/backend` (+ `ruff`/`mypy`). Once green, commit: `ComfyUI Image Generation (1/4) Complete: server-side ComfyUI client (7-step pipeline) + config + offline tests.`

### Phase 2 — Options backend surface

- **Locations:** `web/backend/app/schemas/settings.py`, `web/backend/app/services/settings_store.py`, `web/backend/app/routes/options.py`, `docs/api-contract.md`, `docs/data-flow.md`, `utils/tests/backend/api/test_options.py` + `test_comfyui.py`.
- **Work:**
  - Schemas: `ComfyParams` (steps, cfg, width, height, batchSize, negativePrompt), `ComfyConfigRead`/`ComfyConfigUpdate` (baseUrl, workflow, params), extend `SettingsRead` with `comfy`; add `ComfyStatusResponse`, `ComfyWorkflowsResponse`.
  - `settings_store.py`: `COMFY_KEY`, `_comfy_defaults` (seeded from `Settings.comfyui_base_url` + `ZiT-Workflow.json`), `get_comfy`, `update_comfy`, `resolve_comfy_base_url`.
  - `routes/options.py`: `GET /options` now includes `comfy`; `PATCH /options/comfy`; `POST /options/comfy/status` (system_stats); `GET /options/comfy/workflows` (file list).
  - Docs: `api-contract.md` (Options group gains Comfy shapes + endpoints); `data-flow.md` settings flow note.
  - Tests: status (mock upstream) success + error-envelope; workflows listing; config get/patch roundtrip.
- **Rationale:** persist config and expose the status/discovery surface the UI consumes.
- **Action:** Run `uv run pytest utils/tests/backend` (+ `ruff`/`mypy`). Once green, commit: `ComfyUI Image Generation (2/4) Complete: Options backend — comfy config, status check, workflow listing + tests.`

### Phase 3 — Frontend Image Generation tab

- **Locations:** `web/frontend/lib/api.ts`, `web/frontend/features/options/useOptionsSettings.ts`, `web/frontend/features/options/tabs/ImageModelsTab.tsx` (+ `.test.tsx`), `web/frontend/features/options/OptionsView.tsx` (+ `OptionsView.test.tsx`), `web/frontend/test/api-mock.ts`, `docs/component-map.md`.
- **Work:**
  - `api.ts`: `ComfyParams`, `ComfyConfig`, `ComfyConfigUpdate`, `AppSettings.comfy`; `updateComfyConfig`, `checkComfyStatus`, `fetchComfyWorkflows`.
  - `useOptionsSettings.ts`: `saveComfy` (await-then-apply into `settings.comfy`).
  - `ImageModelsTab.tsx`: base URL, workflow `<select>` (fetched + on-blur of base URL), generation params (steps/cfg/width/height/negative prompt), **Check status** button rendering the Comfy version/device, Save. Lazy-init from loaded config, keyed-remount like `LanguageModelsTab`.
  - `OptionsView.tsx`: add the `images` tab (label "Image Generation", sub "ComfyUI") to `TABS` + render `ImageModelsTab`.
  - `api-mock.ts`: comfy block in `getSettings`, `updateComfyConfig`, `checkComfyStatus`, `fetchComfyWorkflows`.
  - Docs: `component-map.md` new tab.
  - Tests: `ImageModelsTab.test.tsx` (hydrate, fetch workflows → select, status check shows result, save); keep `OptionsView.test.tsx` green.
- **Rationale:** the configuration UI the user asked for in the Options menu.
- **Action:** Run `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` in `web/frontend`; a11y/responsive note (native focusable controls + existing tokens; in-browser pass per the standing constraint). Once green, commit: `ComfyUI Image Generation (3/4) Complete: Options Image Generation tab (config + status check) + tests.`

### Phase 4 — Live validation + docs

- **Locations:** runtime (live ComfyUI at `localhost:8199`), `docs/documentation.md`, `docs/checklist.md`, `docs/comfyui-image-generation.md` (usage doc), `README.md` pointer if needed.
- **Work:**
  - End-to-end: drive `services/comfyui.generate(...)` against the running ComfyUI (queue → WS wait → download) and confirm a real PNG comes back; also hit `/options/comfy/status` + `/options/comfy/workflows` through the API.
  - Author the **usage doc** detailing the 7 steps, the node map, config/env, and how the Options tab + service are used.
  - Update `documentation.md` status + `checklist.md` (done entry + any deferred in-browser a11y pass).
- **Rationale:** the user requires proof against the live server and up-to-date docs.
- **Action:** Run the full suite (`uv run pytest`, frontend tests) once more. Once green, commit: `ComfyUI Image Generation (4/4) Complete: live end-to-end validation + usage docs.` Then merge the feature branch into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| ComfyUI client | 7-step pipeline (status, load/build/queue/wait/info/download/generate) | `web/backend/app/services/comfyui.py` |
| Config | `comfyui_base_url` + workflows dir; env var | `web/backend/app/core/config.py`, `.env.example` |
| Comfy schemas | Config + status/workflows shapes | `web/backend/app/schemas/settings.py` |
| Settings store | Persist/resolve comfy config | `web/backend/app/services/settings_store.py` |
| Options routes | `PATCH /options/comfy`, `POST /options/comfy/status`, `GET /options/comfy/workflows` | `web/backend/app/routes/options.py` |
| API client | Comfy types + calls | `web/frontend/lib/api.ts` |
| Image Generation tab | Config + status-check UI | `web/frontend/features/options/tabs/ImageModelsTab.tsx` |
| Options wiring | New tab in the vertical tablist | `web/frontend/features/options/OptionsView.tsx` |
| Backend tests | Service + route tests (offline) | `utils/tests/backend/api/test_comfyui.py`, `test_options.py` |
| Frontend tests | Tab behavior | `web/frontend/features/options/tabs/ImageModelsTab.test.tsx` |
| Usage doc | How to use the ComfyUI system | `docs/comfyui-image-generation.md` |
