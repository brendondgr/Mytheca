"use client";

import { useEffect } from "react";
import { CloseButton } from "@/components/ui/CloseButton";
import type { TraceTurn } from "@/features/story-player/turn-stream";
import type { TurnTraceFrame } from "@/lib/events";

// Per-step display: a short tag + accent color. Key beats (Director, thinking) are
// gold; everything else reads as muted so the eye lands on the "why" first.
const STEP_META: Record<string, { tag: string; accent: boolean }> = {
  turn: { tag: "You", accent: false },
  assemble: { tag: "Scene", accent: false },
  director: { tag: "Director", accent: true },
  speaker: { tag: "Speaker", accent: false },
  thinking: { tag: "Thinks", accent: true },
  consistency: { tag: "Check", accent: false },
  action: { tag: "Acts", accent: false },
  dialogue: { tag: "Says", accent: false },
  stat: { tag: "Stat", accent: false },
  rerank: { tag: "Re-rank", accent: true },
  cascade: { tag: "Cascade", accent: true },
  branch: { tag: "Branch", accent: true },
  reflection: { tag: "Reflect", accent: false },
};

function tagFor(step: string): { tag: string; accent: boolean } {
  return STEP_META[step] ?? { tag: step, accent: false };
}

/** One trace step: a colored tag, its title, and the plain-language detail below. */
function StepRow({ step }: { step: TurnTraceFrame }) {
  const meta = tagFor(step.step);
  return (
    <li className="flex gap-[10px] py-[7px]">
      <span
        className={`mt-[1px] flex-none rounded-[3px] border px-[6px] py-[2px] font-mono text-[8.5px] tracking-[0.1em] uppercase ${
          meta.accent
            ? "border-accent/40 text-accent"
            : "border-cardbd text-mute2"
        }`}
      >
        {meta.tag}
      </span>
      <div className="min-w-0">
        <div className="font-body text-[13px] leading-[1.35] text-ink">{step.title}</div>
        {step.detail ? (
          <div className="mt-[2px] font-body text-[12.5px] leading-[1.45] text-ink-soft">
            {step.detail}
          </div>
        ) : null}
      </div>
    </li>
  );
}

/** One turn: the player's message as a header, then its steps in the order they ran. */
function TurnBlock({ turn, index }: { turn: TraceTurn; index: number }) {
  return (
    <section className="rounded-[4px] border border-cardbd bg-card2">
      <header className="flex items-baseline gap-[8px] border-b border-cardbd p-[9px_12px]">
        <span className="flex-none font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
          Turn {index}
        </span>
        <span className="min-w-0 flex-1 truncate font-body text-[12.5px] text-ink-soft italic">
          {turn.label || "(turn)"}
        </span>
      </header>
      <ol className="divide-y divide-cardbd/60 p-[4px_12px_8px]">
        {turn.steps
          .filter((s) => s.step !== "turn")
          .map((s) => (
            <StepRow key={s.n} step={s} />
          ))}
      </ol>
    </section>
  );
}

/**
 * A wide right-side drawer that explains the turn loop, in order, after each message:
 * which characters the Director picked and why, their private thinking, stat changes,
 * mid-turn re-ranks, and the reflection step. Newest turn first. Read-only diagnostics
 * — the panel never changes the scene, it only reveals the reasoning behind it.
 */
export function TurnInspectorPanel({
  open,
  onClose,
  turns,
}: {
  open: boolean;
  onClose: () => void;
  turns: TraceTurn[];
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const ordered = [...turns].reverse(); // newest turn at the top

  return (
    <div className="fixed inset-0 z-[60]">
      {/* Backdrop — click to dismiss. */}
      <button
        type="button"
        aria-label="Close inspector"
        onClick={onClose}
        className="absolute inset-0 bg-[rgba(8,5,2,0.35)]"
      />
      <aside
        role="dialog"
        aria-label="Turn inspector"
        className="absolute inset-y-0 right-0 flex w-[min(92vw,480px)] flex-col border-l border-hair-strong bg-page shadow-[0_0_40px_rgba(8,5,2,0.45)]"
      >
        <header className="flex flex-none items-start justify-between gap-3 border-b border-hair-strong p-[16px_18px]">
          <div>
            <h2 className="font-display text-[16px] font-bold leading-none text-ink">
              Turn Inspector
            </h2>
            <p className="mt-[6px] font-mono text-[9.5px] leading-[1.5] tracking-[0.08em] text-mute uppercase">
              What happened, in order, after each message
            </p>
          </div>
          <CloseButton onClose={onClose} className="relative" />
        </header>

        <div className="min-h-0 flex-1 overflow-auto p-[14px_16px]">
          {ordered.length === 0 ? (
            <p className="mt-[10px] font-body text-[13px] leading-[1.5] text-ink-soft">
              Send a message in the scene and the flow will appear here — the Director&apos;s
              choice of who speaks and why, each character&apos;s private thinking, any stat
              changes, and the reflection step that sets up the next turn.
            </p>
          ) : (
            <div className="flex flex-col gap-[12px]">
              {ordered.map((turn, i) => (
                <TurnBlock key={turn.id} turn={turn} index={ordered.length - i} />
              ))}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
