import { cn } from "@/lib/cn";

/** Static pill (non-interactive) — e.g. an assembled-cast chip in the dossier. */
export function Chip({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-cardbd bg-card px-3 py-[5px]",
        className,
      )}
    >
      {children}
    </span>
  );
}
