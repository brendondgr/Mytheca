import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TypingDots } from "@/components/ui/TypingDots";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { liveValueFor } from "@/components/feature/DirectorRail";
import type { PresenceStatus } from "@/lib/events";
import type { Character, StatDefinition } from "@/lib/types";
import type { StatChip } from "@/features/story-player/scene-data";
import type { CharacterActivity } from "@/features/story-player/turn-stream";

export function TurnOrder({
  order,
  charById,
}: {
  order: string[];
  charById: (id: string) => Character | undefined;
}) {
  return (
    <div className="mt-[22px]">
      <Eyebrow tracking="0.16em" className="mb-[10px] block">
        Turn order
      </Eyebrow>
      <div className="flex flex-wrap gap-[5px]">
        {order.map((x, i) => {
          const isYou = x === "You";
          const c = isYou ? undefined : charById(x);
          const mono = isYou ? "YOU" : (c?.mono ?? "?");
          const color = isYou ? "#C8543E" : (c?.color ?? "#5A534A");
          const active = i === 0;
          return (
            <span
              key={`${x}-${i}`}
              className="rounded-[12px] border px-[9px] py-1 font-mono text-[9px] font-medium tracking-[0.04em]"
              style={{
                borderColor: color,
                color: active ? "#F6ECDA" : color,
                background: active ? color : "var(--card-bg)",
              }}
            >
              {mono}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// Ordered options for the manual presence control + their short labels.
const PRESENCE_OPTIONS: { value: PresenceStatus; label: string }[] = [
  { value: "present", label: "In the scene" },
  { value: "unconscious", label: "Unconscious" },
  { value: "departed", label: "Departed" },
  { value: "left", label: "Left" },
  { value: "dead", label: "Dead" },
];
const PRESENCE_LABEL: Record<PresenceStatus, string> = {
  present: "In the scene",
  unconscious: "Unconscious",
  departed: "Departed",
  left: "Left",
  dead: "Dead",
};

/** The manual presence control: a labeled native select (keyboard-operable, full control). */
function PresenceControl({
  character,
  status,
  onChange,
}: {
  character: Character;
  status: PresenceStatus;
  onChange: (status: PresenceStatus) => void;
}) {
  return (
    <select
      aria-label={`Presence for ${character.name}`}
      value={status}
      onChange={(e) => onChange(e.target.value as PresenceStatus)}
      className="mt-[6px] w-full rounded-[3px] border border-cardbd bg-card px-[6px] py-[3px] font-mono text-[9px] tracking-[0.04em] text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      {PRESENCE_OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** Compact "beneath the name" list of this character's public stat values — live when a
 * stat has streamed in this session (`values`, keyed by characterId in `statsByChar`),
 * else falling back to the storyline's schema default. The always-visible in-scene
 * counterpart to the Library `CharacterCard`'s stat list. */
function CastMemberStats({
  statDefs,
  values,
}: {
  statDefs: StatDefinition[];
  values?: StatChip[];
}) {
  const visible = statDefs.filter((d) => d.visibility === "public");
  if (visible.length === 0) return null;
  return (
    <div className="mt-[6px] flex flex-col gap-[2px]">
      {visible.map((d) => (
        <div key={d.key} className="flex items-baseline justify-between gap-2">
          <span className="min-w-0 truncate font-mono text-[9px] tracking-[0.02em] text-ink-soft">
            {d.displayName}
          </span>
          <span className="flex-none font-mono text-[9px] text-accent">
            {liveValueFor(d, values) ?? d.default}
          </span>
        </div>
      ))}
    </div>
  );
}

function CastMemberRow({
  c,
  status,
  speaking,
  activity,
  onProfile,
  setPresence,
  statDefs,
  stats,
}: {
  c: Character;
  status: PresenceStatus;
  speaking: boolean;
  activity?: CharacterActivity;
  onProfile: (id: string) => void;
  setPresence?: (id: string, status: PresenceStatus) => void;
  statDefs?: StatDefinition[];
  stats?: StatChip[];
}) {
  const away = status !== "present";
  // Merge the activity-based status with the existing speakingId signal.
  // activity==="speaking" (or the legacy speakingId match) → show "Speaking".
  // activity==="thinking" → show "Thinking" + dots.
  // Away characters keep their presence label regardless.
  const effectiveSpeaking = speaking || activity === "speaking";
  const isThinking = !effectiveSpeaking && activity === "thinking";

  return (
    <div
      className={cn(
        "rounded-[3px] border p-[8px_10px]",
        effectiveSpeaking ? "border-accent bg-card2" : "border-cardbd bg-card",
        away && "opacity-60",
      )}
    >
      <div className="flex items-center gap-[10px]">
        <button
          type="button"
          onClick={() => onProfile(c.id)}
          title="View profile"
          className="mytheca-row flex min-w-0 flex-1 items-center gap-[10px] text-left hover-nudge"
        >
          <Monogram mono={c.mono} color={c.color} src={c.portrait ? mediaUrl(c.portrait) : undefined} size={34} fontSize={13} />
          <span className="min-w-0 flex-1">
            <span
              className={cn(
                "block font-display text-[14px] font-semibold leading-[1.05] text-ink",
                status === "dead" && "line-through",
              )}
            >
              {c.name}
            </span>
            <Eyebrow size={8} tracking="0.08em" color={c.color} className="mt-[3px] block">
              {c.role}
            </Eyebrow>
          </span>
        </button>
        {effectiveSpeaking ? (
          <span className="flex-none font-mono text-[7.5px] tracking-[0.1em] text-success uppercase">
            Speaking
          </span>
        ) : isThinking ? (
          <span className="flex flex-none items-center gap-[4px] font-mono text-[7.5px] tracking-[0.1em] text-ink-soft uppercase">
            Thinking <TypingDots />
          </span>
        ) : away ? (
          <span className="flex-none font-mono text-[7.5px] tracking-[0.1em] text-ink-soft uppercase">
            {PRESENCE_LABEL[status]}
          </span>
        ) : null}
      </div>
      {statDefs ? <CastMemberStats statDefs={statDefs} values={stats} /> : null}
      {setPresence ? (
        <PresenceControl character={c} status={status} onChange={(s) => setPresence(c.id, s)} />
      ) : null}
    </div>
  );
}

/** Left rail: cast "in the scene" (with a speaking/thinking marker + presence control),
 * those out of the scene grouped below, and the turn order. Presence lets the player
 * remove/restore any character; the engine also removes them automatically on death/departure.
 * `activityByChar` drives per-character "Thinking" (dots) and "Speaking" status labels. */
export function CastRail({
  cast,
  speakingId,
  turnOrder,
  charById,
  onProfile,
  presenceByChar = {},
  setPresence,
  statDefs,
  statsByChar = {},
  activityByChar = {},
}: {
  cast: Character[];
  speakingId: string | null;
  turnOrder: string[];
  charById: (id: string) => Character | undefined;
  onProfile: (id: string) => void;
  presenceByChar?: Record<string, PresenceStatus>;
  setPresence?: (id: string, status: PresenceStatus) => void;
  /** The storyline's stat schema — when given, each cast member shows their public stat
   * values (live via `statsByChar`, else the schema default) beneath their name/role. */
  statDefs?: StatDefinition[];
  statsByChar?: Record<string, StatChip[]>;
  /** Live per-character activity status from the turn stream (Phase 6). */
  activityByChar?: Record<string, CharacterActivity>;
}) {
  const statusOf = (id: string): PresenceStatus => presenceByChar[id] ?? "present";
  const present = cast.filter((c) => statusOf(c.id) === "present");
  const away = cast.filter((c) => statusOf(c.id) !== "present");

  return (
    <aside className="mytheca-rail hidden w-[236px] flex-none overflow-auto border-r border-hair-strong p-[18px_16px] lg:block">
      <Eyebrow tracking="0.16em" className="mb-3 block">
        In the Scene
      </Eyebrow>
      <div className="flex flex-col gap-[7px]">
        {present.map((c) => (
          <CastMemberRow
            key={c.id}
            c={c}
            status="present"
            speaking={c.id === speakingId}
            activity={activityByChar[c.id]}
            onProfile={onProfile}
            setPresence={setPresence}
            statDefs={statDefs}
            stats={statsByChar[c.id]}
          />
        ))}
      </div>

      {away.length > 0 ? (
        <>
          <Eyebrow tracking="0.16em" className="mb-2 mt-[18px] block">
            Out of the Scene
          </Eyebrow>
          <div className="flex flex-col gap-[7px]">
            {away.map((c) => (
              <CastMemberRow
                key={c.id}
                c={c}
                status={statusOf(c.id)}
                speaking={false}
                activity={activityByChar[c.id]}
                onProfile={onProfile}
                setPresence={setPresence}
                statDefs={statDefs}
                stats={statsByChar[c.id]}
              />
            ))}
          </div>
        </>
      ) : null}

      <TurnOrder order={turnOrder} charById={charById} />
    </aside>
  );
}
