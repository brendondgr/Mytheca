import { cn } from "@/lib/cn";
import { FieldLabel } from "@/components/ui/FieldLabel";
import type { ComponentPropsWithoutRef } from "react";

/** Labeled single-line input. The label wraps the input for implicit association. */
export function TextField({
  label,
  className,
  ...props
}: ComponentPropsWithoutRef<"input"> & { label?: string }) {
  return (
    <label className={cn("block", className)}>
      {label ? <FieldLabel>{label}</FieldLabel> : null}
      <input
        className="w-full rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
        {...props}
      />
    </label>
  );
}
