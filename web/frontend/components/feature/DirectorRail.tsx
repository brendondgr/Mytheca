import { Eyebrow } from "@/components/ui/Eyebrow";
import type { StatDefinition } from "@/lib/types";
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

/** The band label whose range contains `value` (the storyline's stat "tickers"). */
function bandFor(def: StatDefinition, value: number): string | null {
  const band = def.bands.find((b) => value >= b.min && value <= b.max);
  return band?.label ?? null;
}

/**
 * The storyline's universal stat schema (definitions + labeled bands) — the same
 * stats the Library/world editor define. Shown read-only at their default values
 * so the scene carries the world's real stat vocabulary; live deltas live in the
 * Scene-state chips below. Hidden/non-public stats are omitted.
 */
export function StatSchema({ defs }: { defs: StatDefinition[] }) {
  const visible = defs.filter((d) => d.visibility === "public");
  if (visible.length === 0) return null;
  return (
    <div className="flex flex-col gap-[7px]">
      {visible.map((d) => {
        const band = bandFor(d, d.default);
        return (
          <div
            key={d.key}
            className="rounded-[3px] border border-cardbd bg-card p-[8px_11px]"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-body text-[13.5px] text-ink">{d.displayName}</span>
              <span className="font-mono text-[11px] text-accent">
                {d.default}
                <span className="text-mute2">{` / ${d.min}–${d.max}`}</span>
              </span>
            </div>
            {band ? (
              <div className="mt-[3px] font-mono text-[9px] tracking-[0.08em] text-mute uppercase">
                {band}
              </div>
            ) : null}
          </div>
        );
      })}
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
  statDefs,
  stats,
  relationships,
}: {
  goal: string;
  tension: number;
  tensionText: string;
  statDefs: StatDefinition[];
  stats: StatChip[];
  relationships: Relationship[];
}) {
  return (
    <aside className="velora-rail hidden w-[248px] flex-none overflow-auto border-l border-hair-strong p-[18px_16px] lg:block">
      <Eyebrow tracking="0.16em" className="mb-[9px] block">
        Scene goal
      </Eyebrow>
      <p className="font-body text-[14px] leading-[1.45] text-ink italic">{goal}</p>

      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Tension
      </Eyebrow>
      <TensionMeter pct={tension} label={tensionText} />

      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Character stats
      </Eyebrow>
      <StatSchema defs={statDefs} />

      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Scene state
      </Eyebrow>
      <StateChips stats={stats} />

      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Relationships
      </Eyebrow>
      <Relationships items={relationships} />
    </aside>
  );
}
