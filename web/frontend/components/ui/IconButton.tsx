import { cn } from "@/lib/cn";
import type { ComponentPropsWithoutRef } from "react";

type IconButtonVariant = "card" | "field";

/** Hover is scoped with `enabled:` so a disabled control never lights up under
 * the cursor — a button that reacts but does nothing is worse than one that
 * stays quiet. */
const VARIANT: Record<IconButtonVariant, string> = {
  card: "border border-cardbd bg-card2 text-mute2 enabled:hover:border-accent enabled:hover:bg-accent enabled:hover:text-[#F6ECDA]",
  field:
    "border border-field-bd bg-field text-accent enabled:hover:border-accent enabled:hover:bg-hover",
};

/** Small square icon button (edit ✎, delete ×, roll die). `label` is required
 * for an accessible name since the content is a glyph.
 *
 * At its 24px default it is well under the 44px touch floor, but it lives in
 * dense card corners and rail rows where it cannot grow. `.touch-target-overlay`
 * projects a 44x44 hit area from its centre on coarse pointers only, so the
 * visual size is untouched and desktop density is preserved. */
export function IconButton({
  label,
  size = 24,
  variant = "card",
  className,
  type = "button",
  ...props
}: ComponentPropsWithoutRef<"button"> & {
  label: string;
  size?: number;
  variant?: IconButtonVariant;
}) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex cursor-pointer items-center justify-center rounded-[3px] leading-none",
        "touch-target-overlay press",
        VARIANT[variant],
        "disabled:cursor-not-allowed disabled:opacity-45",
        className,
      )}
      style={{ width: size, height: size }}
      {...props}
    />
  );
}
