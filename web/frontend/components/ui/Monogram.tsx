import { cn } from "@/lib/cn";

/**
 * Wax-seal monogram avatar: a parchment circle with the character's color as
 * ring + initials. Decorative by default (`aria-hidden`) since the name is
 * shown alongside; wrap it in a button at the call site when it's interactive.
 *
 * When `src` is given (a generated character portrait), the same colored ring
 * frames the image instead of the initials — so every avatar call-site upgrades
 * to a portrait automatically once one exists, with the monogram as the fallback.
 */
export function Monogram({
  mono,
  color,
  size = 46,
  ring = 2,
  bg = "#EDE3CD",
  fontSize,
  className,
  src,
  alt,
}: {
  mono: string;
  color: string;
  size?: number;
  ring?: number;
  bg?: string;
  fontSize?: number;
  className?: string;
  /** Optional portrait image URL; falls back to the initials when absent. */
  src?: string | null;
  /** Alt text when `src` is set; omit to keep the avatar decorative. */
  alt?: string;
}) {
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- generated avatar from our media mount
      <img
        src={src}
        alt={alt ?? ""}
        aria-hidden={alt ? undefined : true}
        className={cn("inline-block flex-none rounded-full object-cover", className)}
        style={{ width: size, height: size, background: bg, border: `${ring}px solid ${color}` }}
      />
    );
  }
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
