---
name: ui-frontend
description: Use this skill when designing or implementing Velora's frontend UI — components, pages, the streaming narrative renderer, responsive layouts, the visual system, motion, and interaction quality on the locked Next.js + React + TypeScript + Tailwind + Framer Motion stack.
---

# Velora Frontend Design & UI System

## Structural Dependency

For any full page, panel, or app surface, first follow `website-architecture` (routes, data flow, streaming contract, design-quality brief) and `repository-structure` (where components live). This skill handles the visual design, responsive behavior, accessibility polish, and interaction quality on top of that structure.

Always pair with:
- `accessibility-mobile` — responsive viewport, touch, mobile performance, mobile SEO.
- `ada-compliance` — WCAG 2.2 AA accessibility.

## Locked Stack

- **Framework:** Next.js (App Router), React, **TypeScript**.
- **Styling:** Tailwind CSS (utility-first). Design tokens recorded in `docs/design-system.md`.
- **Motion:** Framer Motion — purposeful only (entrances of narrator cards, event-stream reveals, transitions). Respect `prefers-reduced-motion`.
- **Primitives:** native HTML first; add Radix UI / shadcn-style copy-owned components in `web/frontend/components/ui/` only when accessible headless behavior is needed.
- **Optional, by job only:** TanStack Query (server-state caching), TanStack Table (dense tables), React Hook Form + Zod (complex character/scene editors).

Do not add packages speculatively. Every library needs a recorded job in `docs/architecture.md`, `docs/workflow.md`, or `docs/design-system.md`.

## Velora-Specific UI Surfaces

These are first-class and must be designed with real states, not placeholders:

- **Chat / story player:** the running scene — user turns, character turns, and narrator beats streamed in via the NDJSON event stream. Must handle streaming-in-progress, partial messages, reconnect, and stalled-stream states.
- **Narrator cards:** structured story beats (scene changes, rules outcomes, memory recalls) rendered as distinct cards, not plain chat bubbles.
- **Side panels:** character sheets, scene state, active memories/knowledge — collapsible and mobile-aware.
- **Graph visualizations:** relationship/knowledge-graph views (planned alongside the graph DB) — provide an accessible text alternative.
- **Editors:** character and scene creation/editing forms (validation, autosave/draft, error states).

## Design Quality Standard

The UI must feel human-designed and Velora-specific — an interactive-fiction / narrative product, not a generic SaaS dashboard. Use real narrative artifacts (a live scene, a narrator card, an event timeline) as the meaningful imagery near the top of key pages. Use concrete domain vocabulary in copy: scene, character, event, beat, memory, turn.

Follow `ui/design-quality.md` as the operating standard and review checklist.

## Core Principles

- Project specificity: motifs, copy, empty states, and examples come from the narrative domain.
- Concrete copy: replace vague claims with exact user actions and outcomes.
- Design-system consistency: define palette, typography, spacing, radius, shadows, icon style, and motion behavior in `docs/design-system.md` before building many sections.
- Layout variety: avoid repeated identical card grids; use the story timeline, scene state panels, character sheets, and graph views where they fit.
- Real states: design loading, empty, error, partial-data (mid-stream), success, permission, long-content, dense-data, mobile, and reduced-motion.
- Animation restraint: motion explains, guides, or responds to streamed events — it must not merely decorate.
- Accessibility & mobile: streamed/updating content must use polite ARIA live regions; the story player must be keyboard- and screen-reader-usable; mobile must feel intentionally designed, not just stacked.

## Patterns To Avoid

- Default blue/purple neon gradients, glassmorphism decoration, glowing orbs, mesh backgrounds.
- Generic AI brain / network-node / chat-bubble / sparkle iconography as the brand.
- Fake dashboards and unverifiable metrics.
- Perfectly centered heroes with no product-specific detail.
- Vague phrases ("AI-powered storytelling", "unlock your imagination") not followed by concrete behavior.
- Every section reusing the same card grid, heading width, and spacing.

## Component & Asset Index

- [Design Quality and Anti-Generic Rules](ui/design-quality.md)
- [Colors and Themes](ui/colors.md)
- [Typography](ui/typography.md)
- [Layout and Geometry](ui/geometry.md)
- [Motion and Animations](ui/motion.md)
- [Buttons and Interactive Elements](ui/buttons.md)
- [Dropdowns and Selects](ui/dropdowns.md)
- [Modals and Popups](ui/modals.md)
- [Icons System](ui/icons.md)
- [Data Visualization and Graphs](ui/data-viz.md)

## Related Skills

- [Mobile Accessibility and Responsive UX](../accessibility-mobile/SKILL.md)
- [ADA and WCAG Compliance](../ada-compliance/SKILL.md)

The original UI questionnaire is preserved in [SETUP.md](SETUP.md) for planning new surfaces.
