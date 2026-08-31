import { cn } from "@/lib/cn";

/**
 * Inline validation message for a form field.
 *
 * The wrapper is always in the DOM with a reserved single-line box, so an error
 * appearing does **not** push the next field down the form — the shift is what
 * makes inline validation feel broken, because it moves the control the user is
 * about to reach. Only the message's opacity and a 2px rise are animated; both
 * are compositor-friendly, and the height never changes.
 *
 * `role="alert"` is on the message itself rather than the reserved box, so an
 * empty slot announces nothing.
 */
export function FieldError({
  children,
  id,
  className,
}: {
  children?: React.ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <span
      aria-hidden={children ? undefined : true}
      className={cn("block min-h-[1.15rem] pt-3xs", className)}
    >
      {children ? (
        <span
          id={id}
          role="alert"
          className="content-enter block font-mono text-eyebrow leading-[1.15rem] tracking-[0.08em] text-danger-ink"
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}
