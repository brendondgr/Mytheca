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
    <span className={cn("mb-[6px] block", className)}>
      <Eyebrow size={11} tracking="0.12em" color="#A8762A" className="font-bold">
        {children}
      </Eyebrow>
    </span>
  );
}
