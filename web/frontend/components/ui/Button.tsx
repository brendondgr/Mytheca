import { cn } from "@/lib/cn";
import { Spinner } from "@/components/ui/Spinner";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

/**
 * Hover changes two properties, never one (one reads as unfinished) and never
 * four (four reads as noisy). The lift itself comes from `.hover-lift`, which
 * is gated behind `@media (hover: hover) and (pointer: fine)` — without that
 * gate a touch device applies the hover on tap and it *sticks* until the user
 * taps elsewhere.
 */
const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-[#F6ECDA] border border-accent-hover hover:bg-accent-hover hover:shadow-[0_5px_14px_rgba(10,6,3,.3)]",
  secondary:
    "bg-card text-accent-ink border border-accent hover:bg-accent hover:text-[#F6ECDA] hover:shadow-[0_5px_14px_rgba(10,6,3,.25)]",
  ghost:
    "bg-transparent text-ink-soft border border-field-bd hover:bg-hover hover:text-ink hover:border-hair-strong",
};

/** Mono, uppercase action button — Begin / Send / Create / Submit / Cancel. */
export function Button({
  variant = "primary",
  className,
  type = "button",
  loading = false,
  loadingLabel,
  children,
  disabled,
  ...props
}: ComponentPropsWithoutRef<"button"> & {
  variant?: ButtonVariant;
  /**
   * Swap the label for a spinner **without changing the button's width**, so a
   * row of controls does not reflow the instant someone presses one. The label
   * stays in the DOM (merely invisible) and the spinner is overlaid on top of
   * it — measuring the text is what keeps the box the same size.
   */
  loading?: boolean;
  /**
   * What the button is doing, for assistive tech — e.g. "Saving character".
   * The visible label is hidden during the spin, so without this a screen
   * reader user is told only that a button is busy, not at what.
   */
  loadingLabel?: string;
  children?: ReactNode;
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      aria-label={loading ? loadingLabel : undefined}
      className={cn(
        "relative inline-flex cursor-pointer items-center justify-center rounded-xs px-lg py-sm font-mono text-ui uppercase tracking-[0.08em]",
        // 44px floor on touch only. On a mouse the button keeps the density the
        // design system specifies; see the note in styles/motion.css.
        "touch-target",
        "hover-lift press",
        VARIANT[variant],
        "disabled:cursor-not-allowed disabled:border-hair disabled:bg-hair disabled:text-mute2 disabled:shadow-none",
        className,
      )}
      {...props}
    >
      <span className={cn("inline-flex items-center gap-2", loading && "invisible")}>
        {children}
      </span>
      {loading ? (
        <span className="absolute inset-0 flex items-center justify-center">
          <Spinner size={14} />
        </span>
      ) : null}
    </button>
  );
}
