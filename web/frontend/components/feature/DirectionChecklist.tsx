"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Eyebrow } from "@/components/ui/Eyebrow";
import type { DirectionProgress } from "@/features/story-player/turn-stream";
import type { StandingItem } from "@/lib/events";
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
  standing = [],
  onDismiss,
  className,
  live = true,
}: {
  progress: DirectionProgress;
  /**
   * What an earlier turn could not deliver and the next one will re-owe. Shown alongside
   * this turn's progress, because between turns there IS no progress — a standing item that
   * only appeared mid-turn would blink in and out.
   */
  standing?: StandingItem[];
  /** Stop asking for one item (`null` → all of them). Omit to hide the control. */
  onDismiss?: (itemId: string | null) => void;
  className?: string;
  /**
   * Whether the progress line announces. `false` when this checklist is inside a surface
   * that mounts on open — otherwise the whole turn's progress is read out at once, after the
   * fact, the moment the sheet appears.
   */
  live?: boolean;
}) {
  const { items, undelivered } = progress;
  // A standing item whose text is already on this turn's checklist is the same debt being
  // worked on right now — show it once, in the live list, wearing the carried-over badge.
  // Named `onThisTurn`, not `live` — `live` is the announcement prop above.
  const onThisTurn = new Set(items.map((i) => i.text));
  const waiting = standing.filter((s) => !onThisTurn.has(s.text));
  const carriedText = new Set(standing.map((s) => s.text));
  if (!items.length && !waiting.length) return null;

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
    if (item.state === "delivered") return { glyph: "✓", tone: "text-success-ink", note: "" };
    if (undeliverable) return { glyph: "✕", tone: "text-danger-ink", note: "did not fit this scene" };
    if (item.state === "attempted")
      return { glyph: "◐", tone: "text-ink-soft", note: "the scene may not have reached this" };
    return { glyph: "○", tone: "text-mute2", note: "" };
  };

  return (
    <section className={cn("mt-5", className)} aria-labelledby="direction-heading">
      <Eyebrow tracking="0.16em" className="mb-sm block" id="direction-heading">
        Your direction
      </Eyebrow>

      {/* One polite announcement of overall progress. Announcing each item as it lands
          would talk over the prose the transcript is already reading out. */}
      <p className="sr-only" aria-live={live ? "polite" : "off"}>
        {done} of {items.length} delivered
        {tried ? `, ${tried} attempted but not confirmed` : ""}
        {standing.length ? `, ${standing.length} carried over` : ""}
      </p>

      <ul className="grid gap-xs">
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
                className="flex items-start gap-xs"
              >
                <span
                  aria-hidden
                  className={cn("mt-3xs flex-none font-mono text-eyebrow leading-none", tone)}
                >
                  {glyph}
                </span>
                <span
                  className={cn(
                    "min-w-0 font-body text-eyebrow leading-[1.4]",
                    item.state === "delivered"
                      ? "text-ink-soft"
                      : undeliverable
                        ? "text-danger-ink"
                        : item.state === "attempted"
                          ? "text-ink-soft"
                          : "text-mute2",
                  )}
                >
                  {item.text}
                  {carriedText.has(item.text) ? (
                    <span className="ml-2xs rounded-sm border border-field-bd px-2xs py-3xs align-middle font-mono text-eyebrow tracking-[0.1em] text-mute2 uppercase">
                      carried over
                    </span>
                  ) : null}
                  {note ? (
                    <span
                      className={cn(
                        "block font-mono text-eyebrow tracking-[0.1em] uppercase",
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

      {waiting.length ? (
        <ul
          aria-label="Still owed from an earlier turn"
          className="mt-sm grid gap-xs border-t border-field-bd pt-sm"
        >
          {waiting.map((s) => (
            <li key={s.id} className="flex items-start gap-xs">
              <span aria-hidden className="mt-3xs flex-none font-mono text-eyebrow leading-none text-mute2">
                ○
              </span>
              <span className="min-w-0 flex-1 font-body text-eyebrow leading-[1.4] text-mute2">
                {s.text}
                <span className="ml-2xs rounded-sm border border-field-bd px-2xs py-3xs align-middle font-mono text-eyebrow tracking-[0.1em] uppercase">
                  carried over
                </span>
              </span>
              {onDismiss ? (
                // 24x24 minimum target (WCAG 2.5.8) — the glyph is small, the hit area is
                // not. Labelled with the text so the control is unambiguous out of context.
                <button
                  type="button"
                  onClick={() => onDismiss(s.id)}
                  aria-label={`Stop asking for ${s.text}`}
                  className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-sm text-eyebrow text-mute2 hover:bg-hover hover:text-ink"
                >
                  ×
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-sm font-mono text-eyebrow tracking-[0.12em] text-mute2 uppercase">
        {done}/{items.length} delivered
      </p>

      {undelivered.length ? (
        <p className="mt-xs font-body text-eyebrow leading-[1.4] text-ink-soft">
          Raise the scene&apos;s turn limit to give a longer direction room.
        </p>
      ) : null}
    </section>
  );
}
