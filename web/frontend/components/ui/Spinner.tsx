import { cn } from "@/lib/cn";

/**
 * The one spinner in the app. A ring of `currentColor` with a transparent
 * quadrant, so it inherits whatever it sits in and needs no per-theme variant.
 *
 * Under reduced motion the app-wide rule in `themes.css` strips the rotation;
 * the ring itself is a static border, so what remains is a calm circle rather
 * than an empty box — the same "resting state lives in the base style" idiom as
 * `.mytheca-glow` and `.skeleton`.
 *
 * Decorative by default (`aria-hidden`): a spinner announces nothing useful on
 * its own, and every call site pairs it with real text or `aria-busy` on the
 * container it is standing in for.
 */
export function Spinner({
  size = 16,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block shrink-0 rounded-full border-2 border-current border-t-transparent align-middle",
        "animate-[embSpin_1s_linear_infinite] motion-reduce:animate-none",
        className,
      )}
      style={{ width: size, height: size }}
    />
  );
}
