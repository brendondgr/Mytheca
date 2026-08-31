"use client";

import { cn } from "@/lib/cn";

export interface ProcessStep {
  key: string;
  label: string;
}

/**
 * Compact stage indicator for an agentic run: shows every major step with a
 * done / active / pending state plus a "Now … · Next …" line, so the author
 * always knows where the process is and what comes next. `activeKey` names the
 * step in progress (earlier steps read as done, later as pending); `null` before
 * the run starts, and — once every step is finished — pass a key not in `steps`
 * (or leave the last step active) to show completion. The status line is an
 * `aria-live` region so the change is announced.
 */
export function ProcessProgress({
  steps,
  activeKey,
  done = false,
  className,
  label = "Progress",
}: {
  steps: ProcessStep[];
  activeKey: string | null;
  /** Force the completed state (all steps done, no active step). */
  done?: boolean;
  className?: string;
  label?: string;
}) {
  const activeIndex = activeKey ? steps.findIndex((s) => s.key === activeKey) : -1;
  const current = activeIndex >= 0 ? steps[activeIndex] : null;
  const next =
    activeIndex >= 0 && activeIndex + 1 < steps.length
      ? steps[activeIndex + 1]
      : null;

  function stateOf(i: number): "done" | "active" | "pending" {
    if (done) return "done";
    if (activeIndex < 0) return "pending";
    if (i < activeIndex) return "done";
    if (i === activeIndex) return "active";
    return "pending";
  }

  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        "rounded-sm border border-cardbd bg-card2/50 px-3 py-2",
        className,
      )}
    >
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {steps.map((s, i) => {
          const state = stateOf(i);
          return (
            <li
              key={s.key}
              data-state={state}
              className="flex items-center gap-1.5"
            >
              <span
                aria-hidden
                className={cn(
                  "h-2 w-2 flex-none rounded-full",
                  state === "done" && "bg-success",
                  state === "active" &&
                    "bg-accent animate-pulse motion-reduce:animate-none",
                  state === "pending" && "bg-cardbd",
                )}
              />
              <span
                className={cn(
                  "font-mono text-eyebrow",
                  state === "active" ? "text-ink" : "text-ink-soft",
                  state === "done" && "line-through opacity-70",
                )}
              >
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>
      <p
        aria-live="polite"
        className="mt-1 font-body text-eyebrow text-ink-soft"
      >
        {done || (activeIndex < 0 && steps.length > 0 && !current) ? (
          done ? (
            "Complete"
          ) : (
            "Ready"
          )
        ) : current ? (
          <>
            Now: <span className="text-ink">{current.label}</span>
            {next ? <> · Next: {next.label}</> : null}
          </>
        ) : (
          "Ready"
        )}
      </p>
    </div>
  );
}
