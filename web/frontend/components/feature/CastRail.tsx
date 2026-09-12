import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TypingDots } from "@/components/ui/TypingDots";
import { Select } from "@/components/ui/Select";
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
    <div className="mt-xl">
      <Eyebrow tracking="0.16em" className="mb-sm block">
        Turn order
      </Eyebrow>
      <div className="flex flex-wrap gap-2xs">
        {order.map((x, i) => {
          const isYou = x === "You";
          const c = isYou ? undefined : charById(x);
          const mono = isYou ? "YOU" : (c?.mono ?? "?");
          const color = isYou ? "#C8543E" : (c?.color ?? "#5A534A");
          const active = i === 0;
          return (
            <span
              key={`${x}-${i}`}
              className="rounded-lg border px-sm py-1 font-mono text-eyebrow font-medium tracking-[0.04em]"
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

/**
 * The manual presence control: a labelled native select (keyboard-operable, full control).
 *
 * It carries the shared {@link Select} chrome rather than its own. The hand-rolled version
 * set `font-mono text-field` — 16px monospace — once per cast member down a rail narrow
 * enough to be a bottom sheet on a phone, which made the "in the scene / unconscious /
 * departed / left / dead" dropdown the loudest thing in the rail. `Select` keeps the 16px
 * where it is load-bearing (below `sm`, against iOS auto-zoom) and drops to the dense size
 * above it.
 *
 * No visible title: the row already prints the status beside the name when a character is
 * away, and a caption per member would spend a line saying what the control already shows.
 */
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
    <Select
      aria-label={`Presence for ${character.name}`}
      value={status}
      onChange={(e) => onChange(e.target.value as PresenceStatus)}
      className="mt-xs w-full border-cardbd bg-card tracking-[0.04em] text-ink-soft"
    >
      {PRESENCE_OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </Select>
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
    <div className="mt-xs flex flex-col gap-3xs">
      {visible.map((d) => (
        <div key={d.key} className="flex items-baseline justify-between gap-2">
          <span className="min-w-0 truncate font-mono text-eyebrow tracking-[0.02em] text-ink-soft">
            {d.displayName}
          </span>
          <span className="flex-none font-mono text-eyebrow text-accent-ink">
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
        "rounded-xs border p-[8px_10px]",
        effectiveSpeaking ? "border-accent bg-card2" : "border-cardbd bg-card",
        away && "opacity-60",
      )}
    >
      <div className="flex items-center gap-sm">
        <button
          type="button"
          onClick={() => onProfile(c.id)}
          title="View profile"
          className="mytheca-row flex min-w-0 flex-1 items-center gap-sm text-left hover-nudge"
        >
          <Monogram mono={c.mono} color={c.color} src={c.portrait ? mediaUrl(c.portrait) : undefined} size={34} fontSize={13} />
          <span className="min-w-0 flex-1">
            {/* `break-normal` against the global `overflow-wrap: break-word`. A cast card
                loses width whenever the Speaking badge appears beside it, and the global
                rule then splits the name mid-word — a live rail read "Captai / n Doran
                Hale" and "ANTAGONI / ST". Both the name and the role wrap between words
                instead, onto a second line where they need one: a two-line name is fine,
                and a clipped or hyphen-free-broken one is not. */}
            <span
              className={cn(
                "block break-normal font-display text-body-sm font-semibold leading-[1.05] text-ink",
                status === "dead" && "line-through",
              )}
            >
              {c.name}
            </span>
            <Eyebrow size={8} tracking="0.08em" entity={c.color} className="mt-3xs block break-normal">
              {c.role}
            </Eyebrow>
          </span>
        </button>
        {effectiveSpeaking ? (
          <span className="flex-none font-mono text-eyebrow tracking-[0.1em] text-success-ink uppercase">
            Speaking
          </span>
        ) : isThinking ? (
          <span className="flex flex-none items-center gap-2xs font-mono text-eyebrow tracking-[0.1em] text-ink-soft uppercase">
            Thinking <TypingDots />
          </span>
        ) : away ? (
          <span className="flex-none font-mono text-eyebrow tracking-[0.1em] text-ink-soft uppercase">
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

/**
 * Every prop the cast rail takes. Named so the `lg`-only shell and the mobile drawer are
 * provably passing the same thing — the split only guarantees "identical functionality" if
 * neither surface can quietly take a narrower set.
 */
export interface CastRailProps {
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
  /**
   * Every character in the storyline. The rail's third section offers the ones this scene
   * never cast — the world outside the room — so a play-through can invite someone in
   * without the scenario being re-authored.
   */
  storylineCast?: Character[];
  /** No session yet: there is nothing to attach a presence change to. */
  joinDisabled?: boolean;
}

/**
 * The cast rail's contents, with no container of its own: cast "in the scene" (with a
 * speaking/thinking marker + presence control), those out of the scene grouped below, anyone
 * elsewhere in the world, and the turn order. Presence lets the player remove/restore any
 * character; the engine also removes them automatically on death/departure. `activityByChar`
 * drives per-character "Thinking" (dots) and "Speaking" status labels.
 *
 * Container-free on purpose: {@link CastRail} wraps it in the desktop `<aside>` and the mobile
 * bottom sheet wraps the very same component, so a capability added here cannot reach one
 * width and miss the other.
 */
export function CastRailContent({
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
  storylineCast = [],
  joinDisabled = false,
}: CastRailProps) {
  const statusOf = (id: string): PresenceStatus => presenceByChar[id] ?? "present";
  const present = cast.filter((c) => statusOf(c.id) === "present");
  const away = cast.filter((c) => statusOf(c.id) !== "present");
  // Anyone in the world who is not in this scene at all — neither cast nor already joined.
  const inScene = new Set(cast.map((c) => c.id));
  const elsewhere = storylineCast.filter((c) => !inScene.has(c.id));

  return (
    <>
      <Eyebrow tracking="0.16em" className="mb-3 block">
        In the Scene
      </Eyebrow>
      <div className="flex flex-col gap-xs">
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
          <Eyebrow tracking="0.16em" className="mb-2 mt-lg block">
            Out of the Scene
          </Eyebrow>
          <div className="flex flex-col gap-xs">
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

      {elsewhere.length > 0 ? (
        <>
          <Eyebrow tracking="0.16em" className="mb-2 mt-lg block">
            Elsewhere in the World
          </Eyebrow>
          <ul className="flex flex-col gap-2xs">
            {elsewhere.map((c) => (
              <li key={c.id} className="flex items-center gap-xs">
                <Monogram
                  mono={c.mono}
                  color={c.color}
                  size={22}
                  ring={1}
                  fontSize={9}
                  src={c.portrait ? mediaUrl(c.portrait) : null}
                />
                <span className="min-w-0 flex-1 truncate font-display text-eyebrow text-mute2">
                  {c.name}
                </span>
                {setPresence ? (
                  <button
                    type="button"
                    onClick={() => setPresence(c.id, "present")}
                    disabled={joinDisabled}
                    aria-label={`Bring ${c.name} into the scene`}
                    title={
                      joinDisabled
                        ? "Play a turn first — there is no scene to join yet."
                        : `Bring ${c.name} into the scene`
                    }
                    className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-sm border border-field-bd text-label leading-none text-mute hover:bg-hover hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
                  >
                    +
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <TurnOrder order={turnOrder} charById={charById} />
    </>
  );
}

/**
 * The desktop shell: the `lg`-only left rail. Below `lg` this renders nothing at all and the
 * story player reaches the same content through a bottom sheet — one landmark at a time, never
 * two copies in the tree.
 *
 * `aria-label` is not decoration here: an unnamed `<aside>` is a complementary landmark a
 * screen-reader user has no way to tell apart from the other one on the page.
 */
export function CastRail(props: CastRailProps) {
  return (
    <aside
      aria-label="Cast"
      className="mytheca-rail hidden w-[236px] flex-none overflow-auto border-r border-hair-strong p-[18px_16px] lg:block"
    >
      {/* The heading lives on the SHELL, not in the content: the bottom sheet renders its own
          visible `<h2>` from `Drawer`'s title, and two would be a duplicate. Without one on
          this side the document went h1 straight to the dossier's h3 with nothing between. */}
      <h2 className="sr-only">Cast</h2>
      <CastRailContent {...props} />
    </aside>
  );
}
