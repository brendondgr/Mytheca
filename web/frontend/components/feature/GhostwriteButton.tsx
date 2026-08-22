"use client";

import { TypingDots } from "@/components/ui/TypingDots";

/**
 * **Ghostwrite** — turn the note in the message box into the line itself.
 *
 * The player types what they *want* the line to do ("tell him I don't believe a word of it,
 * but stay polite") and this writes it, in their character's voice or the narrator's. The
 * draft lands in the same `<textarea>` they type into, so reviewing and editing it needs no
 * new affordance — it is just text in the box, and Undo puts back what was there before.
 *
 * Disabled until the box has something in it, because the box *is* the input.
 */
export function GhostwriteButton({
  onGhostwrite,
  onUndo,
  running = false,
  canGhostwrite = false,
  canUndo = false,
}: {
  onGhostwrite: () => void;
  onUndo: () => void;
  running?: boolean;
  /** False when the message box is empty — there is no intent to write from. */
  canGhostwrite?: boolean;
  /** True once a draft has replaced the player's note, until they type again or send. */
  canUndo?: boolean;
}) {
  if (canUndo && !running) {
    return (
      <button
        type="button"
        onClick={onUndo}
        aria-label="Undo the drafted line and restore what you wrote"
        title="Undo — put your own note back"
        className="flex flex-none items-center gap-[5px] rounded-[8px] border border-field-bd px-[9px] py-[5px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent"
      >
        <span aria-hidden>↶</span> Undo
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onGhostwrite}
      disabled={!canGhostwrite || running}
      aria-label="Write this line for me"
      title="Write it for me — turn your note into the line itself"
      className="flex flex-none items-center gap-[5px] rounded-[8px] border border-field-bd px-[9px] py-[5px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-field-bd disabled:hover:text-mute"
    >
      {running ? (
        <>
          <TypingDots />
          <span className="sr-only" aria-live="polite">
            Drafting your line…
          </span>
        </>
      ) : (
        <>
          <span aria-hidden>✒</span> Write it
        </>
      )}
    </button>
  );
}
