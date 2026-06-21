import { cn } from "@/lib/cn";
import { FieldLabel } from "@/components/ui/FieldLabel";
import type { ComponentPropsWithoutRef } from "react";

/** Labeled multi-line input. */
export function TextArea({
  label,
  className,
  rows = 3,
  ...props
}: ComponentPropsWithoutRef<"textarea"> & { label?: string }) {
  return (
    <label className={cn("block", className)}>
      {label ? <FieldLabel>{label}</FieldLabel> : null}
      <textarea
        rows={rows}
        className="w-full resize-y rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] leading-[1.5] text-ink focus:border-accent focus:outline-none"
        {...props}
      />
    </label>
  );
}
