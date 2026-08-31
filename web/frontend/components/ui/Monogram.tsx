import { cn } from "@/lib/cn";

/**
 * Wax-seal monogram avatar: a parchment circle with the character's color as
 * ring + initials. Decorative by default (`aria-hidden`) since the name is
 * shown alongside; wrap it in a button at the call site when it's interactive.
 *
 * The RING keeps the character's colour exactly — it is a non-text mark and only
 * has to clear 3:1. The INITIALS do not: bold 10-13px of a character colour on
 * the fixed parchment ground measured 3.11:1 and 3.86:1 in the baseline audit.
 *
 * They get their own recipe rather than the app-wide `--entity-ink`, and this is
 * the one place that is right: `--entity-ink` mixes toward the THEME's ink,
 * which is light on Ember and Slate, while the monogram's ground is a fixed
 * cream in every theme. Mixing toward the theme ink there would make it worse.
 * 60% is the highest hue retention that clears 4.5:1 against #EDE3CD across the
 * whole built-in entity palette.
 *
 * When `src` is given (a generated character portrait), the same colored ring
 * frames the image instead of the initials — so every avatar call-site upgrades
 * to a portrait automatically once one exists, with the monogram as the fallback.
 */
/** The parchment ground, in every theme. */
const MONOGRAM_BG = "#EDE3CD";
/** Toward this, and by this much, so the initials stay legible on that ground. */
const MONOGRAM_INK = "#241b10";
const MONOGRAM_INK_MIX = 60;

export function Monogram({
  mono,
  color,
  size = 46,
  ring = 2,
  bg = MONOGRAM_BG,
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
        color:
          bg === MONOGRAM_BG
            ? `color-mix(in oklab, ${color} ${MONOGRAM_INK_MIX}%, ${MONOGRAM_INK})`
            : color,
        fontSize: fontSize ?? Math.round(size * 0.37),
      }}
    >
      {mono}
    </span>
  );
}
