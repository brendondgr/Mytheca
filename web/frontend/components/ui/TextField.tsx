import { cn } from "@/lib/cn";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { FieldError } from "@/components/ui/FieldError";
import { useId, type ComponentPropsWithoutRef } from "react";

export type TextFieldProps = ComponentPropsWithoutRef<"input"> & {
  label?: string;
  /**
   * Validation message. Show it on blur, not on every keystroke.
   *
   * Passing this prop **at all** — including as an empty string or a
   * `string | undefined` state variable — opts the field into a reserved error
   * line, so a message can appear without pushing the next control down the
   * form. Fields that never validate omit the prop and gain no extra height.
   */
  error?: string;
};

/** Labeled single-line input. The label wraps the input for implicit association. */
export function TextField({ label, className, ...props }: TextFieldProps) {
  const errorId = useId();
  const reservesErrorLine = "error" in props;
  const { error, ...inputProps } = props;

  return (
    <label className={cn("block", className)}>
      {label ? <FieldLabel>{label}</FieldLabel> : null}
      <input
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cn(
          // text-body resolves from the --fs-* scale, so the user's Text-size
          // preference actually reaches the input.
          "w-full rounded-xs border bg-field px-md py-sm font-body text-body text-ink",
          "transition-[border-color] duration-fast ease-soft",
          "focus:border-accent focus:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-60",
          error ? "border-danger" : "border-field-bd",
        )}
        {...inputProps}
      />
      {reservesErrorLine ? <FieldError id={errorId}>{error}</FieldError> : null}
    </label>
  );
}
