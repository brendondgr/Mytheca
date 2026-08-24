"use client";

import { motion } from "framer-motion";
import { ENTER_TRANSITION } from "@/lib/motion";
import { Eyebrow } from "@/components/ui/Eyebrow";
import type { PlannedBeat } from "@/lib/events";

/**
 * **The plan, waiting for you** — what the scene intends to do with your message, before a
 * word of it is written.
 *
 * Shown only under Plan mode, when a turn has stopped for approval. Nothing has been
 * generated at this point and nothing is in the transcript: approving runs exactly these
 * beats with no second planner call, and *Change it* simply puts the player back in the
 * composer to re-word their direction and send again.
 *
 * **It shows intent, never prose.** The plan carries who acts and what they are trying to
 * do; the writing still happens fresh afterwards. Rendering a draft line here would quietly
 * turn approval into dictation, which is a different feature with different consequences for
 * every character's voice.
 *
 * Sits above the composer rather than over the transcript, because the transcript is the
 * thing the plan is *about* — covering it to ask "is this right?" hides the evidence.
 */
export function PlanApproval({
  beats,
  onApprove,
  onDismiss,
  busy = false,
}: {
  beats: PlannedBeat[];
  onApprove: () => void;
  /** Back to the composer to re-word the direction. Nothing is run. */
  onDismiss: () => void;
  busy?: boolean;
}) {
  if (!beats.length) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={ENTER_TRANSITION}
      aria-label="The plan for this turn"
      // A live region: it arrives mid-stream, after the player has pressed Send and looked
      // away. Announcing it is the difference between a panel and an ambush.
      aria-live="polite"
      className="mx-auto mb-[10px] flex max-w-[720px] flex-col gap-[9px] rounded-[12px] border border-accent bg-field p-[13px]"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-[6px]">
        <Eyebrow tracking="0.16em" color="var(--accent)">
          The plan — nothing written yet
        </Eyebrow>
        <span className="font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
          {beats.length} beat{beats.length === 1 ? "" : "s"}
        </span>
      </div>

      <ol className="flex flex-col gap-[6px]">
        {beats.map((beat, i) => (
          <li
            key={`${beat.action}-${beat.actorId ?? "none"}-${i}`}
            className="flex items-baseline gap-[8px]"
          >
            <span
              aria-hidden
              className="w-[14px] flex-none font-mono text-[9px] text-mute2"
            >
              {i + 1}
            </span>
            <span className="min-w-0 flex-1 font-body text-[12px] leading-[1.5] text-ink">
              <span className="font-mono text-[10px] tracking-[0.08em] text-accent uppercase">
                {beat.actorName || (beat.action === "narrate" ? "Narrator" : beat.action)}
              </span>
              {beat.reason ? <span className="text-mute"> — {beat.reason}</span> : null}
              {/* The register is the scene's read of the moment, and it is the thing most
                  worth arguing with: a beat pitched `grave` when you meant it lightly is the
                  case where approving blind costs you the scene. */}
              {beat.register ? (
                <span className="ml-[5px] font-mono text-[9px] tracking-[0.08em] text-mute2 uppercase">
                  · {beat.register}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center gap-[7px]">
        <button
          type="button"
          onClick={onApprove}
          disabled={busy}
          className="flex-none rounded-[8px] bg-accent px-[11px] py-[5px] font-mono text-[10px] tracking-[0.08em] text-[#F6ECDA] uppercase hover:bg-accent-hover disabled:opacity-50 disabled:hover:bg-accent"
        >
          Play it out
        </button>
        <button
          type="button"
          onClick={onDismiss}
          disabled={busy}
          className="flex-none rounded-[8px] border border-field-bd px-[9px] py-[5px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent disabled:opacity-50"
        >
          Change it
        </button>
        <p className="min-w-0 flex-1 font-body text-[11px] leading-[1.45] text-mute2">
          Approving runs exactly these beats. Changing it puts you back in the composer —
          nothing has been written either way.
        </p>
      </div>
    </motion.section>
  );
}
