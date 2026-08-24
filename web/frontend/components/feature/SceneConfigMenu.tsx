"use client";

import { useEffect, useId, useRef, useState } from "react";
import { SceneControlSelect } from "@/components/ui/SceneControlSelect";
import type { PlanMode } from "@/components/feature/PlanModeButton";
import type { SceneMemory } from "@/features/story-player/turn-stream";
import { Eyebrow } from "@/components/ui/Eyebrow";

/** How a beat is pitched. Mirrors the backend `Register`. */
export type Register = "light" | "neutral" | "tense" | "grave";

/** `Auto` is a real option, not the absence of one — the scene reading the moment is the
 *  default behaviour and the player should be able to choose it back. */
const AUTO = "__auto__";

const REGISTER_OPTIONS = [
  { value: AUTO, label: "Auto · the scene decides" },
  { value: "light", label: "Light" },
  { value: "neutral", label: "Neutral" },
  { value: "tense", label: "Tense" },
  { value: "grave", label: "Grave" },
];

const SUGGESTION_OPTIONS = [0, 1, 2, 3, 4];

function GearIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

/**
 * The scene's play-configuration popover — Max turns, Suggestions, Beat length.
 *
 * **"Number of beats" was deleted, not hidden.** It asked the player to pick a
 * context-window depth, which is a question only the app can answer: the right depth is
 * whatever the model can actually hold, and the app knows the model's window while the
 * player does not. The window now fits itself each turn
 * (`services/context_budget` + the scene's `contextPolicy`), and what the scene reached is
 * *reported* in the Inspector rather than *configured* here.
 *
 * Anchored in the composer's bottom-left controls row (`openUp` flips the popover above the
 * button). Native controls + Esc/outside-click close.
 */
/** Filled = pinned to the scene, outlined = this turn only. Shape, not colour. */
function PinIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 17v5" />
      <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1Z" />
    </svg>
  );
}

/** The three controls a turn may override, keyed as the wire names them. */
export type SceneControlKey = "suggestionsCount" | "planner" | "ties";

/** How much of a speaker's relationship history reaches their beat. */
export type TieScope = "addressed" | "scene" | "world";

const TIE_OPTIONS: { value: TieScope; label: string }[] = [
  { value: "addressed", label: "Whoever they're talking to" },
  { value: "scene", label: "Everyone in the room" },
  { value: "world", label: "…and people elsewhere" },
];

/** What each stop actually does, said as a consequence rather than a scope name. */
const TIE_HELP: Record<TieScope, string> = {
  addressed: "Only how the speaker feels about whoever they are talking to.",
  scene: "How the speaker feels about everyone in the room.",
  world:
    "…and about people elsewhere in this world. Characters may then mention someone the scene has never introduced.",
};

/**
 * Short names for the pins. The row captions state a consequence and are far too long to
 * read out as "«How many beats one message produces» — this turn only".
 */
const PIN_NAMES: Record<SceneControlKey, string> = {
  suggestionsCount: "Suggestions",
  planner: "Turn planning",
  ties: "Ties",
};

/**
 * Scope toggle for one control.
 *
 * `aria-pressed` carries the state, and the accessible name says which scope is in force —
 * "Max turns — pinned to this scene" / "Max turns — this turn only" — so the meaning never
 * depends on seeing the glyph. The visible difference is a filled versus outlined pin plus
 * the caption's own "· this turn" suffix: two non-colour signals, because scope changes what
 * a click permanently does to the player's scene and a hue alone cannot carry that.
 */
function PinToggle({
  controlKey,
  pinned,
  onChange,
  disabled,
}: {
  controlKey: SceneControlKey;
  pinned: boolean;
  onChange?: (key: SceneControlKey, pinned: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-pressed={pinned}
      aria-label={`${PIN_NAMES[controlKey]} — ${
        pinned ? "pinned to this scene" : "this turn only"
      }`}
      disabled={disabled}
      onClick={() => onChange?.(controlKey, !pinned)}
      // No `focus:outline-none` here: the global `:focus-visible` rule in `globals.css` is
      // UNLAYERED and a Tailwind utility (in `@layer utilities`) cannot override it, so the
      // class would be inert and imply a suppression that never happens. The 2px accent
      // outline is the focus indicator; the border change is a second, quieter signal.
      className={`flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[6px] border focus-visible:border-accent disabled:opacity-50 ${
        pinned
          ? "border-field-bd text-mute2 hover:border-accent hover:text-accent"
          : "border-accent text-accent"
      }`}
    >
      <PinIcon filled={pinned} />
    </button>
  );
}

export function SceneConfigMenu({
  suggestionsCount = 4,
  onSuggestionsCountChange,
  plannerMode = "auto",
  onPlannerModeChange,
  tieScope = "scene",
  onTieScopeChange,
  graphAvailable = true,
  register = null,
  onRegisterChange,
  sceneMemory = null,
  summarised = false,
  secondsPerBeat,
  pinned = { suggestionsCount: true, planner: true, ties: true },
  onPinnedChange,
  openUp = false,
  disabled = false,
}: {
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  /**
   * Whether a director reads each moment, or the cast simply answers in order.
   *
   * The popover owns only the **off** end of this. Choosing between playing straight through
   * and stopping for approval is a per-message decision and lives in the composer
   * (`PlanModeButton`); turning planning off entirely changes what the app *is*, which is not
   * a third position on that toggle.
   */
  plannerMode?: PlanMode;
  onPlannerModeChange?: (value: PlanMode) => void;
  /** How much of a speaker's relationship history reaches their beat. */
  tieScope?: TieScope;
  onTieScopeChange?: (value: TieScope) => void;
  /**
   * Whether the story graph exists on this install. `false` disables the Ties control **and
   * says why** — a control that silently does nothing is worse than one that is honestly
   * unavailable.
   */
  graphAvailable?: boolean;
  /**
   * A register pinned for the next message, or `null` to let the scene decide. There is no
   * pinned/unpinned choice here — it is per-turn by construction.
   */
  register?: Register | null;
  onRegisterChange?: (value: Register | null) => void;
  /** How far back the last turn reached — reported, not configured. */
  sceneMemory?: SceneMemory | null;
  /** Whether the beats that dropped out were kept as a summary (compaction on). */
  summarised?: boolean;
  /**
   * Observed seconds per beat in THIS session. Measured rather than hardcoded, because a
   * number invented in the UI would be wrong for every operator's hardware — omitted
   * entirely before a turn has run rather than guessed at.
   */
  secondsPerBeat?: number;
  /**
   * Whether each control is pinned to the scene. Pinned (the default) is today's behaviour
   * exactly: a change is written to the scenario and stays. Unpinned, a change applies to
   * the next message only and then springs back.
   */
  pinned?: Record<SceneControlKey, boolean>;
  onPinnedChange?: (key: SceneControlKey, pinned: boolean) => void;
  /** Open the popover upward (for the bottom-of-screen composer). */
  openUp?: boolean;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const unpinnedCount = Object.values(pinned).filter((p) => !p).length;
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  // Close on outside pointerdown or Escape; move focus into the panel when it opens.
  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={
          unpinnedCount > 0
            ? "Scene configuration — settings apply to this turn only"
            : "Scene configuration"
        }
        className="flex flex-none items-center gap-[5px] rounded-[8px] border border-field-bd px-[9px] py-[5px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-expanded:border-accent aria-expanded:text-accent"
      >
        <GearIcon />
        Config
        {/* Visible without opening the popover: something above is about to spring back.
            The dot is decoration — the button's own accessible name carries the meaning,
            because a coloured dot says nothing to a screen reader and nothing to a reader
            who cannot separate the hues. */}
        {unpinnedCount > 0 ? (
          <span aria-hidden className="h-[5px] w-[5px] flex-none rounded-full bg-accent" />
        ) : null}
      </button>

      {open ? (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Scene configuration"
          tabIndex={-1}
          // `max-h` + `overflow-y-auto` are load-bearing, not defensive. This panel grew from
          // three controls to seven across `docs/plans/depth-for-players.md`, and at 320x720
          // it measured 1004px tall opening upward from the composer — its top edge sat at
          // -386px and the first three controls were off-screen and unreachable, with the
          // panel itself not scrollable. Bounding it to the viewport is what keeps a control
          // added by the next phase reachable rather than silently lost off the top.
          className={`absolute left-0 z-40 flex max-h-[calc(100dvh-140px)] w-[264px] flex-col gap-[13px] overflow-y-auto mytheca-menu p-[14px] focus:outline-none ${
            openUp ? "bottom-[38px]" : "top-[38px]"
          }`}
        >
          <Eyebrow tracking="0.16em" color="var(--accent)">
            Scene configuration
          </Eyebrow>

          <SceneControlSelect
            label="Follow-up ideas offered after each turn"
            value={suggestionsCount}
            options={SUGGESTION_OPTIONS}
            onChange={(v) => onSuggestionsCountChange?.(v)}
            help="Shown under the last beat. 0 turns them off."
            action={
              <PinToggle
                controlKey="suggestionsCount"
                pinned={pinned.suggestionsCount}
                onChange={onPinnedChange}
                disabled={disabled}
              />
            }
            scopeNote={pinned.suggestionsCount ? undefined : "· this turn"}
            disabled={disabled || !onSuggestionsCountChange}
            className="w-full [&_select]:w-full"
          />

          {/* The scope footer. Rendered only when something is unpinned, because a line
              that is always there stops being read — and its whole job is to warn that the
              values above are about to spring back. */}
          {unpinnedCount > 0 ? (
            <p className="font-body text-[11px] leading-[1.45] text-ink">
              {unpinnedCount === 1 ? "1 setting applies" : `${unpinnedCount} settings apply`}{" "}
              to your next message only, then spring back.
            </p>
          ) : null}

          {/* The single largest latency lever a player has, and the copy says what it
              COSTS rather than only what it saves. Turning planning off is not a quality
              setting with an upside — it trades a real read of the moment for roughly half
              a turn's wall clock, and a control that hid that would be lying. */}
          <SceneControlSelect
            label="Turn planning"
            value={plannerMode}
            options={[
              { value: "auto", label: "On · a director reads each moment" },
              { value: "off", label: "Off · the cast answers in order" },
            ]}
            onChange={(v) => onPlannerModeChange?.(v as PlanMode)}
            help={
              plannerMode === "off"
                ? "Much faster — planning is over half of a turn. Nothing judges the moment: no scene-setting narration between beats, no read of how tense things are, and a character the story has written out stays in the rotation until you remove them from the cast rail."
                : "A director reads each moment, decides who speaks, sets the scene between beats, and pitches how tense the beat is. It is over half of a turn's time."
            }
            action={
              <PinToggle
                controlKey="planner"
                pinned={pinned.planner}
                onChange={onPinnedChange}
                disabled={disabled}
              />
            }
            scopeNote={pinned.planner ? undefined : "· this turn"}
            disabled={disabled || !onPlannerModeChange}
            className="w-full [&_select]:w-full"
          />

          {/* The story graph, put to work. Two of the three stops are the same query the
              engine already makes every beat with a wider id list; only the third adds one.
              Disabled-with-a-reason when there is no graph at all. */}
          <SceneControlSelect
            label="How much history a character carries"
            value={tieScope}
            options={TIE_OPTIONS}
            onChange={(v) => onTieScopeChange?.(v as TieScope)}
            help={
              graphAvailable
                ? TIE_HELP[tieScope]
                : "The story graph is off for this install, so nobody carries their history into a beat."
            }
            action={
              <PinToggle
                controlKey="ties"
                pinned={pinned.ties}
                onChange={onPinnedChange}
                disabled={disabled || !graphAvailable}
              />
            }
            scopeNote={pinned.ties ? undefined : "· this turn"}
            disabled={disabled || !onTieScopeChange || !graphAvailable}
            className="w-full [&_select]:w-full"
          />

          {/* The register is per-turn BY CONSTRUCTION, so it carries a permanent "this turn"
              tag instead of a pin: how tense a beat is belongs to a moment, and a scene-wide
              one would be wrong by the second message. The copy also says what it does NOT
              do, because a control called "register" sitting under "who speaks" invites
              exactly that misreading. */}
          <SceneControlSelect
            label="How this moment is pitched"
            value={register ?? AUTO}
            options={REGISTER_OPTIONS}
            onChange={(v) => onRegisterChange?.(v === AUTO ? null : (v as Register))}
            help="Pins how this moment is pitched for your next message only. It picks which of a character's voice samples they draw on and how far their word choice can wander — it does not decide who speaks."
            scopeNote="· this turn"
            disabled={disabled || !onRegisterChange}
            className="w-full [&_select]:w-full"
          />

          {/* Read-only. This is what replaced the "Number of beats" slider: the app decides
              the depth, and reports it, instead of asking the player to guess at it. */}
          <section
            aria-label="What the scene remembers"
            className="flex flex-col gap-[3px] border-t border-field-bd pt-[10px]"
          >
            <span className="font-mono text-[9px] tracking-[0.12em] text-mute2 uppercase">
              What the scene remembers
            </span>
            {sceneMemory ? (
              <p className="font-body text-[11px] leading-[1.45] text-mute2">
                The last {sceneMemory.windowBeats} beat
                {sceneMemory.windowBeats === 1 ? "" : "s"}, word for word
                {sceneMemory.budgetTokens ? (
                  <span className="font-mono text-[10px] text-ink-soft">
                    {" "}
                    (≈ {sceneMemory.budgetTokens.toLocaleString()} tokens)
                  </span>
                ) : null}
                .{" "}
                {sceneMemory.droppedBeats > 0
                  ? summarised
                    ? `${sceneMemory.droppedBeats} older beat${sceneMemory.droppedBeats === 1 ? " is" : "s are"} kept as a summary.`
                    : `${sceneMemory.droppedBeats} older beat${sceneMemory.droppedBeats === 1 ? " has" : "s have"} dropped out.`
                  : "Nothing has dropped out yet."}
              </p>
            ) : (
              <p className="font-body text-[11px] leading-[1.45] text-mute2">
                Fitted to the model&apos;s context window once the scene starts.
              </p>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
