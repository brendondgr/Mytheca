import { useLayoutEffect, useRef, type RefObject } from "react";
import { SceneConfigMenu } from "@/components/feature/SceneConfigMenu";
import { PovSelect, type PovOption } from "@/components/feature/PovSelect";
import { ContextUsageDial } from "@/components/feature/ContextUsageDial";

/** Maximum visible height of the textarea before it becomes scrollable (~10 lines). */
const MAX_HEIGHT = 240;

/**
 * Bottom composer — one continuous panel, two stacked areas:
 *   • the auto-growing message textarea (Enter sends / Shift+Enter newline), then a gap,
 *   • a compact controls bar — Config on the left (room reserved for future options),
 *     and on the right the circular context dial then a small "Send →" pill.
 * The panel shows a single accent border on focus-within; the textarea itself has no
 * focus outline (that boxy ring is suppressed). The textarea stays editable while a turn
 * streams; only sending is blocked (`sendDisabled`).
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
  // Player POV (rendered to the right of Config when a handler is supplied).
  pov = null,
  onPovChange,
  povOptions = [],
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
  /** Player POV: the id of the character the player is speaking AS (`null` = Narrator). */
  pov?: string | null;
  onPovChange?: (id: string | null) => void;
  /** The present cast members the player may speak as (id + name). */
  povOptions?: PovOption[];
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

  // Placeholder reflects the active POV: "Speaking as Mei…" when the player has chosen a
  // character to voice, else the default guide/narrator prompt.
  const povName = pov ? povOptions.find((o) => o.id === pov)?.name : undefined;
  const placeholder = sendDisabled
    ? "The scene responds…"
    : povName
      ? `Speaking as ${povName}…`
      : "Speak, or describe what you do…";

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
    <div className="flex-none px-[16px] pb-[12px] sm:px-[30px] sm:pb-[14px]">
      {/* The single visual unit: the chat box panel (input area + gap + controls). */}
      <div className="mx-auto flex max-w-[720px] flex-col rounded-[14px] border border-field-bd bg-field px-[10px] pt-[8px] pb-[7px] focus-within:border-accent transition-colors duration-150">
        {/* The message input — no focus outline (the container carries the accent border). */}
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
          placeholder={placeholder}
          className="composer-input block w-full resize-none bg-transparent px-[4px] pt-[2px] pb-[8px] font-body text-[14px] text-ink placeholder:text-mute2 focus:outline-none"
          style={{ overflowY: "hidden" }}
        />

        {/* Controls bar — sits a gap below the textarea, no dividing line. */}
        <div className="flex items-center gap-[7px]">
          {/* Left: Config, then the Player POV "Speaking as" select to its right. */}
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
          {onPovChange ? (
            <PovSelect pov={pov} onPovChange={onPovChange} options={povOptions} />
          ) : null}
          <div className="min-w-0 flex-1" />

          {/* Right cluster: context dial, then the small Send pill. */}
          <ContextUsageDial
            usedTokens={usedTokens}
            maxTokens={maxContextTokens ?? 0}
            exact={usedTokensExact}
            size={24}
          />
          <button
            type="button"
            onClick={onSend}
            disabled={sendDisabled}
            aria-label="Send"
            className="flex flex-none items-center gap-[5px] rounded-[8px] bg-accent px-[11px] py-[5px] font-mono text-[10px] tracking-[0.08em] text-[#F6ECDA] uppercase transition-[filter] hover:brightness-110 disabled:opacity-50 disabled:hover:brightness-100"
          >
            Send
            {/* Right-arrow — matches the reference "Send →". */}
            <svg
              aria-hidden="true"
              width="12"
              height="12"
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
