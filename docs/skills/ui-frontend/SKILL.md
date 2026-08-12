---
name: ui-frontend
description: Use this skill when designing or implementing Mytheca's frontend UI — components, pages, the streaming narrative renderer, responsive layouts, the visual system, motion, and interaction quality on the locked Next.js + React + TypeScript + Tailwind v4 + Framer Motion stack.
---

# Mytheca Frontend Design & UI System

## Structural Dependency

For any full page or app surface, first follow `website-architecture` (routes, data flow, streaming contract) and `repository-structure` (where components live). This skill covers visual design, responsive behavior, accessibility polish, and interaction quality on top of that.

Always pair with `accessibility-mobile` and `ada-compliance`.

**The concrete token values, theme definitions, and component specs live in `docs/design-system.md`.** That file is the source of truth for anything numeric. This skill is the judgment layer.

## Locked Stack

- **Framework:** Next.js 16 (App Router, Turbopack), React 19, **TypeScript**.
- **Styling:** Tailwind CSS **v4**, CSS-first. Theme tokens are CSS variables in `web/frontend/styles/themes.css`, mapped to utilities via `@theme inline` in `app/globals.css`. **Never hardcode a hex value in a component** — use a token.
- **Motion:** **Framer Motion 12**, purposeful only. GSAP is not installed and must not be introduced.
- **Graph rendering:** `react-force-graph-2d`, imported **only** by `components/feature/GraphCanvas.tsx` via `next/dynamic({ ssr: false })` — it reads `window` at import and must stay out of the initial bundle.
- **Primitives:** native HTML, with accessible behavior hand-written in `components/ui/`. No headless component library is installed.
- **Tests:** Vitest + React Testing Library, **co-located** beside each component.

Do not add packages speculatively. Every library needs a recorded job in `docs/architecture.md` or `docs/design-system.md`.

## The Visual Language

Mytheca is an **illuminated manuscript**, not a SaaS dashboard. Warm parchment reading surfaces, wax-seal avatars, small-caps Cinzel headings, EB Garamond body prose, IBM Plex Mono for micro-captions and diagnostics.

Three themes, all first-class — every change must be checked in all three:

| Theme | Class | Character |
| --- | --- | --- |
| Parchment | `.theme-light` | Warm aged paper, the default reading experience |
| Ember | `.theme-dark` | Dark, firelit, warm-shadowed |
| Slate | `.theme-slate` | Dark, cool, blue-grey |

Four font-size presets (`.fs-compact` / `.fs-default` / `.fs-comfortable` / `.fs-large`) scale six `--fs-*` variables. Type sizes come from those variables, not from arbitrary Tailwind text classes, so the user's preference actually applies.

## Mytheca-Specific Surfaces

First-class, designed with real states rather than placeholders:

- **Story player** — the running scene. Turns stream in as NDJSON story events. Must handle streaming-in-progress, partial messages, stalled streams, resumed sessions, and reconnect.
- **Transcript beats** — `TranscriptBeat` routes each event type to exactly one renderer. A character's hidden thinking folds into the *same* bubble as their speech, separated by a hairline rule; it is never a separate beat.
- **Rails** — `CastRail` (presence, live stats, thinking/speaking indicators), `DirectorRail` (scene pulse feed, state chips), `CharacterDossier` (takes over the right rail when a character is clicked).
- **Graph view** — force-directed canvas plus an inspector rail, swapped in from the scene header. **A canvas is invisible to assistive tech**: the required text alternative is an `sr-only` description plus a node/edge `<table>`, and a visible legend.
- **Authoring surfaces** — the storyline creator with its conversational Assistant, and the character/setting/scenario modals. These show live agentic progress: a field-active ring, a choreographed reveal, a step progress line, and error toasts.

## Core Principles

- **Project specificity.** Motifs, copy, empty states, and examples come from the narrative domain — storyline, scenario, cast, beat, turn, stat, narrator.
- **Concrete copy.** Exact user actions and outcomes; empty states say what to do next ("The scene is quiet — your move").
- **Real states.** Design loading, empty, error, partial-data (mid-stream), success, long-content, dense-data, mobile, and reduced-motion. Not just the happy path.
- **Motion explains.** Entrances for arriving beats, reveals for streamed fields, transitions that show causality. Motion that merely decorates gets cut.
- **Never color alone.** Every meaning carried by color also carries text or shape — the graph legend, the inspector tags, the presence badges, the context dial tooltip.
- **Layout variety.** Avoid repeating one card grid everywhere; the transcript, rails, columns, and hero carousel are deliberately different shapes.

## Motion Rules

**`docs/frontend-polish-spec.md` is the standing contract for new UI** — motion tokens, the
loading state ladder, interaction states, and responsiveness. `docs/design-system.md` records
how Mytheca implements it and the four deviations taken;
`docs/plans/frontend-polish-acceptance.md` is the last verified pass against its §14 checklist.

- **Never hardcode a duration or an easing.** Use the `--dur-*` / `--ease-*` tokens, the
  `duration-fast|base|slow` / `ease-soft` utilities, or `ENTER_TRANSITION` from `lib/motion.ts`
  for Framer props. `utils/scripts/check_frontend_css.mjs` fails on an undefined motion token.
- **A hover that moves an element must be pointer-gated** — use `.hover-lift` / `.hover-nudge`
  / `.hover-grow`, never a bare `hover:scale-*` or `hover:translate-*`. Tailwind's `hover:`
  is not gated, so on touch the state lands on tap and sticks.
- **Every async boundary owes five states** and a 300 ms delay gate (`useDelayedFlag`). A
  skeleton must trace the real layout and must time out.
- Respect `prefers-reduced-motion` everywhere. The global rule in `themes.css` already kills all `animation` under `.mytheca-themed *` when reduced motion is set, so a new keyframe needs a sensible **static base style**, not a separate media query.
- Framer `MotionConfig` handles component-level reduction; CSS `motion-reduce:` utilities handle the rest.
- Choreographed reveals collapse to instant under reduced motion.
- Never convey information through motion alone — the typing indicator is paired with a literal "Thinking" / "Speaking" label.

## Accessibility Baseline

- Streamed and updating regions use polite ARIA live regions (`role="log"` for the transcript and scene pulse, `role="status"` for progress, `role="alert"` for errors).
- Everything is keyboard-operable: modals trap focus and close on Escape, menus support arrow-key roving focus, popovers close on outside click.
- Visible `:focus-visible` indication everywhere. The composer textarea deliberately opts out of the global outline in favor of the panel's `focus-within` border — that is the one documented exception.
- All token pairs meet WCAG AA and are enforced by `utils/scripts/check_contrast.py`. Run it after any theme-token change.

## Patterns To Avoid

- Neon gradients, glassmorphism, glowing orbs, mesh backgrounds. Mytheca is warm and papery — none of these belong, and none appear in the codebase today.
- Generic AI brain / network-node / sparkle iconography as brand.
- Fake dashboards and unverifiable metrics.
- Vague phrases ("AI-powered storytelling") not followed by concrete behavior.
- Hardcoded colors, or type sizes that bypass the `--fs-*` scale.

## Index

- [Design Quality and Anti-Generic Rules](ui/design-quality.md) — the operating standard and review checklist.
- `docs/design-system.md` — the authoritative token, theme, typography, and component reference.
- `docs/component-map.md` — what every existing component is and where it lives.

## Related Skills

- [Mobile Accessibility and Responsive UX](../accessibility-mobile/SKILL.md)
- [ADA and WCAG Compliance](../ada-compliance/SKILL.md)
