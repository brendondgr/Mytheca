"use client";

/**
 * **Thinking** — how hard the model works something out before it writes this message.
 *
 * The six budgets have always existed in the backend; every call site fixed its own and none
 * of them was ever the player's to move. This puts one of them — the prose call's — in the
 * composer, per message, beside Plan mode.
 *
 * Per message and **not** per scene, and that is the same argument the pinned register makes:
 * how much thought a particular line is worth belongs to the moment, not to the world. A
 * scene-level default would be wrong by the second turn.
 *
 * **`Default` is not a seventh level.** It means "leave the call site's own budget alone",
 * which is a different request from asking for the lowest one — the structured engine's prose
 * call runs with thinking OFF, after it was measured spending 91 % of its output on hidden
 * reasoning nobody reads, and a player who never touched this control must not silently
 * switch that back on.
 *
 * Opens into a popover rather than expanding in place like {@link PlanModeButton}: seven
 * choices is a list, and seven chips inline would push the composer's own controls off the
 * row on a narrow screen.
 */

import { useEffect, useRef } from "react";
import { Icon } from "@/components/ui/Icon";

/** The six budgets, as the wire names them. Mirrors the backend `ThinkingLevel`. */
export type ThinkingLevel = "quick" | "low" | "medium" | "high" | "very_high" | "max";

/** Short names, and the token budget each one actually buys. */
const LEVELS: { value: ThinkingLevel; label: string; tokens: number }[] = [
  { value: "quick", label: "Very low", tokens: 128 },
  { value: "low", label: "Low", tokens: 256 },
  { value: "medium", label: "Medium", tokens: 512 },
  { value: "high", label: "High", tokens: 1024 },
  { value: "very_high", label: "Extra high", tokens: 2048 },
  { value: "max", label: "Max", tokens: 4096 },
];

const LABEL_OF = new Map(LEVELS.map((l) => [l.value, l.label]));

/** What the choice costs and buys, as a consequence rather than a number. */
const HELP =
  "How long the model works out what to write before it starts. More thinking usually reads as a better-judged scene and always means a longer wait.";

export function ThinkingButton({
  level = null,
  onLevelChange,
  open,
  onOpenChange,
  disabled = false,
}: {
  /** `null` — the default — leaves each call site's own budget alone. */
  level?: ThinkingLevel | null;
  onLevelChange: (level: ThinkingLevel | null) => void;
  /** Controlled disclosure, so the parent can close it when a turn starts. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  disabled?: boolean;
}) {
  const box = useRef<HTMLDivElement | null>(null);

  // Close on an outside click, like every other composer popover. Bound only while open, so
  // a scene with the control closed adds no document listener at all.
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) onOpenChange(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open, onOpenChange]);

  const label = level ? LABEL_OF.get(level) : "Default";

  return (
    <div ref={box} className="relative flex-none">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="true"
        // The name carries the setting AND what it does — "Thinking: Medium" alone says what
        // it is called, never what it will change.
        aria-label={`Thinking: ${label}. ${HELP}`}
        title={HELP}
        className="flex flex-none items-center gap-2xs rounded-md border border-field-bd px-sm py-2xs font-mono text-eyebrow tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-field-bd disabled:hover:text-mute"
      >
        <Icon name="think" size={12} />
        {label}
      </button>

      {open ? (
        <div
          role="radiogroup"
          aria-label="Thinking"
          // `mytheca-menu` is the house popover surface — the same border, ground and shadow
          // every other menu in the app uses, so this one cannot drift from them on a theme
          // change. Opens UPWARD: it lives on the composer row at the bottom of the screen.
          //
          // Anchored to the trigger's RIGHT edge, not its left. The composer row wraps as it
          // narrows, and at 320px this control sits about 186px in — a left-anchored 210px
          // panel then ran to 396px, three quarters of it past the edge of a 320px screen and
          // unreachable, because the row clips rather than scrolls. Growing leftward keeps it
          // on screen at every width, and costs nothing on a wide one.
          className="mytheca-menu absolute right-0 bottom-2xl z-30 w-[210px] p-xs"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onOpenChange(false);
            }
          }}
        >
          {[{ value: null, label: "Default", tokens: 0 }, ...LEVELS].map((row) => {
            const active = level === row.value;
            return (
              <button
                key={row.label}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={disabled}
                onClick={() => {
                  onLevelChange(row.value as ThinkingLevel | null);
                  onOpenChange(false);
                }}
                className={`flex w-full items-baseline justify-between gap-sm rounded-sm px-sm py-2xs text-left font-mono text-eyebrow tracking-[0.08em] uppercase disabled:opacity-40 ${
                  active ? "bg-accent text-[#F6ECDA]" : "text-mute hover:bg-hover hover:text-ink"
                }`}
              >
                <span>{row.label}</span>
                {/* The budget itself, quietly. It is the only honest way to say that Max is
                    thirty-two times Very low rather than one notch further along. */}
                <span className="opacity-70">{row.tokens ? row.tokens : "—"}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
