import { cn } from "@/lib/cn";

type TagVariant = "fill" | "outline";
type TagTone = "gold" | "accent" | "neutral";

const FILL: Record<TagTone, string> = {
  gold: "bg-gold text-[#1f160c]",
  accent: "bg-accent text-[#F6ECDA]",
  neutral: "bg-field text-ink-soft",
};

const OUTLINE: Record<TagTone, string> = {
  gold: "border border-gold-soft text-gold-soft",
  accent: "border border-accent text-accent",
  neutral: "border border-field-bd text-ink-soft",
};

/** Small mono pill: genre/tone tags, the "Recent" badge, event-type labels. */
export function Tag({
  children,
  variant = "fill",
  tone = "gold",
  pill = false,
  className,
}: {
  children: React.ReactNode;
  variant?: TagVariant;
  tone?: TagTone;
  pill?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-[9px] py-[3px] font-mono text-[9.5px] uppercase tracking-[0.1em] whitespace-nowrap",
        pill ? "rounded-full" : "rounded-[2px]",
        variant === "fill" ? FILL[tone] : OUTLINE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
