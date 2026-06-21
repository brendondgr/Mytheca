# Icons System

Icons form a core part of the brand identity. Keep stroke widths consistent across all viewports. Touch targets must be enlarged on mobile without increasing the visual footprint of the icon itself.

### Functional Mapping & Accessibility
- **Labeling**: Icons used for interactive elements **must** be provided with an `aria-label` or visually hidden screen reader text explaining their function. Decorative icons should include `aria-hidden="true"`.
- **Primary Actions**: Brand primary colors. Contrast must be **at least 3:1** to remain visibly distinct.
- **Edit/Manage**: Muted secondary tones (e.g., `#a3a3a3`).
- **Success/Create**: Bright positive tones.
- **Danger**: High-alert colors. Color should not be the sole identifier—combine the color with clearly identifiable warning shapes.

### Implementation Structure (UnoCSS/Tailwind)

```html
<!-- Accessibility-first Mobile-friendly Interactive Icon button -->
<button class="p-3 sm:p-2 -m-3 sm:-m-2 rounded-full hover:bg-white/10 active:bg-white/20 transition-colors group focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none" 
        aria-label="Application Settings" 
        title="Application Settings">
  <!-- The padding/margin trick ensures a 44x44px minimum hit bounds on mobile while keeping the icon visibly 24px -->
  <svg class="w-6 h-6 text-gray-300 group-hover:text-primary transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true" stroke-width="2">
    <!-- Icon paths -->
  </svg>
</button>
```
