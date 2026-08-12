import { cn } from "@/lib/cn";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { FieldError } from "@/components/ui/FieldError";
import { useId, type ComponentPropsWithoutRef } from "react";

export type TextAreaProps = ComponentPropsWithoutRef<"textarea"> & {
  label?: string;
  /**
   * Validation message. Show it on blur, not on every keystroke.
   *
   * Passing this prop **at all** opts the field into a reserved error line, so
   * a message can appear without shifting the control below it. See
   * `TextField` for the full note.
   */
  error?: string;
};

/** Labeled multi-line input. */
export function TextArea({ label, className, rows = 3, ...props }: TextAreaProps) {
  const errorId = useId();
  const reservesErrorLine = "error" in props;
  const { error, ...textareaProps } = props;

  return (
    <label className={cn("block", className)}>
      {label ? <FieldLabel>{label}</FieldLabel> : null}
      <textarea
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cn(
          "w-full resize-y rounded-[2px] border bg-field px-[11px] py-[8px] font-body text-body leading-[1.5] text-ink",
          "transition-[border-color] duration-fast ease-soft",
          "focus:border-accent focus:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-60",
          error ? "border-danger" : "border-field-bd",
        )}
        {...textareaProps}
      />
      {reservesErrorLine ? <FieldError id={errorId}>{error}</FieldError> : null}
    </label>
  );
}
