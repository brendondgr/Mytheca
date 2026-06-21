import { cn } from "@/lib/cn";

/**
 * Wax-seal monogram avatar: a parchment circle with the character's color as
 * ring + initials. Decorative by default (`aria-hidden`) since the name is
 * shown alongside; wrap it in a button at the call site when it's interactive.
 */
export function Monogram({
  mono,
  color,
  size = 46,
  ring = 2,
  bg = "#EDE3CD",
  fontSize,
  className,
}: {
  mono: string;
  color: string;
  size?: number;
  ring?: number;
  bg?: string;
  fontSize?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex flex-none items-center justify-center rounded-full font-display font-bold leading-none",
        className,
      )}
      style={{
        width: size,
        height: size,
        background: bg,
        border: `${ring}px solid ${color}`,
        color,
        fontSize: fontSize ?? Math.round(size * 0.37),
      }}
    >
      {mono}
    </span>
  );
}
