import { Eyebrow } from "@/components/ui/Eyebrow";

/**
 * A tab/section header: a Cinzel title, the manuscript "double rule"
 * (thin ink line over a hairline), and an optional mono sub-line.
 */
export function SectionHeader({
  title,
  sub,
  aside,
  size = 23,
  className,
}: {
  title: React.ReactNode;
  sub?: React.ReactNode;
  aside?: React.ReactNode;
  size?: number;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="flex items-baseline gap-3">
        <h2 className="font-display font-semibold text-ink" style={{ fontSize: size }}>
          {title}
        </h2>
        {aside}
      </div>
      <div className="mt-2 mb-1 h-[3px] border-t border-b border-t-ink border-b-hair-strong" />
      {sub ? (
        <Eyebrow size={10.5} tracking="0.06em" color="var(--mute)">
          {sub}
        </Eyebrow>
      ) : null}
    </div>
  );
}
