"use client";

import { useState } from "react";
import { CloseButton } from "@/components/ui/CloseButton";
import type { TraceTurn } from "@/features/story-player/turn-stream";
import type { TurnTraceFrame } from "@/lib/events";

// Per-step display: a short tag + a category color for the dot on the left. Colour is
// redundant with the tag text (never colour-alone), so the WHAT of each row reads at a
// glance — Stat / Plan / Speaker / Thinks / Speaks … — and stays legible without colour.
const STEP_META: Record<string, { tag: string; color: string }> = {
  turn: { tag: "You", color: "var(--accent)" },
  intent: { tag: "Intent", color: "#8b5cf6" },
  assemble: { tag: "Scene", color: "#64748b" },
  lore: { tag: "Lore", color: "#0ea5e9" },
  // The player's @-tagged context files — distinct from `lore`, which is the gated
  // retrieval the engine decides on by itself.
  files: { tag: "Files", color: "#0d9488" },
  plan: { tag: "Plan", color: "#d97706" },
  director: { tag: "Director", color: "#d97706" },
  speaker: { tag: "Speaker", color: "#2563eb" },
  thinking: { tag: "Thinks", color: "#7c3aed" },
  // Historical only — the continuity guard was retired (it cost ~10s per later
  // speaker and blocked their prose from streaming). Kept so traces recorded
  // before that still render with a label instead of a raw step name.
  consistency: { tag: "Check", color: "#64748b" },
  relationship: { tag: "Ties", color: "#db2777" },
  action: { tag: "Acts", color: "#0891b2" },
  prose: { tag: "Writes", color: "#059669" },
  dialogue: { tag: "Speaks", color: "#059669" },
  stat: { tag: "Stat", color: "#ca8a04" },
  relationship_change: { tag: "Bond", color: "#db2777" },
  branch: { tag: "Branch", color: "#d97706" },
  relationships: { tag: "Graph", color: "#16a34a" },
  commit: { tag: "Graph", color: "#16a34a" },
  reflection: { tag: "Reflect", color: "#64748b" },
};

function tagFor(step: string): { tag: string; color: string } {
  return STEP_META[step] ?? { tag: step, color: "#64748b" };
}

/**
 * One trace step: a colored dot + tag + title on the left; a click expands a dropdown
 * to reveal the plain-language detail (feedback #5). Rows with no detail are inert.
 */
function StepRow({ step }: { step: TurnTraceFrame }) {
  const [open, setOpen] = useState(false);
  const meta = tagFor(step.step);
  const hasDetail = Boolean(step.detail);
  return (
    <li>
      <button
        type="button"
        onClick={() => hasDetail && setOpen((o) => !o)}
        aria-expanded={hasDetail ? open : undefined}
        disabled={!hasDetail}
        className="flex w-full items-start gap-[9px] py-[8px] text-left disabled:cursor-default"
      >
        <span
          aria-hidden
          className="mt-[6px] h-[9px] w-[9px] flex-none rounded-full"
          style={{ backgroundColor: meta.color }}
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-[8px]">
            <span
              className="flex-none font-mono text-[10px] tracking-[0.08em] uppercase"
              style={{ color: meta.color }}
            >
              {meta.tag}
            </span>
            <span className="min-w-0 flex-1 font-body text-[14px] leading-[1.4] text-ink">
              {step.title}
            </span>
            {hasDetail ? (
              <span aria-hidden className="flex-none font-mono text-[11px] text-mute2">
                {open ? "▾" : "▸"}
              </span>
            ) : null}
          </span>
          {open && step.detail ? (
            <span className="mt-[5px] block font-body text-[13px] leading-[1.5] text-ink-soft">
              {step.detail}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}

/** One turn: a clickable header (collapses when a newer turn opens), then its steps. */
function TurnBlock({
  turn,
  index,
  open,
  onToggle,
}: {
  turn: TraceTurn;
  index: number;
  open: boolean;
  onToggle: () => void;
}) {
  const steps = turn.steps.filter((s) => s.step !== "turn");
  return (
    <section className="rounded-[4px] border border-cardbd bg-card2">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={`flex w-full items-baseline gap-[8px] p-[10px_12px] text-left ${
          open ? "border-b border-cardbd" : ""
        }`}
      >
        <span className="flex-none font-mono text-[10px] tracking-[0.1em] text-mute2 uppercase">
          Turn {index}
        </span>
        <span className="min-w-0 flex-1 truncate font-body text-[13px] text-ink-soft">
          {turn.label || "(turn)"}
        </span>
        <span className="flex-none font-mono text-[10px] text-mute2">{steps.length}</span>
        <span aria-hidden className="flex-none font-mono text-[11px] text-mute2">
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open ? (
        <ol className="divide-y divide-cardbd/60 p-[2px_12px_8px]">
          {steps.map((s) => (
            <StepRow key={s.n} step={s} />
          ))}
        </ol>
      ) : null}
    </section>
  );
}

/**
 * A docked right-side column that explains the turn loop, in order, after each message:
 * the intent read from your input, which characters the planner picked and why, their
 * private thinking, stat + relationship changes, the graph commit, and the reflection
 * step. It sits to the right of the current rail (the chat stays visible), newest turn
 * first. The active (newest) turn is expanded; completed turns collapse to a header you
 * can click open. Read-only diagnostics — the panel never changes the scene.
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
  const latestId = turns.length ? turns[turns.length - 1].id : null;
  // Accordion: the active (newest) turn is open; older turns auto-collapse once a newer
  // one begins. Clicking a header opens that turn (and closes the others). When a newer
  // turn arrives we re-open it by adjusting state during render (the documented pattern
  // for deriving from a changed value — no effect, no extra commit).
  const [openId, setOpenId] = useState<string | null>(latestId);
  const [seenLatest, setSeenLatest] = useState<string | null>(latestId);
  if (latestId !== seenLatest) {
    setSeenLatest(latestId);
    setOpenId(latestId);
  }

  if (!open) return null;
  const ordered = [...turns].reverse(); // newest turn at the top

  return (
    <aside
      aria-label="Turn inspector"
      // A flat w-[340px] with no breakpoint was the one panel in the app that
      // could not fit a 320px viewport — it is the only rail rendered outside
      // an `lg:` gate, so on a phone it pushed the transcript off-screen.
      // Below `sm` it takes the full width (the diagnostic IS the view while
      // it is open); from `sm` up it returns to its docked 340px column.
      className="flex w-full flex-none flex-col border-l border-hair-strong bg-page sm:w-[340px]"
    >
      <header className="flex flex-none items-start justify-between gap-3 border-b border-hair-strong p-[14px_16px]">
        <div>
          <h2 className="font-display text-[15px] font-bold leading-none text-ink">
            Turn Inspector
          </h2>
          <p className="mt-[6px] font-mono text-[9px] leading-[1.5] tracking-[0.08em] text-mute uppercase">
            What happens, step by step, per message
          </p>
        </div>
        <CloseButton onClose={onClose} className="relative" />
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-[12px_14px]">
        {ordered.length === 0 ? (
          <p className="mt-[8px] font-body text-[14px] leading-[1.5] text-ink-soft">
            Send a message in the scene and the flow will appear here — the intent read from
            your input, the planner&apos;s choice of who speaks and why, each character&apos;s
            private thinking, any lore look-up, stat + relationship changes, the story-graph
            commit, and the reflection step that sets up the next turn. Tap a step to expand it.
          </p>
        ) : (
          <div className="flex flex-col gap-[12px]">
            {ordered.map((turn, i) => (
              <TurnBlock
                key={turn.id}
                turn={turn}
                index={ordered.length - i}
                open={openId === turn.id}
                onToggle={() => setOpenId((cur) => (cur === turn.id ? null : turn.id))}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
