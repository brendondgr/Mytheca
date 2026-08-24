"use client";

import { useId, type ReactNode, type RefObject } from "react";
import { useRememberedFlag } from "@/hooks/use-remembered-flag";

/**
 * Where the verb row's open/closed state lives. Per browser, not per scene: a player who
 * wants the verbs wants them everywhere, and one who does not should not have to close them
 * again in every scenario they open.
 */
const VERBS_OPEN_KEY = "mytheca.directionVerbs.open";

/**
 * The scene direction, always present above the message box.
 *
 * **What changes between modes is the row's *role*, never whether it exists.** Until this
 * row was unconditional, the entire direction concept was invisible to any player who had
 * not happened to pick a POV character — which is most of them.
 *
 * - **Playwright mode** — not a second textarea, but a one-line labelled strip saying that
 *   the message box below *is* the direction. There is still exactly one text input, so the
 *   two modes cannot read as duplicate fields. (The Playwright is the player steering the
 *   scene from outside it — never the Narrator, which is the AI voice inside the scene.)
 * - **POV mode** — the same row expands into the direction textarea, because the message box
 *   is now the character's own line and has nowhere left to steer from.
 *
 * The rejected alternative — a collapsed second textarea in both modes — puts two empty
 * boxes in front of a new player and makes them guess which one is "the scene". The strip
 * answers that question in words instead.
 */
export function DirectionRow({
  mode,
  value,
  onChange,
  povName,
  textareaRef,
  textareaProps,
  children,
}: {
  mode: "playwright" | "pov";
  value: string;
  onChange: (next: string) => void;
  /** The character the player is voicing, named in the POV label so the split is concrete. */
  povName?: string;
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
  /**
   * Mention plumbing (aria, key/caret handlers) owned by the composer. Only ever applied in
   * POV mode — in Playwright mode there is no textarea to attach it to. Its `onChange` runs
   * *after* `onChange` above rather than instead of it, so there is exactly one writer of
   * the value and the composer's side-effects (resize, mention sync) compose onto it.
   */
  textareaProps?: Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "ref">;
  /** Slot for the direction verb bar, which attaches to this row in both modes. */
  children?: ReactNode;
}) {
  // Closed by default. The owner's report was that the verb row "gets in the way" and that
  // they "don't even look at it half the time" — a fifteen-chip toolbar sitting above the
  // message box in every scene, permanently. Collapsing rather than deleting keeps the verbs,
  // their availability gating and any scenario-authored ones intact for the players who do
  // use them, at the cost of one click.
  const [verbsOpen, setVerbsOpen] = useRememberedFlag(VERBS_OPEN_KEY, false);
  const verbsId = useId();
  const toggleVerbs = () => setVerbsOpen(!verbsOpen);
  // `children` is the verb bar. It attaches to this row in BOTH modes, because the row is
  // the direction — what changes between modes is only which box the verb writes into, and
  // that is the parent's business (see `Composer.insertDirection`).
  return (
    <div className="mb-[6px] border-b border-field-bd pb-[6px]">
      <div className="flex flex-wrap items-center gap-x-[8px] gap-y-[3px] px-[4px]">
        <span className="font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase">
          Direction
        </span>
        <span className="font-body text-[11px] text-mute2">
          {mode === "playwright"
            ? "— this message steers the scene"
            : `— ${povName ? `${povName} speaks below` : "your character speaks below"}`}
        </span>
        {/* The verbs, behind a disclosure. When closed the bar is UNMOUNTED rather than
            hidden, so its fifteen chips leave the tab order entirely — a visually-collapsed
            toolbar that still swallows keyboard focus is worse than no disclosure at all. */}
        {children ? (
          <>
            <button
              type="button"
              onClick={toggleVerbs}
              aria-expanded={verbsOpen}
              aria-controls={verbsOpen ? verbsId : undefined}
              className="min-h-[24px] flex-none rounded-[6px] border border-field-bd px-[7px] py-[2px] font-mono text-[9px] tracking-[0.06em] text-mute2 uppercase hover:bg-hover hover:text-ink aria-expanded:border-accent aria-expanded:text-accent"
            >
              <span aria-hidden className="mr-[3px]">{verbsOpen ? "−" : "+"}</span>
              Verbs
            </button>
            {verbsOpen ? <div id={verbsId} className="contents">{children}</div> : null}
          </>
        ) : null}
      </div>
      {mode === "pov" ? (
        <textarea
          {...textareaProps}
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            textareaProps?.onChange?.(e);
          }}
          aria-label="Scene direction"
          placeholder="Tell the scene what should happen — as vague or as exact as you like"
          className="composer-input mt-[2px] block w-full resize-none bg-transparent px-[4px] py-[2px] font-body text-[13px] text-mute placeholder:text-mute2 focus:outline-none"
          style={{ overflowY: "hidden" }}
        />
      ) : null}
    </div>
  );
}
