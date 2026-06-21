# Dropdowns & Selects

Default browser `<select>` dropdowns frequently introduce harsh white backgrounds and black text that break the immersive dark-mode aesthetic. All dropdowns in the application must use custom UI implementations while rigorously maintaining keyboard access and ADA compliance.

### Aesthetics & Theme Alignment
- **Background**: Menus use the `Elevated` (`#1e1e1e`) or `Surface` (`#141414`) background colored to stand out against the `Base` background.
- **Text & Contrast**: High-contrast white or light gray text. The background-to-text contrast must be at least **4.5:1**.
- **Hover/Focus**: Interactive items should feature a subtle neon background tint rather than solid white. **Critical**: They must exhibit a visible focus indicator when navigated by a keyboard (e.g., `focus-visible:ring-2 focus-visible:outline-none`).
- **Active/Selected**: Selected items should visually indicate their state (`aria-selected="true"`) using a vibrant neon text accent or a subtle left-border indent.

### Implementation Guidelines
- **Structure**: Utilize headless UI components (e.g., Radix UI, Headless UI) styled with Tailwind/UnoCSS to ensure keyboard accessibility (Arrow keys, Enter, Esc, Space) and ARIA support (`role="listbox"`, `role="option"`) while keeping complete DOM customization.
- **Animation**: Implement quick CSS scale-in or GSAP list animations. Elements must not trigger layout context changes unexpectedly on focus.
- **Mobile Adjustments**: On mobile viewports, complex dropdown options should adapt into touch-pan-friendly bottom sheets to ensure minimum **`44x44px`** hit areas and avoid trapping touch focus. Use `<dialog>` elements or a full-screen overlay for mobile selectors instead of hovering lists that get clipped by the viewport.