"use client";

import { Monogram } from "@/components/ui/Monogram";
import type { Character } from "@/lib/types";
import { mediaUrl } from "@/lib/api";

/**
 * The scene asking for a character who is not in it — with two answers, and no default.
 *
 * **The AI never brings anyone in.** There is no planner action for it; the engine can only
 * raise this question, and it does so only when the player themselves named an absent
 * character. That is the owner's rule made structural rather than merely intended: "I feel
 * like the AI will abuse it and bring in a character for the fun of it when we don't need
 * it." Nothing about presence changes until a button here is pressed.
 *
 * A centred aside rather than a bubble — nobody in the story said this. Once answered it
 * renders as a settled line and never as a live control again, so a reload cannot re-offer a
 * decision the player already made.
 */
export function CastRequestBeat({
  character,
  reason,
  resolved = false,
  disabled = false,
  onAccept,
  onDecline,
}: {
  /** The absent character being asked about; `null` when they have since been deleted. */
  character: Character | null;
  /** The requirement or phrase that named them — the player's own words, quoted back. */
  reason?: string;
  resolved?: boolean;
  /** No session yet, or a turn in flight — the answer is still shown, just not actionable. */
  disabled?: boolean;
  onAccept?: () => void;
  onDecline?: () => void;
}) {
  if (!character) return null;
  const name = character.name;

  if (resolved) {
    return (
      <p className="py-3xs text-center font-mono text-eyebrow tracking-[0.16em] text-mute2 uppercase">
        — you answered about {name} —
      </p>
    );
  }

  return (
    <section
      aria-label={`The scene is asking for ${name}`}
      className="mx-auto flex max-w-[420px] flex-col items-center gap-xs rounded-md border border-field-bd bg-field px-md py-sm text-center"
    >
      <Monogram
        mono={character.mono}
        color={character.color}
        size={26}
        ring={1}
        fontSize={11}
        src={character.portrait ? mediaUrl(character.portrait) : null}
      />
      <p className="font-body text-eyebrow leading-[1.45] text-ink-soft">
        The scene is asking for <strong className="font-semibold">{name}</strong>.
      </p>
      {reason ? (
        // The player's own words, not a generic prompt — so the ask is obviously a
        // consequence of what they wrote rather than the model inventing a reason.
        <p className="font-body text-eyebrow leading-[1.4] text-mute2 italic">“{reason}”</p>
      ) : null}
      <div className="flex flex-wrap items-center justify-center gap-xs">
        <button
          type="button"
          onClick={onAccept}
          disabled={disabled}
          className="min-h-[32px] rounded-md bg-accent px-md py-2xs font-mono text-eyebrow tracking-[0.08em] text-[#F6ECDA] uppercase hover:bg-accent-hover disabled:opacity-50 disabled:hover:bg-accent"
        >
          Bring them in
        </button>
        <button
          type="button"
          onClick={onDecline}
          disabled={disabled}
          className="min-h-[32px] rounded-md border border-field-bd px-md py-2xs font-mono text-eyebrow tracking-[0.08em] text-mute uppercase hover:bg-hover hover:text-ink disabled:opacity-50"
        >
          Not now
        </button>
      </div>
    </section>
  );
}
