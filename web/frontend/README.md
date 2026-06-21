# Velora Frontend (Next.js)

This is the Velora web UI: Next.js (App Router) · React · TypeScript · Tailwind CSS · Framer Motion.

Scaffolded with Next.js 16 (App Router, Turbopack), React 19, Tailwind CSS v4 (CSS-first `@theme`), and Framer Motion. Brand fonts (Cinzel / EB Garamond / IBM Plex Mono) load via `next/font` in `app/layout.tsx`. Tests use Vitest + React Testing Library and are co-located beside components (`*.test.tsx`).

```bash
# from web/frontend/
npm install        # install dependencies
npm run dev        # dev server (http://localhost:3000)
npm run build      # production build
npm test           # Vitest (run once)
npm run lint       # ESLint
npm run typecheck  # tsc --noEmit
```

Read [../../docs/skills/ui-frontend/SKILL.md](../../docs/skills/ui-frontend/SKILL.md), [../../docs/design-system.md](../../docs/design-system.md), and [../../docs/component-map.md](../../docs/component-map.md) before building UI.
