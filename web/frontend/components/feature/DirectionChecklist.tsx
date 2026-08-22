"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Eyebrow } from "@/components/ui/Eyebrow";
import type { DirectionProgress } from "@/features/story-player/turn-stream";
import { cn } from "@/lib/cn";

/**
 * The player's scene direction, ticking off as the turn delivers it.
 *
 * The engine has always broken a direction into requirements and tracked which had
 * landed — but it only reported the outcome, after the fact, in the Inspector. Shown
 * live this is the clearest evidence in the app that a long turn is going somewhere:
 * unlike a spinner, it says *how much* is left.
 *
 * It also makes a real failure visible. A direction longer than the scene's beat budget
 * is compressed rather than spread, and the parts that never fit used to be discoverable
 * only by noticing something had not happened. They are now named.
 *
 * Renders nothing when the player is not directing the scene, which is most turns.
 */
export function DirectionChecklist({
  progress,
  className,
}: {
  progress: DirectionProgress;
  className?: string;
}) {
  const { items, undelivered } = progress;
  if (!items.length) return null;

  const done = items.filter((i) => i.state === "delivered").length;
  const tried = items.filter((i) => i.state === "attempted").length;
  const missed = new Set(undelivered);

  /**
   * Glyph, colour and (for the third state) an explanation.
   *
   * Three states, because "the scene may not have reached this" is genuinely different
   * from both "done" and "not started" — a beat was spent on it and the engine could not
   * confirm the prose got there. The distinction is carried by the glyph and by words, not
   * by colour alone.
   */
  const mark = (item: (typeof items)[number], undeliverable: boolean) => {
    if (item.state === "delivered") return { glyph: "✓", tone: "text-success", note: "" };
    if (undeliverable) return { glyph: "✕", tone: "text-danger", note: "did not fit this scene" };
    if (item.state === "attempted")
      return { glyph: "◐", tone: "text-ink-soft", note: "the scene may not have reached this" };
    return { glyph: "○", tone: "text-mute2", note: "" };
  };

  return (
    <section className={cn("mt-5", className)} aria-labelledby="direction-heading">
      <Eyebrow tracking="0.16em" className="mb-[9px] block" id="direction-heading">
        Your direction
      </Eyebrow>

      {/* One polite announcement of overall progress. Announcing each item as it lands
          would talk over the prose the transcript is already reading out. */}
      <p className="sr-only" aria-live="polite">
        {done} of {items.length} delivered
        {tried ? `, ${tried} attempted but not confirmed` : ""}
      </p>

      <ul className="grid gap-[6px]">
        <AnimatePresence initial={false}>
          {items.map((item) => {
            const undeliverable = missed.has(item.text) && item.state !== "attempted";
            const { glyph, tone, note } = mark(item, undeliverable);
            return (
              <motion.li
                key={item.text}
                layout
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-start gap-[7px]"
              >
                <span
                  aria-hidden
                  className={cn("mt-[3px] flex-none font-mono text-[10px] leading-none", tone)}
                >
                  {glyph}
                </span>
                <span
                  className={cn(
                    "min-w-0 font-body text-[12.5px] leading-[1.4]",
                    item.state === "delivered"
                      ? "text-ink-soft"
                      : undeliverable
                        ? "text-danger"
                        : item.state === "attempted"
                          ? "text-ink-soft"
                          : "text-mute2",
                  )}
                >
                  {item.text}
                  {note ? (
                    <span
                      className={cn(
                        "block font-mono text-[9px] tracking-[0.1em] uppercase",
                        undeliverable ? "" : "text-mute2",
                      )}
                    >
                      {note}
                    </span>
                  ) : null}
                </span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>

      <p className="mt-[8px] font-mono text-[9px] tracking-[0.12em] text-mute2 uppercase">
        {done}/{items.length} delivered
      </p>

      {undelivered.length ? (
        <p className="mt-[6px] font-body text-[12px] leading-[1.4] text-ink-soft">
          Raise the scene&apos;s turn limit to give a longer direction room.
        </p>
      ) : null}
    </section>
  );
}
