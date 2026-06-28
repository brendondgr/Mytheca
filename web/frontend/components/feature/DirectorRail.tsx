import { Eyebrow } from "@/components/ui/Eyebrow";
import type { Relationship, StatChip } from "@/features/story-player/scene-data";

function fmt(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

function chipColor(label: string, value: number): string {
  const l = label.toLowerCase();
  if (l.includes("trust") || l.includes("favour"))
    return value < 0 ? "var(--accent)" : "#1F8A5B";
  if (l.includes("suspicion") || l.includes("tension"))
    return value > 0 ? "var(--accent)" : "var(--ink-soft)";
  return "var(--ink-soft)";
}

export function TensionMeter({ pct, label }: { pct: number; label: string }) {
  return (
    <div>
      <div
        className="h-[9px] overflow-hidden rounded-[5px] bg-cardbd"
        role="progressbar"
        aria-label="Tension"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={label}
      >
        <div
          className="h-full transition-[width] duration-[400ms]"
          style={{ width: `${pct}%`, background: "linear-gradient(90deg,#C8862A,#8E2B1C)" }}
        />
      </div>
      <div className="mt-[6px] font-mono text-[9px] tracking-[0.06em] text-accent">{label}</div>
    </div>
  );
}

export function StateChips({ stats }: { stats: StatChip[] }) {
  if (stats.length === 0) return null;
  return (
    <div className="flex flex-col gap-[7px]">
      {stats.map((s) => (
        <div
          key={s.label}
          className="flex items-center justify-between rounded-[3px] border border-cardbd bg-card p-[8px_11px]"
        >
          <span className="font-body text-[13.5px] text-ink">{s.label}</span>
          <span className="font-mono text-[11px]" style={{ color: chipColor(s.label, s.value) }}>
            {fmt(s.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Relationships({ items }: { items: Relationship[] }) {
  return (
    <div className="flex flex-col gap-[6px]">
      {items.map((r, i) => (
        <p key={`${r.who}-${i}`} className="font-body text-[13px] leading-[1.4] text-ink-soft">
          <span className="font-semibold" style={{ color: r.color }}>
            {r.who}
          </span>{" "}
          {r.text}
        </p>
      ))}
    </div>
  );
}

/** Right rail: scenario goal · tension meter · scene-state chips · relationships. */
export function DirectorRail({
  goal,
  tension,
  tensionText,
  stats,
  relationships,
}: {
  goal: string;
  tension: number;
  tensionText: string;
  stats: StatChip[];
  relationships: Relationship[];
}) {
  return (
    <aside className="velora-rail hidden w-[248px] flex-none overflow-auto border-l border-hair-strong p-[18px_16px] lg:block">
      <Eyebrow size={9} tracking="0.16em" className="mb-[9px] block">
        Scene goal
      </Eyebrow>
      <p className="font-body text-[14px] leading-[1.45] text-ink italic">{goal}</p>

      <Eyebrow size={9} tracking="0.16em" className="mt-5 mb-[9px] block">
        Tension
      </Eyebrow>
      <TensionMeter pct={tension} label={tensionText} />

      <Eyebrow size={9} tracking="0.16em" className="mt-5 mb-[9px] block">
        Scene state
      </Eyebrow>
      <StateChips stats={stats} />

      <Eyebrow size={9} tracking="0.16em" className="mt-5 mb-[9px] block">
        Relationships
      </Eyebrow>
      <Relationships items={relationships} />
    </aside>
  );
}
