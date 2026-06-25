# Velora — Component Map

Defines where frontend components live and who owns them. Ownership rules come from `docs/skills/repository-structure/SKILL.md`. Update this file as components are added.

## Layers

| Layer | Location | Contains |
| --- | --- | --- |
| Primitives (`ui`) | `web/frontend/components/ui/` | Buttons, inputs, dialogs, tabs, toasts — reusable, domain-agnostic. Radix UI / shadcn-style copies live here. |
| Chrome (`layout`) | `web/frontend/components/layout/` | App shell, top nav, side panels/rails, drawers, footers, theme switcher. |
| Domain (`feature`) | `web/frontend/components/feature/` | Velora-specific UI: narrator cards, character bubbles, action cards, stats panel, branch choices, character sheet. |
| Feature modules | `web/frontend/features/` | Larger composed surfaces: `story-player/`, `storylines/`, `characters/`, `settings/`, `scenarios/`. |
| Hooks | `web/frontend/hooks/` | `use-event-stream` (SSE/WS NDJSON consumer), `use-auth`, `use-theme`, etc. |
| Helpers | `web/frontend/lib/` | API client, formatting, contract adapters. |
| Styles/tokens | `web/frontend/styles/` + `docs/design-system.md` | Tailwind theme + the three Velora themes (Parchment/Ember/Slate). Token decisions documented in design-system. |

## Implemented (frontend)

| Component / module | Layer | Location |
| --- | --- | --- |
| `AppShell` | layout | `components/layout/AppShell.tsx` — themed page background/glow wrapper (server component). |
| `ThemeSwitcher` | layout | `components/layout/ThemeSwitcher.tsx` — three-dot Parchment/Ember/Slate picker. |
| `useTheme` / `setTheme` | hook | `hooks/use-theme.tsx` — `useSyncExternalStore` over the `<html>` theme class + `localStorage`. |
| Theme tokens | styles | `styles/themes.css` (token sets) + `app/globals.css` (`@theme inline` Tailwind mapping). |
| Brand fonts | lib | `lib/fonts.ts` — Cinzel / EB Garamond / IBM Plex Mono via `next/font`. |
| UI primitives | ui | `components/ui/` — `Monogram` (initials avatar; optional `src` upgrades it to a portrait image with the same colored ring), `Eyebrow`, `SectionHeader`, `Tag`, `Chip`, `ToggleChip`, `IconButton`, `Button`, `FieldLabel`, `TextField`, `TextArea`, `Modal` (portal + focus trap + Esc/backdrop; optional `externalClose` renders a reddish × hovering outside the panel, still inside the trap; optional `splitScroll` gives the panel's columns independent vertical scroll at `lg+` instead of the whole dialog scrolling), `FieldLabel` (bold + slightly larger for legible editor headers). |
| Domain types | lib | `lib/types.ts` — `Character` / `Setting` / `Branch` / `Scenario` / `ResolvedScenario` / `EventTag`. |
| Seed data | lib | `lib/seed-data.ts` — Embergate cast/settings/scenarios + agentic-draft pools + `resolveScenario`. |
| Helpers | lib | `lib/monogram.ts` (`monoOf`), `lib/cn.ts` (classnames joiner). |
| `AppHeader` | layout | `components/layout/AppHeader.tsx` — wordmark, `storylineSlot` (the switcher), search, `createSlot`, `optionsSlot`. Theme switching moved into the Options dropdown / Options page (the standalone `ThemeSwitcher` was removed from the header; it still ships on `SceneHeader`). |
| `StorylineMenu` | feature | `components/feature/StorylineMenu.tsx` — header dropdown switching the active storyline (✓ active + counts), with per-row **Edit** (pencil) and **Delete** (trash) actions (`aria-label`'d icon buttons), plus "New Storyline" (opens `StorylineModal`); themed popover (outside-click + Esc, `aria-haspopup`/`expanded`/`current`). |
| `StorylineModal` | feature | `components/feature/StorylineModal.tsx` — write-first storyline create **and edit** modal. **Main column** (`md+`): a by-hand form (Title + Genre on one row, full-width Tagline, then Premise) beside the agentic **Draft with Velora** seed (with a full-width draft button), over a **full-width World Primer row** + actions; a **detached context-files column** (`lg`) runs the **full height** down the right side. The header is a **single promoted title** ("Edit/New Storyline"); the **seal** is a **compact summary row** (preview glyph + **Edit** button) in the main column that opens `SealModal` (the full shape/color/wheel picker). Beneath the World Primer sits a **Statistics** editor (`StatsEditor`) defining the world's universal stats + labeled bands. The edit column and the context column each **scroll independently** at `lg+` (`Modal` `splitScroll`). Create persists via `POST /storylines`; edit (prefilled, "Save Changes") via `PATCH /storylines/{id}`; the universal stats are diffed into `POST`/`PATCH`/`DELETE /storylines/{id}/stats` on save. The agentic seed box drafts the metadata (`POST /storylines/draft`), **"Generate primer"** writes the World Primer (`POST /storylines/primer`). The context column's drop zone reads `.txt`/`.md` files in-browser (`lib/readDocs.ts`); each dropped file is **showcased with per-use toggles — Draft / RAG / KG** (`ReadDoc.useDraft/useRag/useKg`), with a file count and **per-category bulk All / None** controls for hundreds of files. Only **Draft** is wired (it filters which files ground generation, via `docsForDraft`); **RAG/KG** are forward-looking seams (those systems deferred). Files are **not** persisted. The whole modal scrolls (no nested scroll). The × close uses `Modal`'s `externalClose` — a reddish button hovering **outside** the panel's top-right corner (kept inside the focus trap). |
| `StorylineDeleteModal` | feature | `components/feature/StorylineDeleteModal.tsx` — confirmation before deleting a storyline (spells out the cascade: its scenarios/characters/settings); `DELETE /storylines/{id}`, then reselects the first remaining world if the active one was deleted. |
| Library cards | feature | `components/feature/` — `CharacterCard` (disclosure, `highlighted` cast state; avatar shows the WebP portrait when set, monogram otherwise), `SettingCard` (`active` state + `aria-current`), `ScenarioCard` (stretched select button). |
| Library columns | feature | `components/feature/` — `ScenarioColumn` (1/row), `CharacterColumn` (2/row, lights up cast), `SettingColumn` (1/row, active setting forward), `ColumnChrome` (shared header + empty note). |
| `LibraryTabs` | feature | `components/feature/LibraryTabs.tsx` — ARIA tablist w/ roving tabindex + arrow keys; now the **mobile-only** section switcher (`lg:hidden`). |
| `ScenarioCarousel` | feature | `components/feature/ScenarioCarousel.tsx` — recent-scenario hero w/ slide track, prev/next, dots; theme-aware tokens + empty-storyline state. |
| `LibraryView` + `LibraryColumns` + `useLibraryState` | feature module | `features/library/` — `LibraryView` composes header + carousel + columns; `LibraryColumns` is the responsive 3-column container; `useLibraryState` holds storyline-scoped state (active storyline → cast/settings/scenarios) + tab/featured/search/expand + editor/modal/draft/profile. Route: `app/page.tsx`. |
| `CreateMenu` | feature | `components/feature/CreateMenu.tsx` — "+ Create" popover (outside-click + Esc): Character / Setting / Scenario. |
| `EntityModal` + forms | feature | `components/feature/EntityModal.tsx` with `SettingForm` / `ScenarioForm`; create/edit/delete. Now owns **Setting + Scenario only** (Character moved to `CharacterModal`, Storyline to `StorylineModal`). Header is a **single promoted title** ("Edit/New Setting|Scenario"). **Desktop (`md+`)**: two-column layout — the By-hand form fills the left, the Agentic draft panel sits in a fixed right rail, toggle hidden. **Mobile (`< md`)**: a By-hand / Agentically toggle swaps a single column. Draft is still faked for these two. |
| `CharacterModal` | feature | `components/feature/CharacterModal.tsx` — the agentic **Character Creator** (mirrors `StorylineModal`). Header is a **single promoted title** ("Edit/New Character"). Main column: a by-hand form (name/role/traits + **voice/speech** with a non-functional **voice-sample upload** placeholder for future text-to-speech + **Appearance / Background / Personality**; Goal/Secret are no longer edited here but remain on the wire shape) with an avatar+accent header; an agentic **Draft with Velora** seed (`POST /characters/draft`, optionally grounded in the world + dropped docs); a **Starting stats** section (`POST /characters/starting-stats` → review/adjust → applied via `PUT /characters/{id}/stats`). The right column shows a **compact portrait preview** + **Edit image** button above Draft with Velora, opening `PortraitModal`. A detached **context-files** column (shared `ContextFilesPanel`); the edit column and context column **scroll independently** at `lg+` (`Modal` `splitScroll`). Produces §1 *node properties* only — no graph. |
| `PortraitModal` | feature | `components/feature/PortraitModal.tsx` — the character **portrait pop-up** (nested `Modal`, raised z) opened from `CharacterModal`'s Edit-image button. Holds the rendered-WebP/monogram preview, editable watercolor **positive/negative** prompts, **Generate prompts** (`POST /characters/portrait-prompts`, from the character's current context) and **Generate portrait** (`POST /characters/portrait`). Presentational — all generation handlers live on `useLibraryState`. |
| `SealModal` | feature | `components/feature/SealModal.tsx` — the storyline **seal pop-up** (nested `Modal`, raised z) opened from `StorylineModal`'s Seal-row **Edit** button. Large live preview + the expanded shape grid (~24 glyphs) + a curated color palette + a native **color wheel** (`<input type="color">`) for any custom hex. Presentational — writes `symbol`/`symbolColor` through the parent draft setters. Shape/color sets live in `lib/seals.ts`. |
| `StatsEditor` | feature | `components/feature/StatsEditor.tsx` — the **universal-stats editor** inside `StorylineModal` (under World Primer). Add/rename/remove stats (display name → slug `key`, locked once saved), set min/max/default, and edit labeled **bands** ("tickers" — `{min,max,label}`) describing what value ranges mean. Holds the list on `Draft._stats` with a `_statsOriginal` snapshot; the parent diffs it into create/update/delete calls on save. |
| `ContextFilesPanel` | feature | `components/feature/ContextFilesPanel.tsx` — shared detached context-files column used by `StorylineModal` + `CharacterModal`: drop `.txt`/`.md` (read in-browser via `lib/readDocs.ts`), per-file **Draft / RAG / KG** toggles + per-category bulk All / None + file count. Optional `scroll` gives it independent vertical scroll at `lg+`. Only **Draft** is wired (`docsForDraft`); RAG/KG are forward-looking seams. Files are never persisted. |
| `CharacterProfileModal` | feature | `components/feature/CharacterProfileModal.tsx` — read-only profile + Edit. Shows the WebP **portrait** (monogram fallback) and, when set, **Appearance / Background / Personality** alongside Voice / Goal / Secret. |
| `BeginSceneModal` | feature | `components/feature/BeginSceneModal.tsx` — narrator opening + cast/setting/goal; "Enter Scene" → `/play/[scenarioId]`. |
| `editor` helpers | feature module | `features/library/editor.ts` — Draft/ModalState types, defaults, validation, prompt copy. |
| `SceneHeader` | layout | `components/layout/SceneHeader.tsx` — back-to-Library, scene title/setting, theme, status. |
| Transcript beats | feature | `components/feature/TranscriptBeat.tsx` — `NarratorCard` / `CharacterMessage` / `PlayerMessage` / `CheckCard` / `BranchChoices` + the `TranscriptBeat` router (event→component contract). |
| `CastRail` / `TurnOrder` | feature | `components/feature/CastRail.tsx` — at-the-table cast (speaking marker) + turn order. |
| `DirectorRail` | feature | `components/feature/DirectorRail.tsx` — goal · `TensionMeter` · `StateChips` · `Relationships`. |
| `Composer` / `SceneLoader` | feature | `components/feature/{Composer,SceneLoader}.tsx` — roll/input/send; ❖ loader → reveal. |
| `StoryPlayerView` + `useScenePlay` + `scene-data` | feature module | `features/story-player/` — composes the player; seeds + drives send/roll/choose over local state. Route: `app/play/[scenarioId]/page.tsx`. |
| `OptionsMenu` | feature | `components/feature/OptionsMenu.tsx` — header "Options ▾" dropdown (outside-click + Esc, `aria-haspopup`/`expanded`/`controls`): a **Settings Menu** link → `/options`, plus a quick **Appearance** theme selector (label-free colored swatches; persisted via `velora-theme`). |
| `OptionsView` + `useOptionsSettings` + `tabs/*` | feature module | `features/options/` — `OptionsView` is the `/options` surface: a centered 66%-width panel with a **vertical ARIA tablist** (roving tabindex + ↑/↓/Home/End) on the left and the active `tabpanel` on the right. Tabs in `tabs/`: `LanguageModelsTab` (endpoint/API key/model/params + save; **fetch-models dropdown** via `POST /options/llm/models` — button + on-blur, falling back to a text input — and a **connection test** via `POST /options/llm/test`), `ImageModelsTab` (**ComfyUI** image generation: base URL + **workflow dropdown** via `GET /options/comfy/workflows`, default generation params + negative prompt, and a **status check** via `POST /options/comfy/status`; saves via `PATCH /options/comfy`), `AppearanceTab` (label-free theme swatches), `LibraryDefaultsTab` (default storyline + startup), `AboutTab` (read-only diagnostics, no secrets). `useOptionsSettings` loads `GET /options` (loading/error/Retry) and exposes `saveLlm`/`saveLibrary`/`saveComfy` (await-then-apply). Route: `app/options/page.tsx`. |

## Key Domain Components (planned)

| Component | Layer | Responsibility |
| --- | --- | --- |
| `StoryPlayer` | feature module | Orchestrates a live scenario: sends turns, consumes the event stream, renders the transcript + side rails. |
| `NarratorCard` | feature | Renders a `narration` event (teal-accented narrator card, italic prose). |
| `CharacterMessage` | feature | Renders a `character_dialogue` event: monogram avatar in the character's color + name + chat bubble; supports streaming-in-progress state. |
| `CharacterAction` | feature | Renders a `character_action` event (inline italic emote/action). |
| `PlayerMessage` | feature | Renders the user's own turn (right-aligned accent bubble). |
| `StatsPanel` | feature (side panel) | Renders stat values from `state_update` events; respects stat `visibility` (hides hidden stats); supports an animating bar / delta when promoted to `stat_update`. |
| `BranchChoices` | feature | Renders a `branch_choices` event as selectable paths (label, outcome, optional check). |
| `ScenarioStatePanel` | feature (side panel) | Cast at the table, turn order, scenario goal, tone/tension, relationships. |
| `CharacterSheet` | feature | Read/edit a character incl. its stat block. |
| `ThemeSwitcher` | layout | Switches between Parchment / Ember / Slate themes (persisted). |
| `EventStreamProvider` / `useEventStream` | hook/lib | Connects to `GET /stream/{sessionId}`, parses NDJSON, routes by `type`, exposes events + connection state (connecting, open, stalled, reconnecting, closed). |

## Conventions

- Each event `type` maps to exactly one renderer; the frontend never decides story layout beyond that mapping.
- Native HTML primitives first; reach for Radix/shadcn only for accessible headless behavior.
- Streamed/updating regions (transcript, stats) use polite ARIA live regions and respect `prefers-reduced-motion`.
- Distinguish narrator / character / player / action visually **and** typographically — never by color alone (see `docs/design-system.md`).
- Shared FE↔BE types come from `web/shared/contracts/`, not redeclared per component.
