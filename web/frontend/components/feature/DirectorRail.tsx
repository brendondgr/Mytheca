"use client";

import { useState } from "react";
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

/** The labeled band whose range contains `value` (e.g. 50 → "Charged"). */
function bandLabelFor(def: StatDefinition): string | null {
  const b = def.bands.find((x) => def.default >= x.min && def.default <= x.max);
  return b?.label ?? null;
}

/**
 * One stat as a min→max slider: the stat name with its current band title beside
 * it (e.g. "Essence: Charged"), a numeric readout floating above the value's
 * position on the track, a filled track with a thumb, and the min/max end ticks.
 * The band legend below opens only when the "?" is hovered or clicked. Read-only
 * (the value sits at the schema default) — it visualizes the stat, not edits it.
 */
function StatSlider({ def }: { def: StatDefinition }) {
  const { min, max, default: value, displayName, bands } = def;
  const span = max - min;
  const pct = span > 0 ? ((value - min) / span) * 100 : 0;
  // Keep the floating readout from clipping at the track ends.
  const labelPct = Math.max(7, Math.min(93, pct));
  const hasBands = bands.length > 0;
  const currentBand = bandLabelFor(def);
  const [pinned, setPinned] = useState(false);
  const [hovered, setHovered] = useState(false);
  const open = pinned || hovered;

  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate font-body text-[13px] text-ink">
          {displayName}
          {currentBand ? (
            <span style={{ color: "var(--accent)" }}>: {currentBand}</span>
          ) : null}
        </span>
        {hasBands ? (
          <button
            type="button"
            aria-expanded={open}
            aria-label={`What ${displayName} ranges mean`}
            onClick={() => setPinned((p) => !p)}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            onFocus={() => setHovered(true)}
            onBlur={() => setHovered(false)}
            className="flex h-[15px] w-[15px] flex-none cursor-pointer items-center justify-center rounded-full border border-cardbd font-mono text-[9px] leading-none text-mute hover:border-accent hover:text-accent focus:border-accent focus:text-accent focus:outline-none aria-expanded:border-accent aria-expanded:text-accent"
          >
            ?
          </button>
        ) : null}
      </div>

      {/* Floating value readout, centered over the thumb (sits above the track). */}
      <div className="relative mt-[3px] h-[17px]">
        <span
          className="absolute top-0 -translate-x-1/2 font-mono text-[12px] font-medium text-accent"
          style={{ left: `${labelPct}%` }}
        >
          {value}
        </span>
      </div>

      {/* Track + fill + thumb. */}
      <div className="relative h-[6px] rounded-full bg-cardbd">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pct}%`, background: "linear-gradient(90deg,#C8862A,#8E2B1C)" }}
        />
        <span
          aria-hidden
          className="absolute top-1/2 h-[12px] w-[12px] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-card"
          style={{ left: `${pct}%` }}
        />
      </div>

      <div className="mt-[4px] flex justify-between font-mono text-[8.5px] text-mute2">
        <span>{min}</span>
        <span>{max}</span>
      </div>

      {/* Band legend — opens only via the "?" (hover or click); in-flow, never clipped. */}
      {hasBands ? (
        <div
          className={`grid transition-[grid-template-rows] duration-200 motion-reduce:transition-none ${
            open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          }`}
        >
          <div className="overflow-hidden">
            <dl className="mt-[7px] rounded-[3px] border border-cardbd bg-card2 p-[7px_9px]">
              {bands.map((b) => (
                <div key={b.label} className="flex items-baseline justify-between gap-[10px] py-[2px]">
                  <dt className="flex-none font-mono text-[9.5px] text-mute2">
                    {b.min}–{b.max}
                  </dt>
                  <dd className="text-right font-body text-[11.5px] leading-[1.3] text-ink-soft">
                    {b.label}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The storyline's universal stat schema (definitions + labeled bands) — the same
 * stats the Library/world editor define. Each renders as a min→max slider at its
 * default value with a hover "?" that explains its band ranges; live deltas live
 * in the Scene-state chips below. Hidden/non-public stats are omitted.
 */
export function StatSchema({ defs }: { defs: StatDefinition[] }) {
  const visible = defs.filter((d) => d.visibility === "public");
  if (visible.length === 0) return null;
  return (
    <div className="flex flex-col gap-[16px]">
      {visible.map((d) => (
        <StatSlider key={d.key} def={d} />
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
