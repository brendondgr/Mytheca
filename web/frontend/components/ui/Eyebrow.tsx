import { cn } from "@/lib/cn";

/**
 * Mono, uppercase, letter-spaced micro-label — the recurring "eyebrow" used for
 * section kickers, role tags, counts, "Narrator"/"You" labels, field labels.
 * Size/tracking/color are props (inline style) so they never clash with the
 * caller's Tailwind classes.
 *
 * Default size is `var(--fs-eyebrow)` — scales with the user's chosen font-size
 * preset from the Appearance settings. Pass an explicit px number only when a
 * caller intentionally wants a size outside the shared scale.
 */
export function Eyebrow({
  children,
  size = "var(--fs-eyebrow)",
  tracking = "0.16em",
  color = "var(--mute2)",
  className,
  id,
}: {
  children: React.ReactNode;
  size?: number | string;
  tracking?: string;
  color?: string;
  className?: string;
  /** Set when a section uses this eyebrow as its `aria-labelledby` target. */
  id?: string;
}) {
  return (
    <span
      id={id}
      className={cn("font-mono uppercase", className)}
      style={{ fontSize: size, letterSpacing: tracking, color }}
    >
      {children}
    </span>
  );
}
