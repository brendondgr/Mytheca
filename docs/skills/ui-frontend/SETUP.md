# UI Frontend Setup

When configuring the UI frontend, answer these questions before generating pages or components.

## 1. Framework and Rendering

Which frontend architecture should be used?

- Astro
- SvelteKit
- React/Vite
- React/Next.js
- Flask/Jinja or Flask/HTMX
- Django templates
- API-backed frontend
- Static HTML/CSS/JS

Also define whether the project is static, SSR, SSG, ISR, SPA, server-rendered templates, or a mixed model.

## 2. Styling and Component System

Which styling and component choices should be used?

- Tailwind
- UnoCSS
- SCSS
- CSS Modules
- vanilla CSS
- styled-components
- shadcn/ui
- Radix UI
- Headless UI
- native HTML/custom primitives

If shadcn/ui, Radix UI, or another component system is selected, define where generated/custom components live and how they are customized.

## 3. Interaction Libraries

Which optional libraries are needed?

- TanStack Query for API-backed server state
- TanStack Router or React Router for client-side routing
- TanStack Table for dense tables
- React Hook Form and Zod for complex forms
- Framer Motion/Motion, GSAP, CSS transitions, or View Transitions for motion

Only include a library when the project has a matching need.

## 4. Visual Identity

Define the visual direction:

- tone, such as utilitarian dashboard, editorial, playful, clinical, luxury, technical, brutalist, or minimal
- project-specific visual motif
- color palette
- typography direction
- radius, shadow, icon, texture, and spacing rules
- meaningful imagery, product screenshots, diagrams, or sample artifacts

## 5. Anti-Generic Quality Bar

Define how the interface will avoid generic AI-site patterns:

- Which cliches must be avoided?
- What concrete product language should replace vague copy?
- What real workflow artifacts, sample outputs, or states should be shown?
- Which layout should break away from repeated card grids?
- Which fake metrics or placeholder claims are forbidden?

Use `ui/design-quality.md` as the review checklist.

## 6. Modularity and Ownership

Define how strictly components should be isolated:

- primitive UI components
- layout/chrome components
- route-level components
- feature/domain components
- hooks/utilities
- styles/tokens
- assets and illustrations

## 7. Required States

List required UI states:

- loading
- empty
- error
- success
- partial data
- permission denied
- long content
- dense data
- mobile
- reduced motion

*(AI Note: For full websites, dashboards, and web applications, route layout, page hierarchy, data needs, and frontend/backend boundaries must come from `website-architecture/SETUP.md`. Do not invent structural assumptions from UI preferences alone.)*
