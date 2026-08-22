"use client";

import type { ReactNode, RefObject } from "react";

/**
 * The scene direction, always present above the message box.
 *
 * **What changes between modes is the row's *role*, never whether it exists.** Until this
 * row was unconditional, the entire direction concept was invisible to any player who had
 * not happened to pick a POV character — which is most of them.
 *
 * - **Narrator mode** — not a second textarea, but a one-line labelled strip saying that the
 *   message box below *is* the direction. There is still exactly one text input, so the two
 *   modes cannot read as duplicate fields.
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
  mode: "narrator" | "pov";
  value: string;
  onChange: (next: string) => void;
  /** The character the player is voicing, named in the POV label so the split is concrete. */
  povName?: string;
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
  /**
   * Mention plumbing (aria, key/caret handlers) owned by the composer. Only ever applied in
   * POV mode — in narrator mode there is no textarea to attach it to. Its `onChange` runs
   * *after* `onChange` above rather than instead of it, so there is exactly one writer of
   * the value and the composer's side-effects (resize, mention sync) compose onto it.
   */
  textareaProps?: Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "ref">;
  /** Slot for the direction verb bar, which attaches to this row in both modes. */
  children?: ReactNode;
}) {
  return (
    <div className="mb-[6px] border-b border-field-bd pb-[6px]">
      <div className="flex flex-wrap items-center gap-x-[8px] gap-y-[3px] px-[4px]">
        <span className="font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase">
          Direction
        </span>
        <span className="font-body text-[11px] text-mute2">
          {mode === "narrator"
            ? "— this message steers the scene"
            : `— ${povName ? `${povName} speaks below` : "your character speaks below"}`}
        </span>
        {children}
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
          placeholder="Guide the scene — what happens next…"
          className="composer-input mt-[2px] block w-full resize-none bg-transparent px-[4px] py-[2px] font-body text-[13px] text-mute placeholder:text-mute2 focus:outline-none"
          style={{ overflowY: "hidden" }}
        />
      ) : null}
    </div>
  );
}
