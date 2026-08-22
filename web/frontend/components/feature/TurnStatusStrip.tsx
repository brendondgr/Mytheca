"use client";

import { motion } from "framer-motion";
import { Monogram } from "@/components/ui/Monogram";
import { TypingDots } from "@/components/ui/TypingDots";
import { ENTER_TRANSITION } from "@/lib/motion";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Character } from "@/lib/types";
import type { TurnStatus } from "@/features/story-player/turn-stream";

/**
 * **Who is up** — the live status strip at the foot of the transcript.
 *
 * While a turn streams, prose simply appears: nothing tells the reader that a new speaker
 * has been chosen, that a line is still being written, or that the turn is wrapping up.
 * The cast rail carries a per-character marker, but it is `hidden … lg:block` — below
 * 1024px there is no speaker signal at all. This strip is that signal, at every breakpoint.
 *
 * It renders only while a turn is in flight, in the same slot `CreateImageBar` occupies
 * between turns, so the two swap without the composer hopping.
 *
 * The phase can briefly be `idle` mid-turn (a line just finished, the planner has not yet
 * named the next speaker). That is deliberately NOT a gap: it shows the neutral
 * "the scene is unfolding" line, because a strip that blinks out between every beat reads
 * as a glitch rather than as progress.
 *
 * Accessibility: one polite live region carrying the label — it changes at most once per
 * beat, and says something the {@link TranscriptAnnouncer} (which speaks *finished* prose)
 * does not. The dots and the monogram are decorative.
 */
export function TurnStatusStrip({
  status,
  streaming,
  charById,
  className,
}: {
  status: TurnStatus;
  /** True while a turn is being written — the strip is hidden entirely when false. */
  streaming: boolean;
  charById: (id: string) => Character | undefined;
  className?: string;
}) {
  if (!streaming) return null;

  const character = status.characterId ? charById(status.characterId) : undefined;
  // Cast lookup → the name the `speaker` trace carried → a neutral stand-in. The middle
  // step matters on a resumed scene, where a character may stream before the cast settles.
  const who = character?.name ?? status.name ?? "Someone";
  const label = labelFor(status.phase, who, status.planner);
  // The turn is over bar the bookkeeping — nothing more is being written, so dots would
  // promise something that is not coming.
  const showDots = status.phase !== "ending";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={ENTER_TRANSITION}
      className={cn("flex flex-col items-center gap-[4px]", className)}
    >
      <p
        role="status"
        aria-live="polite"
        className="inline-flex items-center gap-[8px] rounded-[999px] border border-cardbd bg-card px-[12px] py-[6px] font-mono text-[10px] tracking-[0.12em] text-ink-soft uppercase"
      >
        {character ? (
          <Monogram
            mono={character.mono}
            color={character.color}
            src={character.portrait ? mediaUrl(character.portrait) : undefined}
            size={18}
            fontSize={8}
            ring={1.5}
          />
        ) : null}
        {/* The label stays on a contrast-checked token, not the character's color: at 10px
            uppercase a light character color would fall under AA. Identity is carried by the
            monogram's ring instead, where it is graphical rather than text. */}
        <span className="text-ink-soft">{label}</span>
        {showDots ? <TypingDots className="text-mute2" /> : null}
      </p>
      {/* How the turn read the message, or why this speaker is up. Outside the live region
          above: the label already announces the change, and repeating a long clause on
          every phase would make the strip chatty for a screen reader. Wraps rather than
          truncates — a directive the player cannot finish reading is worse than none. */}
      {status.detail ? (
        <p className="max-w-[46ch] text-balance px-[8px] text-center font-body text-[12px] leading-[1.4] text-mute2">
          {status.detail}
        </p>
      ) : null}
    </motion.div>
  );
}

/**
 * The player-facing sentence for each phase.
 *
 * The pre-generation phases matter as much as the character ones: they cover the stretch
 * before the first token, which is the longest part of a turn and used to show nothing but
 * the generic fallback below.
 */
function labelFor(
  phase: TurnStatus["phase"],
  who: string,
  planner?: TurnStatus["planner"],
): string {
  // Planning off: nothing is being worked out, and saying otherwise would make a turn the
  // player deliberately made fast look like one that is stuck.
  if (phase === "planning" && planner === "off") {
    return "The cast answers in order";
  }
  switch (phase) {
    case "gathering":
      return "Gathering the scene";
    case "reading":
      return "Reading your message";
    case "planning":
      // Deliberately not "deciding who speaks next": the planner now decides several
      // beats in one pass (TURN_PLANNER_LOOKAHEAD), so a label promising one choice
      // would misdescribe the wait it is covering.
      return "Working out what happens next";
    case "thinking":
      return `${who} is thinking`;
    case "speaking":
      return `${who} is speaking`;
    case "acting":
      return `${who} is acting`;
    case "narrating":
      return "The narrator is setting the scene";
    case "ending":
      return "The turn is ending";
    default:
      return "The scene is unfolding";
  }
}
