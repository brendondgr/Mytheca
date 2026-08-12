import { cn } from "@/lib/cn";

/**
 * Animated three-dot "still working" indicator.
 *
 * Uses the `embDots` keyframe from `themes.css`. The app-wide `.mytheca-themed *`
 * reduced-motion rule strips `animation` globally, so the dots must read as something
 * even when they are frozen — each dot carries an explicit non-zero opacity as its base
 * style, leaving three visible dots rather than an invisible gap. That is why no separate
 * `prefers-reduced-motion` media query is needed here.
 *
 * Decorative (`aria-hidden`): every call site pairs it with a text label that says the same
 * thing, so announcing it too would be noise.
 */
export function TypingDots({
  size = 4,
  className,
}: {
  /** Dot diameter in px. */
  size?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn("inline-flex items-center gap-[2px]", className)}
      data-testid="typing-dots"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="inline-block rounded-full bg-current"
          style={{
            width: size,
            height: size,
            opacity: 0.5,
            animation: `embDots 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </span>
  );
}
