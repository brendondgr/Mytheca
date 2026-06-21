# Velora — Design System & Design-Quality Brief

This is the design gate that must be satisfied before broad UI implementation. It follows `docs/skills/ui-frontend/ui/design-quality.md`. Values below are a starting direction to refine during UI design — record final decisions here.

## Visual Motif

Velora is an **interactive-fiction / narrative engine**, not a generic SaaS dashboard. The motif is "a living manuscript / unfolding scene": a calm reading surface where streamed story beats appear like a play script or annotated transcript, with structured narrator cards and contextual side panels. Avoid sci-fi "AI" clichés.

## Domain Vocabulary (use in copy)

scene · character · event · beat · turn · narrator · memory · session · world/rules. Replace vague phrases ("AI-powered storytelling") with concrete actions ("Start a scene", "Add a character", "Replay this beat", "Recall a memory").

## Palette (starting direction)

- Neutral, paper-like base for the reading surface (warm off-white / deep ink in dark mode).
- One restrained accent for interactive elements and narrator emphasis.
- Semantic colors for status (success/warn/error) that never carry meaning by color alone.
- All text meets WCAG AA contrast (4.5:1 body, 3:1 large/non-text). Verify in both themes.

## Typography

- A readable text face for story content with comfortable measure (line length) and 1.5–1.75 line height.
- Body ≥ 16px on mobile; a clear type scale for headings, narrator-card titles, and metadata.
- Distinguish narrator beats, character turns, and user turns typographically — not by color alone.

## Geometry, Shadow, Icon, Spacing

- Consistent radius and spacing scale (define exact tokens here when chosen).
- Subtle elevation for narrator cards and panels; no decorative glassmorphism.
- Icon set: a single coherent line-icon family. Avoid generic AI brain / sparkle / network-node icons as the brand.

## Motion (Framer Motion)

- Purposeful only: new turns/beats animate in to signal arrival; panels slide; transitions guide attention.
- Always honor `prefers-reduced-motion` (provide a near-instant fallback).

## Meaningful Imagery

Near the top of key pages show **real artifacts**: a live/sample scene transcript, a narrator card, an event timeline, a character sheet — not abstract orbs, mesh gradients, or fake dashboards.

## Required UI States (design all)

loading · empty · error · partial-data (mid-stream) · stalled/reconnecting stream · success · permission-denied · long-content · dense-data · mobile · reduced-motion.

## At Least One Velora-Specific Layout Decision

The **story player** uses a reading-first center column (the transcript of turns and narrator cards) with a collapsible context side panel (scene state / characters / active memories) — not a generic three-pane app shell or a card grid. On mobile the side panel becomes a drawer; the transcript stays the primary surface.

## Anti-Generic Checklist (forbidden unless justified)

- Blue/purple neon gradients, glowing orbs, mesh backgrounds.
- Floating glassmorphism cards as decoration.
- Generic AI brain / sparkle / chat-bubble iconography as identity.
- Fake metrics and unverifiable dashboards.
- Perfectly centered hero with no product-specific detail.
- Every section reusing the same card grid, heading width, and spacing.
