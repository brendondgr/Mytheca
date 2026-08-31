"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

/** Maximum visible height before the field scrolls (~12 lines), mirroring the composer. */
const MAX_HEIGHT = 280;

/**
 * Rewrite one beat's prose in place.
 *
 * A real `<form>` with a labelled `<textarea>`, not a `contenteditable`. Contenteditable
 * would have to re-implement undo, paste handling, IME composition and screen-reader
 * semantics that a textarea gets for nothing — and this field's whole job is plain text.
 *
 * Escape cancels; ⌘/Ctrl+Enter saves. Plain Enter inserts a newline, because a beat is prose
 * and multi-paragraph edits are the common case — the opposite of the composer, where Enter
 * sends because the common case is one line.
 */
export function BeatEditor({
  initialText,
  onSave,
  onCancel,
  label = "beat",
  saving = false,
}: {
  initialText: string;
  onSave: (text: string) => void;
  onCancel: () => void;
  /** What is being edited, for the field's accessible name. */
  label?: string;
  saving?: boolean;
}) {
  const [text, setText] = useState(initialText);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fieldId = useId();

  // Focus the field and put the caret at the end — the player is amending, not restarting.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    // One read, not two: the second `scrollHeight` after the height write costs
    // a whole extra synchronous layout for an unchanged number. See Composer.
    el.style.height = "auto";
    const content = el.scrollHeight;
    el.style.height = `${Math.min(content, MAX_HEIGHT)}px`;
    el.style.overflowY = content > MAX_HEIGHT ? "auto" : "hidden";
  }, [text]);

  const dirty = text.trim() !== initialText.trim();

  return (
    <form
      className="flex flex-col gap-xs rounded-sm border border-accent bg-field p-sm"
      onSubmit={(e) => {
        e.preventDefault();
        if (dirty && text.trim()) onSave(text);
      }}
    >
      <label htmlFor={fieldId} className="font-mono text-eyebrow tracking-[0.12em] text-mute uppercase">
        Editing {label}
      </label>
      <textarea
        id={fieldId}
        ref={ref}
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
            return;
          }
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            if (dirty && text.trim()) onSave(text);
          }
        }}
        className="block w-full resize-none bg-transparent font-body text-field leading-[1.5] text-ink focus:outline-none"
        style={{ overflowY: "hidden" }}
      />
      <div className="flex items-center gap-xs">
        <button
          type="submit"
          disabled={saving || !dirty || !text.trim()}
          className="flex h-[26px] items-center rounded-xs bg-accent px-sm font-mono text-eyebrow tracking-[0.1em] text-[#F6ECDA] uppercase hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="flex h-[26px] items-center rounded-xs px-sm font-mono text-eyebrow tracking-[0.1em] text-mute uppercase hover:bg-hover hover:text-ink"
        >
          Cancel
        </button>
        <span className="ml-auto font-mono text-eyebrow tracking-[0.06em] text-mute2">
          Esc cancels · ⌘↵ saves
        </span>
      </div>
    </form>
  );
}
