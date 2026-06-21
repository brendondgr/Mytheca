# Colors & Themes

The application relies heavily on a high-contrast, dark-mode color system adhering rigorously to ADA WCAG 2.2 AA standards. All color palettes must maintain high contrast to guarantee text legibility.

### Core Accessibility Mandates
- **Text & Core Information**: Must strictly meet a contrast ratio of **4.5:1** against the background.
- **Large Text, Icons & Borders**: Non-text UI components (active borders, input elements, interactive buttons) and large text require a contrast ratio of **3:1**.
- **Information Dependency**: Color must **never** be the only way to convey meaning. Pair critical status colors with distinct icons, descriptive text, patterns, or borders to ensure information is distinguishable for color-blind users.

### Neutral Base
- **Background**: `#0a0a0a` (Deep Matte Black) — Provides a stark, high-contrast canvas.
- **Surface**: `#141414` (Dark Gray) — Used for cards and secondary panels. Ensure text over this surface passes contrast checks.
- **Elevated**: `#1e1e1e` (Lighter Gray) — Used for modals, dropdowns, and floating elements.

### Brand Colors (Neon & Vibrant)
Select from this extended neon palette to create the application's unique signature:
- **Cyber Cyan**: `#00f0ff` | `0, 240, 255` — Excellent for primary interactive elements. Use darkened or outlined variants if overlaying text to preserve contrast.
- **Toxic Green**: `#39ff14` | `57, 255, 20` — High-contrast success states. Pair with distinct checkmarks.
- **Matrix Mint**: `#00ff9d` | `0, 255, 157` — Slightly softer neon green.
- **Plasma Pink**: `#ff007f` | `255, 0, 127` — Bold accents, active states, or intense notification dots.
- **Hot Magenta**: `#d500ff` | `213, 0, 255` — Deep but vibrant.
- **Electric Violet**: `#7000ff` | `112, 0, 255` — Secondary tones with luminescent qualities.
- **Atomic Orange**: `#ff5500` | `255, 85, 0` — Warning indications paired with warning triangle icons.
- **Laser Lemon**: `#eaff00` | `234, 255, 0` — Extreme contrast notifications. Black text recommended over this color.
- **Neon Crimson (Danger)**: `#ff003c` | `255, 0, 60` — Destructive action alerts. Always pair with text reading "Error" or "Delete" (do not rely on red alone).

### Categorization Tones
Used for classifying various data types:
1. **Deep Background**: Very low opacity, dark-tinted backgrounds (e.g., `rgba(0, 255, 157, 0.05)`).
2. **Vibrant Border**: Bright, saturated borders for categorization (e.g., 1px solid `#00ff9d`).
3. **High-contrast Text**: Light, bright text for legibility.

### Implementation Structure (UnoCSS/Tailwind)
```css
/* variables.css */
:root {
  --color-bg-base: #0a0a0a;
  --color-surface: #141414;
  --color-elevated: #1e1e1e;
  
  /* Neon Brand Tokens - RGB defined for opacity modifications */
  --color-primary: 0, 255, 157;    /* #00ff9d */
  --color-secondary: 59, 130, 246; /* #3b82f6 */
  --color-tertiary: 255, 0, 127;   /* #ff007f */
  --color-danger: 255, 0, 60;      /* #ff003c */
}
```

```html
<!-- Mobile-friendly card with surface color and vibrant border hover -->
<div class="bg-[var(--color-surface)] sm:bg-transparent sm:hover:bg-[var(--color-surface)] border border-transparent hover:border-[rgba(var(--color-primary),0.5)] transition-colors rounded-xl p-4 w-full max-w-sm">
  <span class="text-[rgba(var(--color-primary),1)] font-semibold text-sm">Category Label</span>
</div>
```
