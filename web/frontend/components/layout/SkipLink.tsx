/**
 * Skip to content.
 *
 * The baseline audit measured zero skip links across all seven routes, so a
 * keyboard user tabbed the whole header — brand, storyline switcher, search,
 * Create, Options — on every single navigation before reaching anything they
 * came for.
 *
 * Two details are the whole reason this works:
 *
 *  - It is VISIBLE ON FOCUS, not hidden with `display: none`. A skip link that
 *    is `display: none` is removed from the tab order entirely, which is the
 *    most common way this control is shipped broken.
 *  - It targets `#main`, which `Page` renders with `tabIndex={-1}`. Without the
 *    negative tabindex the browser moves the scroll position but not focus, so
 *    the next Tab restarts at the top of the header — the exact thing the link
 *    exists to avoid.
 *
 * `sr-only` here is Mytheca's `position: fixed` override (see globals.css), not
 * Tailwind's stock absolute one; `focus:not-sr-only` cannot be used to reveal it
 * because that utility loses to the unlayered override, so the visible state is
 * spelled out by hand instead.
 */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only z-50 focus-visible:top-sm focus-visible:left-sm focus-visible:m-0 focus-visible:h-auto focus-visible:w-auto focus-visible:overflow-visible focus-visible:rounded-xs focus-visible:border focus-visible:border-accent focus-visible:bg-menu focus-visible:px-md focus-visible:py-sm focus-visible:font-mono focus-visible:text-ui focus-visible:tracking-[0.08em] focus-visible:text-ink focus-visible:uppercase focus-visible:whitespace-nowrap focus-visible:shadow-lg"
    >
      Skip to content
    </a>
  );
}
