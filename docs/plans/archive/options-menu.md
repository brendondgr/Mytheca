# Plan — Options Menu (`/options`) + Language-Model configuration

**Status:** Phase 1 complete (backend) · Phases 2–3 pending · **Owner:** Claude Code · **Created:** 2026-06-22

> **Implementation note:** the backend routes ship under the **`/options`** prefix
> (`web/backend/app/routes/options.py`), *not* `/settings` as drafted below — the
> Setting entity already owns `/settings`. Read the `/settings` references in
> Phase 1 as `/options`. The schema module is still `schemas/settings.py`.

## Goal

Add an **Options** surface, reachable from a new header **dropdown** placed to the
right of **Create**. The dropdown has two items:

1. **Settings Menu** → navigates to a new full-screen route **`/options`**.
2. **Appearance** → an inline theme selector (Parchment / Ember / Slate) that
   persists across sessions (reuses the existing `mytheca-theme` machinery).

`/options` replaces the full screen. It follows the existing manuscript visual
language (tokens, fonts, glow) but a **different structure**: a centered panel at
**66% width**, with a **vertical tab list on the left** and the active tab's
content on the right. Tabs:

| Tab | Purpose |
| --- | --- |
| **Language Models** (priority) | Configure an OpenAI-compatible endpoint: enter a base URL (e.g. `http://localhost:7070/v1`), fetch available models from `/models`, pick the active model, edit generation params, and run a connection/chat **test**. |
| **Appearance** | Theme picker + the persistence story, surfaced as a full panel. |
| **Library defaults** | Non-sensitive UI prefs: default storyline on load, etc. |
| **About / Diagnostics** | Read-only: app version, backend health, provider, API base, active model. No secrets. |

### Design decisions (confirmed with the user)

- **Persistence:** a **backend settings store** (DB table) read/written via new
  `/api/settings` endpoints. This is the only option where the backend "brain"
  can later *use* the configured model, and it dodges browser CORS when talking
  to local model servers. The **API key is stored server-side and never returned
  in clear** — `GET` exposes only `hasApiKey` + a masked hint.
- **Model listing & connection test go through the FastAPI backend** (a thin
  httpx proxy), not the browser — avoids CORS to `localhost:*` and keeps the key
  server-side. `httpx` is already a dependency.
- **Appearance** stays client-side (`localStorage['mytheca-theme']`, already
  persistent); it is surfaced both in the header dropdown and the Appearance tab.

## Gaps / assumptions

- **No auth / no users table yet.** The settings store is therefore a single
  **global** config (one row per namespace). When auth lands, scope by owner.
  *Assumption — acceptable for the current single-user dev posture.*
- **API key at rest is plaintext in the DB** (local single-user app). Documented
  as a known limitation; not returned to the browser. Encryption-at-rest is
  deferred to the auth phase.
- **No new env vars.** All endpoint config lives in the DB store; the existing
  `LLM_PROVIDER` / `OPENAI_API_KEY` / `LOCAL_LLM_BASE_URL` remain as fallback
  seeds for the store's defaults.
- Base URL is used verbatim with a trailing-slash trim: we call `{base}/models`
  and `{base}/chat/completions`. The user supplies the full `…/v1`.

---

## Phase 1 — Backend: settings store + LLM proxy

**Why first:** it is independently testable with `pytest` (in-memory SQLite, no
network), and the frontend builds on its shapes.

### 1.1 Model — `web/backend/app/models/app_setting.py`
A portable key/value row so namespaces stay flexible:
```python
class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)   # "llm" | "library"
    value: Mapped[dict] = mapped_column(JSONColumn, default=dict)
```
Register it in `app/models/__init__.py` (so `Base.metadata` + tests see it).

### 1.2 Schemas — `web/backend/app/schemas/settings.py` (CamelModel)
- `LlmParams` — `temperature`, `maxTokens`, `topP`, `frequencyPenalty`,
  `presencePenalty` (all optional, sensible defaults).
- `LlmConfigRead` — `baseUrl`, `model`, `provider`, `params`, `hasApiKey: bool`,
  `apiKeyHint: str | None` (e.g. `"…AB12"`). **No raw key.**
- `LlmConfigUpdate` — `baseUrl?`, `model?`, `provider?`, `params?`, `apiKey?`
  (omitted = keep; `""` = clear).
- `LibraryDefaultsRead/Update` — `defaultStorylineId?`, `openLastStoryline: bool`.
- `SettingsRead` — `{ llm: LlmConfigRead, library: LibraryDefaultsRead }`.
- `LlmModelsRequest` — `baseUrl?`, `apiKey?` (fall back to stored).
- `LlmModelsResponse` — `models: list[str]`.
- `LlmTestRequest` — `baseUrl?`, `apiKey?`, `model`, `params?`.
- `LlmTestResponse` — `ok`, `model`, `latencyMs`, `sample` (short completion text).

### 1.3 Services
- `web/backend/app/services/settings_store.py` — `get_settings_doc(db)`,
  `get_llm(db)`, `update_llm(db, data)`, `get_library(db)`, `update_library(db,…)`.
  Get-or-create defaults (seed `baseUrl`/`provider` from `Settings`). Masking +
  key-retention logic lives here so routes stay thin.
- `web/backend/app/services/llm.py` — `list_models(base_url, api_key)` →
  `GET {base}/models`; `test_chat(base_url, api_key, model, params)` →
  `POST {base}/chat/completions` with a tiny prompt + small `max_tokens`, timing
  the round-trip. Errors map to `APIError` (`502 upstream_error` for non-2xx,
  `504`/`bad_gateway` for timeout/network). HTTP client built by a
  `get_http_client()` helper so tests can inject an `httpx.MockTransport`.

### 1.4 Routes — `web/backend/app/routes/settings.py`
`APIRouter(prefix="/settings")`: `GET ""`, `PATCH "/llm"`, `PATCH "/library"`,
`POST "/llm/models"`, `POST "/llm/test"`. Register in `app/main.py`.

### 1.5 Tests — `utils/tests/backend/api/`
- `test_settings.py` — GET returns defaults; PATCH `/llm` persists baseUrl/model/
  params; setting `apiKey` → GET shows `hasApiKey=true` + masked hint, **never the
  raw key**; sending `apiKey:""` clears it; PATCH `/library` persists.
- `test_llm.py` — with an `httpx.MockTransport`: `/llm/models` returns the parsed
  id list; `/llm/test` returns `ok` + a sample; an upstream 500 → error envelope
  (`upstream_error`); a transport error → `bad_gateway`.

### Validation + commit (Phase 1)
`uv run pytest` green (new + existing); `uv run ruff check .` + `uv run mypy
web/backend` clean. Update `docs/api-contract.md` (Settings/LLM group),
`docs/structure.md` (new model/route), `docs/data-flow.md` (settings flow).
Commit: `[Options Menu] (1/3) Complete: backend settings store + LLM proxy`.

---

## Phase 2 — Frontend: header Options dropdown + `/options` shell + Appearance / Library / About tabs

### 2.1 API client — extend `web/frontend/lib/api.ts`
Types mirroring the schemas (`LlmConfig`, `LlmParams`, `LibraryDefaults`,
`AppSettings`, `LlmModelsResult`, `LlmTestResult`) + functions: `getSettings`,
`updateLlmConfig`, `updateLibraryDefaults`, `fetchLlmModels`, `testLlmConnection`,
and a `getHealth()` (hits the non-`/api` `/health`). 

### 2.2 Header dropdown — `components/feature/OptionsMenu.tsx`
"Options ▾" button (mirrors `CreateMenu`: outside-click + Esc, `aria-haspopup`/
`expanded`/`controls`). Popover: a **Settings Menu** row (`next/link` → `/options`)
and an **Appearance** group rendering the three theme swatches (reuse `THEMES` +
`useTheme`/`setTheme`). Add an `optionsSlot` to `AppHeader` rendered **after**
`createSlot`; wire from `LibraryView`. Remove the now-redundant standalone
`ThemeSwitcher` from `AppHeader` (kept elsewhere, e.g. `SceneHeader`); update the
affected Library tests.

### 2.3 Route + shell — `app/options/page.tsx` → `features/options/OptionsView.tsx`
- `page.tsx`: `metadata.title = "Options · Mytheca"`, renders `<OptionsView/>`.
- `OptionsView`: `AppShell`-style background; a slim top bar (❖ MYTHECA + a
  **"← Library"** link). Centered container **`w-full max-w-[1100px] lg:w-[66%]`**
  (66% on desktop, full-width with padding on small screens — see a11y note).
  Inside: a **vertical ARIA tablist** (left, roving tabindex + Up/Down/Home/End)
  and the active `role=tabpanel` (right). Default tab: **Language Models** (a
  placeholder panel in this phase — "configured in the next step").
- `features/options/useOptionsSettings.ts` — loads `getSettings()` on mount
  (loading/error/Retry), exposes the config + savers.

### 2.4 Tabs (this phase)
- `tabs/AppearanceTab.tsx` — theme cards (label + swatch + selected state) via
  `useTheme`; copy noting persistence.
- `tabs/LibraryDefaultsTab.tsx` — default-storyline `<select>` (from
  `listStorylines`) + "open last storyline" toggle; saves via
  `updateLibraryDefaults`.
- `tabs/AboutTab.tsx` — read-only rows: app version (constant), backend health
  (`getHealth`), provider, API base (`API_BASE`), active model. No secrets.

### 2.5 Tests
- `OptionsView.test.tsx` — renders; tab click + Arrow keys switch panels; default
  is Language Models; "← Library" link present.
- `OptionsMenu.test.tsx` — opens; Settings Menu links to `/options`; appearance
  swatches call `setTheme`.
- `tabs/AppearanceTab.test.tsx`, `tabs/LibraryDefaultsTab.test.tsx` (mock
  `@/lib/api`). `AboutTab` covered via OptionsView smoke.

### Validation + commit (Phase 2)
`npm test` + `npm run typecheck` + `npm run lint` + `npm run build` green.
**A11y/responsive pass** (keyboard tablist, focus-visible, contrast, 320/375/768/
1024 — the 66% panel must not overflow; collapses to full width on small). Update
`docs/routes.md`, `docs/component-map.md`. Commit:
`[Options Menu] (2/3) Complete: header Options dropdown + /options shell + Appearance/Library/About tabs`.

---

## Phase 3 — Frontend: Language Models tab (full)

`tabs/LanguageModelsTab.tsx`:
- **Base URL** field (placeholder `http://localhost:7070/v1`); **Fetch models**
  button + auto-fetch on blur when non-empty → `fetchLlmModels`. loading / error /
  empty states.
- **API key** (password) — shows "•••• set" + Change when one is stored; left
  blank = keep existing.
- **Provider** label (`openai` / `local` / `openai-compatible`).
- **Models** `<select>` populated from the fetch (disabled until fetched); empty
  state "Fetch models to choose."
- **Parameters**: temperature, maxTokens, topP, frequencyPenalty,
  presencePenalty (numeric inputs with ranges).
- **Test connection** button → `testLlmConnection` → shows ok + latency + sample,
  or a structured error.
- **Save** → `updateLlmConfig`; success/error feedback.

State: hydrate from `useOptionsSettings`; local form; dirty/save tracking.

### Tests — `tabs/LanguageModelsTab.test.tsx` (mock `@/lib/api`)
Fetch populates the model select; selecting + Save calls `updateLlmConfig` with
the chosen model/params; Test shows the success result; a fetch error renders the
error state and leaves the select empty.

### Validation + commit (Phase 3)
`npm test` + typecheck + lint + build green; a11y/responsive pass on the tab.
Update `docs/component-map.md`, `docs/documentation.md` (status), `docs/checklist.md`.
Commit: `[Options Menu] (3/3) Complete: Language Models tab — fetch/select/test/params/save`.

---

## Deliverables

| Area | Files |
| --- | --- |
| Backend model | `web/backend/app/models/app_setting.py` (+ `__init__`) |
| Backend schemas | `web/backend/app/schemas/settings.py` |
| Backend services | `web/backend/app/services/settings_store.py`, `services/llm.py` |
| Backend route | `web/backend/app/routes/settings.py` (+ `main.py`) |
| Backend tests | `utils/tests/backend/api/test_settings.py`, `test_llm.py` |
| Frontend api | `web/frontend/lib/api.ts` (extend) |
| Frontend header | `components/feature/OptionsMenu.tsx`, `components/layout/AppHeader.tsx` |
| Frontend route | `app/options/page.tsx`, `features/options/OptionsView.tsx`, `useOptionsSettings.ts` |
| Frontend tabs | `features/options/tabs/{LanguageModels,Appearance,LibraryDefaults,About}Tab.tsx` |
| Frontend tests | co-located `*.test.tsx` per the above |
| Docs | `routes.md`, `component-map.md`, `api-contract.md`, `data-flow.md`, `structure.md`, `documentation.md`, `checklist.md` |
