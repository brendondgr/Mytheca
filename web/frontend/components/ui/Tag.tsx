import { cn } from "@/lib/cn";

type TagVariant = "fill" | "outline";
type TagTone = "gold" | "accent" | "neutral";

const FILL: Record<TagTone, string> = {
  gold: "bg-gold text-[#1f160c]",
  accent: "bg-accent text-[#F6ECDA]",
  neutral: "bg-field text-ink-soft",
};

const OUTLINE: Record<TagTone, string> = {
  gold: "border border-gold-soft text-gold-soft-ink",
  accent: "border border-accent text-accent-ink",
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
        "inline-flex items-center px-sm py-3xs font-mono text-tag uppercase tracking-[0.1em] whitespace-nowrap",
        pill ? "rounded-full" : "rounded-xs",
        variant === "fill" ? FILL[tone] : OUTLINE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
