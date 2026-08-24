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
 *
 * **Icon-only, and sitting between the context dial and Send.** It used to read "✒ Write it"
 * beside the POV select, which put a labelled verb in the middle of the controls row for a
 * feature most turns do not use, and pushed the two things a player looks at every turn —
 * how full the context is, and Send — further apart. An icon-only control MUST carry its
 * accessible name; that is the whole cost of the change and the thing most likely to be
 * dropped by a later edit.
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
        // 28px square: comfortably past the WCAG 2.5.8 24px floor now that there is no label
        // widening the hit area.
        className="flex h-[28px] w-[28px] flex-none items-center justify-center rounded-[8px] border border-field-bd text-[13px] text-mute hover:border-accent hover:text-accent"
      >
        <span aria-hidden>↶</span>
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
      className="flex h-[28px] w-[28px] flex-none items-center justify-center rounded-[8px] border border-field-bd text-[13px] text-mute hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-field-bd disabled:hover:text-mute"
    >
      {running ? (
        <>
          <TypingDots />
          <span className="sr-only" aria-live="polite">
            Drafting your line…
          </span>
        </>
      ) : (
        <span aria-hidden>✒</span>
      )}
    </button>
  );
}
