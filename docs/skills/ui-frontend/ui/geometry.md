# Layout, Geometry & Glassmorphism

The app makes extensive use of transparency, depth, and soft geometry to feel layered. **Mobile-first design is absolutely critical**, starting at 375px and scaling up using flexible CSS Grid/Flexbox.

### Soft Geometry
- **Border Radii**: Generous rounding (`6px` to `24px`). Modals and segmented controls use high radii to soften the technical nature.
- **Elevation**: A shadow system using deep, diffuse drop-shadows creates clear spatial hierarchy.

### Modular Glassmorphism
- **Backdrop Blur**: Semi-transparent dark overlays with `backdrop-filter: blur()`.
- **Themed Glows**: Interactive elements use vibrant neon glows on hover (adapt to touch states on mobile).

### Images & Media Handlers
- **Responsive Embeds**: To eliminate layout shift (CLS), unconditionally set explicit `width` and `height` attributes on images.
- **Lazy Loading**: Enable below-the-fold media optimizations using `loading="lazy"` and `decoding="async"`. 
- **Formats & Serving**: Default to modern formats like **AVIF/WebP** utilizing the `<picture>` element with appropriate `srcset` sizes based on viewport.
- **Mobile Video**: Always use the `playsinline` attribute on `<video>` assets to prevent iOS from forcing fullscreen playback and breaking the app flow.

### Mobile-First Layout Strategy
- **Responsive Fluid Grids**: Rely on `%`, `fr`, `clamp()`, and `auto-fill` rather than fixed-pixel layouts. Ensure seamless breakpoint scaling (375px, 390px, 768px, 1024px+).
- **Single-Column Collapsing**: Multi-column layouts must collapse into stacked, single-column layouts on small mobile screens.
- **Prevent Horizontal Scrolling**: Set `max-width: 100%` on images, videos, and embedded content. If absolutely necessary, use `overflow-x: hidden` on the outer shell, avoiding forced horizontal scroll on the viewport.
- **Anchored Elements**: For mobile, anchor primary CTAs to the bottom of the screen within easy thumb reach. Avoid simultaneously stacking multiple sticky elements (e.g., sticky header + sticky footer + cookie banner).

### Implementation Structure (UnoCSS/Tailwind & React)

```html
<!-- Glassmorphism Container with Fluid Mobile Padding -->
<div class="bg-black/40 backdrop-blur-xl rounded-2xl sm:rounded-3xl shadow-2xl border border-white/5 p-4 sm:p-6 md:p-8 w-full max-w-full overflow-hidden">
  <!-- Fluid Single-Column to Multi-Column Layout -->
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
    <!-- Card Content -->
  </div>
</div>
```
