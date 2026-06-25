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
| UI primitives | ui | `components/ui/` — `Monogram`, `Eyebrow`, `SectionHeader`, `Tag`, `Chip`, `ToggleChip`, `IconButton`, `Button`, `FieldLabel`, `TextField`, `TextArea`, `Modal` (portal + focus trap + Esc/backdrop). |
| Domain types | lib | `lib/types.ts` — `Character` / `Setting` / `Branch` / `Scenario` / `ResolvedScenario` / `EventTag`. |
| Seed data | lib | `lib/seed-data.ts` — Embergate cast/settings/scenarios + agentic-draft pools + `resolveScenario`. |
| Helpers | lib | `lib/monogram.ts` (`monoOf`), `lib/cn.ts` (classnames joiner). |
| `AppHeader` | layout | `components/layout/AppHeader.tsx` — wordmark, `storylineSlot` (the switcher), search, `createSlot`, `optionsSlot`. Theme switching moved into the Options dropdown / Options page (the standalone `ThemeSwitcher` was removed from the header; it still ships on `SceneHeader`). |
| `StorylineMenu` | feature | `components/feature/StorylineMenu.tsx` — header dropdown switching the active storyline (✓ active + counts), with per-row **Edit** (pencil) and **Delete** (trash) actions (`aria-label`'d icon buttons), plus "New Storyline" (opens `StorylineModal`); themed popover (outside-click + Esc, `aria-haspopup`/`expanded`/`current`). |
| `StorylineModal` | feature | `components/feature/StorylineModal.tsx` — write-first storyline create **and edit** modal. **Main column** (`md+`): a by-hand form (Title + Genre on one row, full-width Tagline, then Premise) beside the agentic **Draft with Velora** seed (with a full-width draft button), over a **full-width World Primer row** + actions; a **detached context-files column** (`lg`) runs the **full height** down the right side. The **seal + color picker** sit right-justified in the header (preview left of the symbol/color grids, no "Seal" label). Create persists via `POST /storylines`; edit (prefilled, "Save Changes") via `PATCH /storylines/{id}`. The agentic seed box drafts the metadata (`POST /storylines/draft`), **"Generate primer"** writes the World Primer (`POST /storylines/primer`). The context column's drop zone reads `.txt`/`.md` files in-browser (`lib/readDocs.ts`); each dropped file is **showcased with per-use toggles — Draft / RAG / KG** (`ReadDoc.useDraft/useRag/useKg`). Only **Draft** is wired (it filters which files ground generation, via `docsForDraft`); **RAG/KG** are forward-looking seams (those systems deferred). Files are **not** persisted. |
| `StorylineDeleteModal` | feature | `components/feature/StorylineDeleteModal.tsx` — confirmation before deleting a storyline (spells out the cascade: its scenarios/characters/settings); `DELETE /storylines/{id}`, then reselects the first remaining world if the active one was deleted. |
| Library cards | feature | `components/feature/` — `CharacterCard` (disclosure, `highlighted` cast state), `SettingCard` (`active` state + `aria-current`), `ScenarioCard` (stretched select button). |
| Library columns | feature | `components/feature/` — `ScenarioColumn` (1/row), `CharacterColumn` (2/row, lights up cast), `SettingColumn` (1/row, active setting forward), `ColumnChrome` (shared header + empty note). |
| `LibraryTabs` | feature | `components/feature/LibraryTabs.tsx` — ARIA tablist w/ roving tabindex + arrow keys; now the **mobile-only** section switcher (`lg:hidden`). |
| `ScenarioCarousel` | feature | `components/feature/ScenarioCarousel.tsx` — recent-scenario hero w/ slide track, prev/next, dots; theme-aware tokens + empty-storyline state. |
| `LibraryView` + `LibraryColumns` + `useLibraryState` | feature module | `features/library/` — `LibraryView` composes header + carousel + columns; `LibraryColumns` is the responsive 3-column container; `useLibraryState` holds storyline-scoped state (active storyline → cast/settings/scenarios) + tab/featured/search/expand + editor/modal/draft/profile. Route: `app/page.tsx`. |
| `CreateMenu` | feature | `components/feature/CreateMenu.tsx` — "+ Create" popover (outside-click + Esc): Character / Setting / Scenario. |
| `EntityModal` + forms | feature | `components/feature/EntityModal.tsx` with `CharacterForm` / `SettingForm` / `ScenarioForm`; create/edit/delete. **Desktop (`md+`)**: two-column layout — the By-hand form fills the left, the Agentic draft panel sits in a fixed right rail (so chat can build live into the form), toggle hidden. **Mobile (`< md`)**: a By-hand / Agentically toggle swaps a single column. Draft is still faked. |
| `CharacterProfileModal` | feature | `components/feature/CharacterProfileModal.tsx` — read-only profile + Edit. |
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
