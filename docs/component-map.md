# Velora — Component Map

Defines where frontend components live and who owns them. Ownership rules come from `docs/skills/repository-structure/SKILL.md`. Update this file as components are added.

## Layers

| Layer | Location | Contains |
| --- | --- | --- |
| Primitives (`ui`) | `web/frontend/components/ui/` | Buttons, inputs, dialogs, tabs, toasts — reusable, domain-agnostic. Radix UI / shadcn-style copies live here. |
| Chrome (`layout`) | `web/frontend/components/layout/` | App shell, top nav, side panels, drawers, footers. |
| Domain (`feature`) | `web/frontend/components/feature/` | Velora-specific UI: narrator cards, chat turns, scene-state panel, character sheet. |
| Feature modules | `web/frontend/features/` | Larger composed surfaces: `story-player/`, `characters/`, `scenes/`, `graph/`. |
| Hooks | `web/frontend/hooks/` | `use-event-stream` (SSE/WS NDJSON consumer), `use-auth`, etc. |
| Helpers | `web/frontend/lib/` | API client, formatting, contract adapters. |
| Styles/tokens | `web/frontend/styles/` + `docs/design-system.md` | Tailwind theme, global styles. Token decisions documented in design-system. |

## Key Domain Components (planned)

| Component | Layer | Responsibility |
| --- | --- | --- |
| `StoryPlayer` | feature module | Orchestrates a live scene: sends turns, consumes the event stream, renders the transcript. |
| `NarratorCard` | feature | Renders a structured narrator beat (scene change, rules outcome, memory recall). |
| `ChatTurn` | feature | Renders a user or character turn, including streaming-in-progress state. |
| `SceneStatePanel` | feature (side panel) | Shows current scene state, active characters, active memories. |
| `CharacterSheet` | feature | Read/edit a character. |
| `GraphView` | feature module | Relationship/knowledge graph; must ship an accessible text alternative. |
| `EventStreamProvider` / `useEventStream` | hook/lib | Connects to `GET /stream/{sessionId}`, parses NDJSON, exposes events + connection state (connecting, open, stalled, reconnecting, closed). |

## Conventions

- Native HTML primitives first; reach for Radix/shadcn only for accessible headless behavior.
- Streamed/updating regions use polite ARIA live regions and respect `prefers-reduced-motion`.
- Shared FE↔BE types come from `web/shared/contracts/`, not redeclared per component.
