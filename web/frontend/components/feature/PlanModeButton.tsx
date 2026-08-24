"use client";

/**
 * **Plan mode** — whether the scene's plan runs straight through, or waits for you.
 *
 * Planning already existed; it lived at the bottom of a seven-control popover as "Turn
 * planning: On / Off", where it read as a performance setting and nobody touched it. It is a
 * decision about *how you play* — whether the story commits to what happens next or shows
 * you first — so it belongs in the composer beside the POV select, one click from the
 * message box.
 *
 * Collapsed it shows the mode in a word. Activated it expands in place into the two choices:
 *
 * - **Auto** — the plan is approved automatically and the turn plays out. Today's behaviour.
 * - **Plan** — the turn stops after planning and shows you who acts and what they do, and
 *   nothing is written until you approve it.
 *
 * **`off` is deliberately not here.** Turning planning off changes what the app *is* — no
 * director reads the moment, no register, no narrator beats between speakers — which is not
 * a third position on a two-way toggle about approval. It stays in the Config popover, and
 * this control renders as a disabled, honest label while it is set.
 *
 * Expands in place rather than into a popover: two options do not need a menu, and a popover
 * over the composer would cover the very transcript the choice is about.
 */

export type PlanMode = "auto" | "plan" | "off";

/** A clipboard-with-a-tick: the plan, as a thing you sign off. */
function PlanIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M9 3h6a1 1 0 0 1 1 1v1H8V4a1 1 0 0 1 1-1Z" />
      <path d="M16 5h1a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h1" />
      <path d="m9 13 2 2 4-4" />
    </svg>
  );
}

const LABELS: Record<PlanMode, string> = {
  auto: "Auto",
  plan: "Plan",
  off: "No plan",
};

/** What each mode actually does, in a consequence rather than a name. */
const HELP: Record<PlanMode, string> = {
  auto: "The scene plans each turn and plays it out without stopping.",
  plan: "The scene plans each turn and waits for you to approve it before writing anything.",
  off: "Planning is off for this scene — nobody reads the moment. Change it in Config.",
};

export function PlanModeButton({
  mode = "auto",
  onModeChange,
  open,
  onOpenChange,
  disabled = false,
}: {
  mode?: PlanMode;
  onModeChange: (mode: PlanMode) => void;
  /** Controlled disclosure, so the parent can close it when a turn starts. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  disabled?: boolean;
}) {
  // With planning off there is nothing to approve, so the control states that rather than
  // offering two choices that would both be lies.
  const inert = mode === "off";

  if (!open || inert) {
    return (
      <button
        type="button"
        onClick={() => onOpenChange(true)}
        disabled={disabled || inert}
        aria-expanded={inert ? undefined : false}
        // The accessible name carries the mode AND its consequence: "Plan mode: Auto" alone
        // tells a screen-reader user what it is called, never what it will do.
        aria-label={`Plan mode: ${LABELS[mode]}. ${HELP[mode]}`}
        title={HELP[mode]}
        className="flex flex-none items-center gap-[5px] rounded-[8px] border border-field-bd px-[9px] py-[5px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-field-bd disabled:hover:text-mute"
      >
        <PlanIcon />
        {LABELS[mode]}
      </button>
    );
  }

  return (
    <div
      role="radiogroup"
      aria-label="Plan mode"
      className="flex flex-none items-center gap-[3px] rounded-[8px] border border-accent p-[2px]"
      // Escape closes without choosing — the same affordance every other popover here has.
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          onOpenChange(false);
        }
      }}
    >
      {(["auto", "plan"] as const).map((value) => {
        const active = mode === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            title={HELP[value]}
            onClick={() => {
              onModeChange(value);
              onOpenChange(false);
            }}
            className={`rounded-[6px] px-[8px] py-[3px] font-mono text-[9px] tracking-[0.12em] uppercase disabled:opacity-40 ${
              active
                ? "bg-accent text-[#F6ECDA]"
                : "text-mute hover:bg-hover hover:text-ink"
            }`}
          >
            {LABELS[value]}
          </button>
        );
      })}
    </div>
  );
}
