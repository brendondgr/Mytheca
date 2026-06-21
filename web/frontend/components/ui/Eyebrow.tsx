import { cn } from "@/lib/cn";

/**
 * Mono, uppercase, letter-spaced micro-label — the recurring "eyebrow" used for
 * section kickers, role tags, counts, "Narrator"/"You" labels, field labels.
 * Size/tracking/color are props (inline style) so they never clash with the
 * caller's Tailwind classes.
 */
export function Eyebrow({
  children,
  size = 10,
  tracking = "0.16em",
  color = "var(--mute2)",
  className,
}: {
  children: React.ReactNode;
  size?: number;
  tracking?: string;
  color?: string;
  className?: string;
}) {
  return (
    <span
      className={cn("font-mono uppercase", className)}
      style={{ fontSize: size, letterSpacing: tracking, color }}
    >
      {children}
    </span>
  );
}
