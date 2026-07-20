import { cn } from "@/lib/cn";
import type { ComponentPropsWithoutRef } from "react";

type IconButtonVariant = "card" | "field";

const VARIANT: Record<IconButtonVariant, string> = {
  card: "border border-cardbd bg-card2 text-mute2 hover:border-accent hover:bg-accent hover:text-[#F6ECDA]",
  field:
    "border border-field-bd bg-field text-accent hover:border-accent hover:bg-hover",
};

/** Small square icon button (edit ✎, delete ×, roll die). `label` is required
 * for an accessible name since the content is a glyph. */
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
        VARIANT[variant],
        className,
      )}
      style={{ width: size, height: size }}
      {...props}
    />
  );
}
