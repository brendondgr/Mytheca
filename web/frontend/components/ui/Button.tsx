import { cn } from "@/lib/cn";
import type { ComponentPropsWithoutRef } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-accent text-[#F6ECDA] border border-accent hover:brightness-[1.08]",
  secondary:
    "bg-card text-accent border border-accent hover:bg-accent hover:text-[#F6ECDA]",
  ghost: "bg-transparent text-ink-soft border border-field-bd hover:bg-card",
};

/** Mono, uppercase action button — Begin / Send / Create / Submit / Cancel. */
export function Button({
  variant = "primary",
  className,
  type = "button",
  ...props
}: ComponentPropsWithoutRef<"button"> & { variant?: ButtonVariant }) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex cursor-pointer items-center justify-center rounded-[2px] px-[18px] py-[10px] font-mono text-[11px] uppercase tracking-[0.08em]",
        VARIANT[variant],
        "disabled:cursor-not-allowed disabled:border-hair disabled:bg-hair disabled:text-mute2",
        className,
      )}
      {...props}
    />
  );
}
