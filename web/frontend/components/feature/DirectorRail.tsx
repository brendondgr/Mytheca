"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ENTER_TRANSITION } from "@/lib/motion";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { DirectionChecklist } from "@/components/feature/DirectionChecklist";
import type { StandingItem } from "@/lib/events";
import { NO_DIRECTION, type DirectionProgress } from "@/features/story-player/turn-stream";
import type { StatDefinition } from "@/lib/types";
import type { Relationship, StatChip } from "@/features/story-player/scene-data";
import type { ActivityEntry } from "@/features/story-player/turn-stream";

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
        {/* scaleX, not width: `width` is a layout property, so animating it
            re-runs layout on every frame of the fill. A transform runs on the
            compositor. The bar is drawn at full width and squeezed from the
            left, which is why the gradient is sized to the track. */}
        <div
          className="h-full w-full origin-left transition-transform duration-base ease-out"
          style={{
            transform: `scaleX(${pct / 100})`,
            background: "linear-gradient(90deg,#C8862A,#8E2B1C)",
          }}
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
          title={s.reason || undefined}
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
function bandLabelFor(def: StatDefinition, value: number): string | null {
  const b = def.bands.find((x) => value >= x.min && value <= x.max);
  return b?.label ?? null;
}

/**
 * One stat as a min→max slider: the stat name with its current band title beside
 * it (e.g. "Essence: Charged"), a numeric readout floating above the value's
 * position on the track, a filled track with a thumb, and the min/max end ticks.
 * The band legend below opens only when the "?" is hovered or clicked. Read-only —
 * it visualizes the stat, not edits it. `value` is the live per-character value when
 * given (the dossier), falling back to the schema default (the rail's legend).
 */
function StatSlider({ def, value: live }: { def: StatDefinition; value?: number }) {
  const { min, max, displayName, bands } = def;
  const value = live ?? def.default;
  const span = max - min;
  const pct = span > 0 ? ((value - min) / span) * 100 : 0;
  // Keep the floating readout from clipping at the track ends.
  const labelPct = Math.max(7, Math.min(93, pct));
  const hasBands = bands.length > 0;
  const currentBand = bandLabelFor(def, value);
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
          className={`grid transition-[grid-template-rows] duration-base ease-out motion-reduce:transition-none ${
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

/** Live value for a stat def from a per-character chip list (match on key/label). Exported
 * so other per-character stat surfaces (e.g. the cast rail) share this exact matching. */
export function liveValueFor(def: StatDefinition, values?: StatChip[]): number | undefined {
  if (!values) return undefined;
  const key = def.key.toLowerCase();
  const chip = values.find((c) => c.label.toLowerCase() === key);
  return chip?.value;
}

/**
 * The storyline's universal stat schema (definitions + labeled bands) — the same
 * stats the Library/world editor define. Each renders as a min→max slider with a hover
 * "?" that explains its band ranges. When `values` is given (the character dossier), each
 * slider shows that character's LIVE stat value; without it (the Director rail) sliders
 * sit at the schema default as a legend. Hidden/non-public stats are omitted.
 */
export function StatSchema({ defs, values }: { defs: StatDefinition[]; values?: StatChip[] }) {
  const visible = defs.filter((d) => d.visibility === "public");
  if (visible.length === 0) return null;
  return (
    <div className="flex flex-col gap-[16px]">
      {visible.map((d) => (
        <StatSlider key={d.key} def={d} value={liveValueFor(d, values)} />
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

/** Icon prefix for each activity kind (single char — purely decorative, aria-hidden). */
function kindIcon(kind: ActivityEntry["kind"]): string {
  switch (kind) {
    case "thinking": return "…";
    case "speaking": return "◆";
    case "action": return "↳";
    case "narration": return "◇";
    case "stat": return "▲";
    case "presence": return "●";
    case "plan": return "⟳";
    case "branch": return "⑂";
  }
}

/** Drop the leading subject (characterId or resolved name) from an activity label. */
function stripSubject(label: string, who: string, name: string): string {
  if (label.startsWith(who)) return label.slice(who.length).trimStart();
  if (label.startsWith(name)) return label.slice(name.length).trimStart();
  return label;
}

/**
 * The live "scene pulse" feed: a scrollable `role="log"` region that shows the 12 most
 * recent activity entries streamed from the turn engine. Each entry shows the character
 * name (in their colour) when `who` resolves via `charById`, the action label, and an
 * optional muted detail line. Entries animate in with the transcript's standard entrance.
 * Empty state: a quiet italic prompt.
 */
function ScenePulse({
  activity,
  charById,
  live = true,
}: {
  activity: ActivityEntry[];
  charById?: (id: string) => { name: string; color: string } | undefined;
  /**
   * Whether this feed announces. `false` for a surface that is mounted only while it is
   * open: a log that appears and immediately reads out twelve entries the player already
   * scrolled past is worse than silence. The `role="log"` and the label stay either way, so
   * the region is still navigable — it just stops interrupting.
   */
  live?: boolean;
}) {
  return (
    <div
      role="log"
      aria-live={live ? "polite" : "off"}
      aria-label="Scene pulse"
      className="max-h-[52dvh] overflow-y-auto"
    >
      {activity.length === 0 ? (
        <p className="font-body text-[12px] italic text-ink-soft">
          The scene is quiet — your move.
        </p>
      ) : (
        <div className="flex flex-col gap-[6px]">
          {activity.map((entry) => {
            const char = entry.who ? charById?.(entry.who) : undefined;
            return (
              <motion.div
                key={entry.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={ENTER_TRANSITION}
              >
                <div className="rounded-[3px] border border-cardbd bg-card p-[6px_9px]">
                  <div className="flex items-baseline gap-[5px]">
                    <span aria-hidden className="flex-none font-mono text-[9px] text-mute2">
                      {kindIcon(entry.kind)}
                    </span>
                    {char ? (
                      <span
                        className="flex-none font-display text-[12px] font-semibold leading-[1.2]"
                        style={{ color: char.color }}
                      >
                        {char.name}
                      </span>
                    ) : null}
                    <span className="min-w-0 font-body text-[12px] leading-[1.3] text-ink">
                      {/* Labels lead with their subject — the raw characterId for event-derived
                          entries ("abc123 speaks") but the display name for trace-derived ones
                          ("Maerin is about to speak"). Strip whichever prefixes the label so the
                          colored name span never shows the subject twice. */}
                      {char && entry.who
                        ? stripSubject(entry.label, entry.who, char.name)
                        : entry.label}
                    </span>
                  </div>
                  {entry.detail ? (
                    <p className="mt-[2px] font-body text-[11px] leading-[1.3] text-ink-soft pl-[14px]">
                      {entry.detail}
                    </p>
                  ) : null}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Right rail: live "Scene pulse" activity feed · scene-state chips. The Scene Goal,
 * Tension meter, and Relationships sections have been replaced by the live feed; those
 * data streams now belong to the CharacterDossier (relationships) and the cast rail
 * (per-character stats). `charById` resolves a characterId to a name+color for the feed.
 */
export interface DirectorRailProps {
  stats: StatChip[];
  activity?: ActivityEntry[];
  charById?: (id: string) => { name: string; color: string } | undefined;
  /** The player's scene direction and how much of it the turn has delivered. */
  direction?: DirectionProgress;
  /** What an earlier turn could not deliver, and the next one will re-owe. */
  standing?: StandingItem[];
  /** Stop asking for one carried-over item (`null` → all). Omit to hide the control. */
  onDismissStanding?: (itemId: string | null) => void;
  /**
   * Whether the two live regions in here announce. The always-mounted desktop rail leaves it
   * `true`; a bottom sheet that exists only while it is open passes `false` — see
   * {@link ScenePulse}.
   */
  live?: boolean;
}

/**
 * The director rail's contents, with no container of its own — wrapped by {@link DirectorRail}
 * on desktop and by a bottom sheet below `lg`, so neither width can drift from the other.
 */
export function DirectorRailContent({
  stats,
  activity = [],
  charById,
  direction = NO_DIRECTION,
  standing = [],
  onDismissStanding,
  live = true,
}: DirectorRailProps) {
  return (
    <>
      <Eyebrow tracking="0.16em" className="mb-[9px] block">
        Scene pulse
      </Eyebrow>
      <ScenePulse activity={activity} charById={charById} live={live} />

      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Scene state
      </Eyebrow>
      <StateChips stats={stats} />

      <DirectionChecklist
        progress={direction}
        standing={standing}
        onDismiss={onDismissStanding}
        live={live}
      />
    </>
  );
}

/**
 * The desktop shell: the `lg`-only right rail. Named, because an unnamed `<aside>` is
 * indistinguishable from the cast rail in a landmark list.
 */
export function DirectorRail(props: DirectorRailProps) {
  return (
    <aside
      aria-label="Scene"
      className="mytheca-rail hidden w-[248px] flex-none overflow-auto border-l border-hair-strong p-[18px_16px] lg:block"
    >
      {/* See `CastRail`: the heading is on the shell so the sheet's own `<h2>` is not doubled. */}
      <h2 className="sr-only">Scene</h2>
      <DirectorRailContent {...props} />
    </aside>
  );
}
