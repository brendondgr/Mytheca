import { cn } from "@/lib/cn";

/**
 * Mono, uppercase, letter-spaced micro-label — the recurring "eyebrow" used for
 * section kickers, role tags, counts, "Narrator"/"You" labels, field labels.
 *
 * Two of this component's props used to be the app's largest source of
 * accessibility findings, and both are now constrained rather than free:
 *
 *  - `color` accepted any string, and callers passed raw entity colours
 *    (`c.color`) and literal hexes (`#A8762A`, `#1F8A82`) straight into an
 *    inline style. Those are chosen for identity and are theme-independent, so
 *    they cannot clear 4.5:1 against both a cream ground and a near-black one —
 *    measured at 3.11:1, 3.61:1 and 4.08:1 in the baseline audit. Pass
 *    `entity` instead: it routes the colour through the theme-aware recipe in
 *    themes.css. `color` remains for theme TOKENS (`var(--mute2)`), which are
 *    already gated.
 *  - `size` accepted any number, and callers passed 8 and 9.5. Numeric sizes are
 *    now clamped to the 11px caption floor; below that a label stops being small
 *    and starts being unreadable.
 */

/** The caption floor, in px. Mirrors --fs-tag / --fs-eyebrow in themes.css. */
const MIN_SIZE = 11;

export function Eyebrow({
  children,
  size = "var(--fs-eyebrow)",
  tracking = "0.16em",
  color,
  entity,
  className,
  id,
}: {
  children: React.ReactNode;
  size?: number | string;
  tracking?: string;
  /** A theme TOKEN, e.g. `var(--mute2)`. For an entity's own colour use `entity`. */
  color?: string;
  /**
   * An entity's identity colour — a character's, a seal's, a graph type's.
   * Mixed toward the theme's ink so it stays legible in all three themes while
   * keeping its hue. See `--entity-ink` in styles/themes.css.
   */
  entity?: string;
  className?: string;
  /** Set when a section uses this eyebrow as its `aria-labelledby` target. */
  id?: string;
}) {
  const resolved = typeof size === "number" ? Math.max(MIN_SIZE, size) : size;
  return (
    <span
      id={id}
      className={cn("font-mono uppercase", entity && "text-entity", className)}
      style={{
        fontSize: resolved,
        letterSpacing: tracking,
        ...(entity ? { ["--entity" as string]: entity } : { color: color ?? "var(--mute2)" }),
      }}
    >
      {children}
    </span>
  );
}
