import { useLayoutEffect, useRef, type RefObject } from "react";
import { SceneConfigMenu } from "@/components/feature/SceneConfigMenu";
import { ContextUsageDial } from "@/components/feature/ContextUsageDial";

/** Maximum visible height of the textarea before it becomes scrollable (~10 lines). */
const MAX_HEIGHT = 240;

/**
 * Bottom composer — one panel, two rows:
 *   • Row 1: the auto-growing message textarea (Enter sends / Shift+Enter newline).
 *   • Row 2: a controls bar — Config on the left (with room reserved for future options),
 *     and on the right the circular context dial then the "Send →" pill.
 * The textarea stays editable while a turn streams; only sending is blocked (`sendDisabled`).
 */
export function Composer({
  value,
  onChange,
  onSend,
  sendDisabled = false,
  inputRef,
  // Scene config (rendered on the bottom-left when at least one handler is supplied).
  maxTurns,
  onMaxTurnsChange,
  suggestionsCount,
  onSuggestionsCountChange,
  contextBeats,
  onContextBeatsChange,
  beatTexts,
  // Context dial (rendered when the model's window size is known).
  usedTokens = 0,
  maxContextTokens = null,
  usedTokensExact = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /**
   * When true, only sending is blocked (button disabled + Enter guarded).
   * The textarea stays editable so the player can keep typing while a turn streams.
   */
  sendDisabled?: boolean;
  /** Lets the parent move focus here after a suggestion is written into the box. */
  inputRef?: RefObject<HTMLTextAreaElement | null>;
  maxTurns?: number;
  onMaxTurnsChange?: (value: number) => void;
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  contextBeats?: number;
  onContextBeatsChange?: (value: number) => void;
  /** Real transcript beats (one string each) — feeds the config's content-real readout. */
  beatTexts?: string[];
  /** Used tokens for the context dial (exact when `usedTokensExact`, else the estimate). */
  usedTokens?: number;
  /** The model's context-window size; `null` hides the dial (unknown limit). */
  maxContextTokens?: number | null;
  /** True when `usedTokens` is the model's reported `usage.prompt_tokens`. */
  usedTokensExact?: boolean;
}) {
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const ref = (inputRef as RefObject<HTMLTextAreaElement>) ?? internalRef;

  const hasConfig = Boolean(
    onMaxTurnsChange ?? onSuggestionsCountChange ?? onContextBeatsChange,
  );

  /** Resize the textarea to fit its content, capped at MAX_HEIGHT. */
  function resize(el: HTMLTextAreaElement) {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? "auto" : "hidden";
  }

  // Re-run resize whenever `value` changes externally (e.g. suggestion select).
  useLayoutEffect(() => {
    const el = ref.current;
    if (el) resize(el);
  }, [value, ref]);

  return (
    /* Outer band: transparent, no background — just positions the centered panel. */
    <div className="flex-none px-[16px] pb-[16px] sm:px-[30px] sm:pb-[20px]">
      {/* The single visual unit: the chat box panel (textarea row + controls row). */}
      <div className="mx-auto max-w-[720px] rounded-[14px] border border-field-bd bg-field focus-within:border-accent transition-colors duration-150">
        {/* Row 1 — the message input. */}
        <textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            resize(e.currentTarget);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!sendDisabled && value.trim()) onSend();
            }
          }}
          // textarea is always enabled — only send is blocked while streaming
          aria-label="Your message"
          placeholder={sendDisabled ? "The scene responds…" : "Speak, or describe what you do…"}
          className="block w-full resize-none bg-transparent p-[12px_14px] font-body text-[15px] text-ink placeholder:text-mute2 focus:outline-none"
          style={{ overflowY: "hidden" }}
        />

        {/* Row 2 — the controls bar. */}
        <div className="flex items-center gap-[8px] border-t border-field-bd px-[10px] py-[7px]">
          {/* Left: Config (+ blank space reserved for future options). */}
          {hasConfig ? (
            <SceneConfigMenu
              maxTurns={maxTurns}
              onMaxTurnsChange={onMaxTurnsChange}
              suggestionsCount={suggestionsCount}
              onSuggestionsCountChange={onSuggestionsCountChange}
              contextBeats={contextBeats}
              onContextBeatsChange={onContextBeatsChange}
              beatTexts={beatTexts}
              openUp
            />
          ) : null}
          <div className="min-w-0 flex-1" />

          {/* Right cluster: context dial, then the Send pill. */}
          <ContextUsageDial
            usedTokens={usedTokens}
            maxTokens={maxContextTokens ?? 0}
            exact={usedTokensExact}
            size={34}
          />
          <button
            type="button"
            onClick={onSend}
            disabled={sendDisabled}
            aria-label="Send"
            className="flex flex-none items-center gap-[6px] rounded-[9px] bg-accent px-[15px] py-[8px] font-mono text-[11px] tracking-[0.08em] text-[#F6ECDA] uppercase transition-[filter] hover:brightness-110 disabled:opacity-50 disabled:hover:brightness-100"
          >
            Send
            {/* Right-arrow — matches the reference "Send →". */}
            <svg
              aria-hidden="true"
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path d="M2.5 7h9M8 3.5 11.5 7 8 10.5" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
