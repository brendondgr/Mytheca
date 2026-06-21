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
