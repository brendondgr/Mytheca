# Data Visualization & Graphs

Interactive charts, plots, and robust data visualizations frequently fall short of accessibility and mobile usability standards. All data viz implementations must adhere strictly to these guidelines.

### Accessibility (ADA Compliance)
- **Contrast & Color Distinction**: Do not rely strictly on color (e.g., green vs. red lines) to distinguish data. Use varying patterns (dashed vs. solid lines), distinct geometric markers (circles, triangles, squares), and direct inline text labeling where possible. Ensure contrast of 3:1 for all graphical elements and 4.5:1 for axis text.
- **Screen Reader Support**: Complex graphical outputs (SVG, Canvas) must feature a visually hidden but programmatically associated tabular data representation (`<table>`) or extended description serving as an alternative.
- **Keyboard & Focus**: If tooltips or specific data points are interactive, they must be fully traversable via keyboard (e.g., arrow keys). The chart container or data points require a visible focus indicator.

### Mobile & Readability Standards
- **Responsive Sizing**: The core chart structure should adapt fluidly or support horizontal swipe (`touch-pan-x` and `overflow-x-auto`) rather than squishing data points together resulting in unreadable overlapping text.
- **Text Sizing in Graphs**: All labels, axis units, and tooltip content must remain legible on a 320px viewport. The minimum font size embedded within SVGs or canvas charts must be scaled to effectively represent `14px` or larger.
- **Touch-Friendly Interactivity**: Hover-only tooltips are forbidden. Incorporate standard tap interactions or crosshairs that follow touch events securely. The interactive target area for selecting individual plot points must be artificially expanded to meet the **44x44px minimum touch target**.

### Implementation Example

```html
<!-- Data Visualization Wrapper with Accessibility Features -->
<div class="relative w-full overflow-hidden rounded-xl border border-white/10 bg-surface">
  
  <!-- Accessible description for screen readers -->
  <div class="sr-only" id="chart-description">
    A line chart displaying system performance metrics for the last 30 days. 
    Metrics show a steady climb from 45% to 82% over the month.
  </div>

  <!-- Accessible Table Data Fallback -->
  <table class="sr-only" aria-hidden="false">
    <caption>Performance Metrics Data</caption>
    <tr><th scope="col">Date</th><th scope="col">Performance (%)</th></tr>
    <tr><td>01/01</td><td>45%</td></tr>
    <!-- ... -->
  </table>

  <!-- Chart Canvas / SVG Container -->
  <!-- Allow keyboard access to the chart area -->
  <figure aria-labelledby="chart-description" tabindex="0" class="focus-visible:ring-2 focus-visible:ring-primary w-full h-[300px] overflow-x-auto touch-pan-x">
    <!-- Render chart library output here (e.g., Recharts, D3, Chart.js) -->
    <svg class="min-w-[500px] w-full h-full text-base sm:text-lg" ...>
       <!-- SVG contents with text readable at 16px font-size -->
    </svg>
  </figure>
</div>
```