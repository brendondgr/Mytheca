"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Eyebrow } from "@/components/ui/Eyebrow";
import type { TurnTask } from "@/lib/events";
import { cn } from "@/lib/cn";

/**
 * What a free-text turn said it owed you, filling in as it grades itself.
 *
 * Free-text mode has no plan to show, because it schedules nobody. What it has instead is a
 * checklist the model writes before it starts and then reads its own passage against, and
 * this is that list — arriving before a word of prose exists, and gaining its verdicts once
 * the review has run.
 *
 * **Not {@link DirectionChecklist}, deliberately.** That component tracks the player's own
 * direction across turns: two states plus an undeliverable set, a carried-over badge, a
 * dismiss control, and a standing list that survives the turn. None of those exist here — a
 * checklist is written fresh each turn, by the model rather than by the player, and it is
 * graded in three states rather than two. Bending one component around both would mean every
 * prop being meaningful in one mode and inert in the other.
 *
 * `who` is shown, and it is a **note about who is involved** — never an order of speaking.
 * Nothing in the engine dispatches on it, and the copy must not imply otherwise.
 *
 * Renders nothing outside free-text mode, which is most scenes.
 */
export function TurnChecklist({
  tasks,
  className,
  live = true,
}: {
  tasks: TurnTask[];
  className?: string;
  /**
   * Whether progress announces. `false` inside a surface that mounts on open — otherwise the
   * whole turn's grading is read out at once, after the fact, the moment the sheet appears.
   */
  live?: boolean;
}) {
  if (!tasks.length) return null;

  const graded = tasks.filter((t) => t.state !== "");
  const done = tasks.filter((t) => t.state === "yes").length;

  /**
   * Glyph, colour and a plain-English note per state.
   *
   * Four, not three: "not graded yet" is genuinely different from "graded and missing" —
   * the first means the turn is still writing, the second that it wrote and fell short. The
   * distinction is carried by the glyph and by words, never by colour alone.
   */
  const mark = (state: TurnTask["state"]) => {
    if (state === "yes") return { glyph: "✓", tone: "text-success", note: "" };
    if (state === "partial")
      return { glyph: "◐", tone: "text-ink-soft", note: "started, not finished" };
    if (state === "no") return { glyph: "✕", tone: "text-danger", note: "not on the page" };
    return { glyph: "○", tone: "text-mute2", note: "" };
  };

  return (
    <section className={cn("mt-5", className)} aria-labelledby="turn-checklist-heading">
      <Eyebrow tracking="0.16em" className="mb-[9px] block" id="turn-checklist-heading">
        What this turn owes you
      </Eyebrow>

      {/* One polite announcement of overall progress. Announcing each verdict as it lands
          would talk over the prose the transcript is already reading out. */}
      <p className="sr-only" aria-live={live ? "polite" : "off"}>
        {graded.length
          ? `${done} of ${tasks.length} delivered`
          : `${tasks.length} thing${tasks.length === 1 ? "" : "s"} to do, not yet checked`}
      </p>

      <ul className="grid gap-[6px]">
        <AnimatePresence initial={false}>
          {tasks.map((task) => {
            const { glyph, tone, note } = mark(task.state);
            return (
              <motion.li
                key={task.n}
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
                    task.state === "no"
                      ? "text-danger"
                      : task.state === ""
                        ? "text-mute2"
                        : "text-ink-soft",
                  )}
                >
                  {task.must}
                  {task.who.length ? (
                    <span className="ml-[5px] font-mono text-[9px] tracking-[0.08em] text-mute2">
                      {task.who.join(" · ")}
                    </span>
                  ) : null}
                  {note ? (
                    <span
                      className={cn(
                        "block font-mono text-[9px] tracking-[0.1em] uppercase",
                        task.state === "no" ? "" : "text-mute2",
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
    </section>
  );
}
