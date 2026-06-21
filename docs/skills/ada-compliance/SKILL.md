---
name: ada-compliance
description: Use this skill when implementing, auditing, or documenting ADA-aligned web accessibility using WCAG 2.2 AA expectations for websites, web apps, UI components, forms, media, navigation, dynamic content, and semantic HTML.
---

# ADA and WCAG Compliance

Use this skill when a project needs accessibility requirements, accessibility review, or ADA-aligned website behavior. Treat WCAG 2.2 AA as the default target unless the user specifies a different standard. WCAG 2.1 AA may be the minimum requirement in some contexts, but this repository should prefer the more current AA target when feasible.

Before declaring a page, component, or workflow accessible, verify the checklist below or document any intentionally deferred items in `docs/checklist.md`.

## Images and Non-Text Content

- Meaningful images have descriptive `alt` text.
- Decorative images use `alt=""` or are implemented as decorative CSS backgrounds.
- Complex visuals such as charts, maps, and diagrams have an accessible text summary or extended description.
- Images of text are avoided unless essential, such as logos or brand marks.
- Linked images describe the link destination through their accessible name.

## Audio and Video

- Prerecorded video includes synchronized captions.
- Audio-only content includes a text transcript.
- Video communicates important visual-only information through audio description or adjacent text.
- Live audio or video includes captions when required by the project.
- Auto-playing audio longer than 3 seconds has a visible pause, stop, or mute control.

## Structure and Semantics

- Pages use semantic landmarks such as `header`, `nav`, `main`, `section`, `article`, `aside`, and `footer` where appropriate.
- Each page has a logical heading hierarchy.
- Headings, labels, and control names are descriptive.
- Lists use list markup, not visual-only line breaks.
- Data tables use captions and scoped headers when needed.
- The document has the correct `lang` attribute.
- Any content in another language has a local `lang` attribute.
- Content reads in a logical order without CSS.

## Color and Visual Design

- Normal text has at least 4.5:1 contrast against its background.
- Large text has at least 3:1 contrast against its background.
- Non-text UI elements and graphical state indicators have at least 3:1 contrast.
- Color is not the only way to communicate errors, success, selection, required fields, or status.
- Content remains readable and functional at 200% zoom.
- Content reflows at 320px width without horizontal scrolling except for genuinely two-dimensional content such as data tables.
- User-adjusted text spacing does not break content or controls.

## Keyboard and Navigation

- All functionality works with a keyboard.
- Focus never becomes trapped unless the user is inside a modal or equivalent controlled interaction, and an escape path exists.
- Every interactive element has a visible focus indicator.
- Focused elements are not hidden behind sticky headers, overlays, or bottom bars.
- A skip link or equivalent bypass mechanism exists for repeated navigation.
- Tab order follows the logical reading and interaction order.
- Single-character keyboard shortcuts can be disabled, remapped, or limited to focused contexts.
- Pointer targets meet WCAG target-size expectations, and important touch targets should follow the larger mobile guidance in `accessibility-mobile`.

## Forms

- Every form input has a visible, programmatically associated label.
- Required fields are identified without relying on color alone.
- Error messages are specific, visible, and available to assistive technology.
- Error suggestions are provided when possible.
- Inputs that collect personal data use appropriate `autocomplete` attributes.
- Legal, financial, account, or test submissions allow review, confirmation, or reversal when required.
- Authentication does not rely on inaccessible puzzles or memorization tasks without an accessible alternative.
- Previously entered information is reused when re-entry would otherwise be required.

## Links and Buttons

- Link text is meaningful on its own or in its immediate programmatic context.
- Identical link text does not point to different destinations unless context makes the difference clear.
- Buttons have descriptive accessible names.
- Links that open new tabs, download files, or trigger unusual behavior communicate that behavior.

## Page-Level Requirements

- Every page has a unique, descriptive `<title>`.
- Users have more than one way to find important pages when the site has multiple pages.
- Navigation appears in consistent locations and order.
- Components with the same function are consistently labeled.
- Help, contact, or support options are consistently placed when present.
- No content flashes more than three times per second.

## Motion and Dynamic Content

- Auto-moving, blinking, or scrolling content can be paused, stopped, or hidden.
- Orientation is not locked unless the use case requires it.
- Gesture interactions have single-pointer or keyboard alternatives.
- Device-motion interactions have control alternatives and can be disabled.
- Tooltips and popups can be dismissed, hovered, and focused without losing content unexpectedly.
- Drag-and-drop interactions have an accessible alternative.
- Status messages are announced with appropriate ARIA live regions without stealing focus.

## Code and Compatibility

- HTML is valid enough to preserve accessibility tree behavior.
- Custom components expose accurate name, role, state, and value.
- Native HTML controls are preferred over ARIA when they meet the need.
- Context changes do not happen automatically on focus.
- Form controls do not submit or navigate without deliberate user action.
- iframes and embedded content have descriptive `title` attributes.
- Accessibility checks include automated tooling and manual keyboard review.
