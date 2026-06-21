import { cn } from "@/lib/cn";
import { Eyebrow } from "@/components/ui/Eyebrow";

/** Gold mono field label (also used for grouped controls like cast pickers). */
export function FieldLabel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("mb-[5px] block", className)}>
      <Eyebrow size={9} tracking="0.14em" color="#A8762A">
        {children}
      </Eyebrow>
    </span>
  );
}
