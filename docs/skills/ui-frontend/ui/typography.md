# Typography

Typography must be exceedingly legible on both small mobile screens and large desktop displays, strictly adhering to ADA contrast and sizing standards.

### Core Choices & Accessibility
- **Contrast**: All regular-sized text must maintain a minimum contrast ratio of **4.5:1** against backgrounds. Large text (typically `text-xl` or above, >18pt) requires a **3:1** ratio.
- **Headings**: Geometric and modern typefaces that provide a sleek, functional personality. Scale down appropriately on mobile, but strictly ensure proper semantic HTML hierarchy (`<h1>` through `<h6>` without skipping levels).
- **Body Text Size & Line Height**: Clean sans-serif aesthetics. Ensure a minimum body text size of **16px (`text-base`)** for mobile readability. This prevents iOS auto-zoom on input focus. Apply a line-height of `1.5 - 1.75em` (`leading-relaxed`) to improve legibility on small screens. Avoid texts smaller than `12px` (the absolute minimum floor for metadata).
- **Adaptive Sizing & Fluid Type**: Use fluid type scaling with CSS `clamp()` so text scales smoothly without explicitly breaking layouts. Ensure users can adjust text size or zoom up to **200%**.
- **Line Length**: Set max widths to `65–75ch` on paragraphs. Do not let text stretch edge-to-edge on wider phones or tablets.
- **Mono**: Monospaced fonts used for labels, numerical values, and metadata. Provide enough line height (typically 1.5) for comfortable reading.

### Responsive Implementation (UnoCSS/Tailwind)
Use fluid typography or breakpoint-specific utility classes to ensure mobile readability without horizontal overflow.

```html
<!-- Responsive Heading structure - Ensure semantic order -->
<h1 class="font-display text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-white leading-tight">
  Dashboard Overview
</h1>

<!-- Body text adapting to screen size, keeping minimum base 16px size for legibility -->
<p class="font-body text-base sm:text-lg text-gray-300 mt-4 max-w-[65ch] leading-relaxed">
  Detailed metrics and system analysis designed for readability.
</p>

<!-- Tabular data in Mono - Contrast remains strictly 4.5:1 -->
<span class="font-mono text-sm md:text-base text-primary tabular-nums">
  1,024.50
</span>
```
