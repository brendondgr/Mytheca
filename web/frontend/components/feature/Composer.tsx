import { useId, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { SceneConfigMenu } from "@/components/feature/SceneConfigMenu";
import { PovSelect, type PovOption } from "@/components/feature/PovSelect";
import { GhostwriteButton } from "@/components/feature/GhostwriteButton";
import { ContextUsageDial } from "@/components/feature/ContextUsageDial";
import { MentionMenu } from "@/components/feature/MentionMenu";
import {
  applyMention,
  filterMentions,
  findMentionQuery,
  stripMentions,
  type MentionOption,
} from "@/features/story-player/mentions";
import type { BeatLength } from "@/lib/types";

/** Maximum visible height of the textarea before it becomes scrollable (~10 lines). */
const MAX_HEIGHT = 240;

/**
 * Maximum visible height of the scene-direction box (~5 lines). Deliberately shorter than
 * the message box: direction is a note to the scene, not the line the player is performing.
 */
const GUIDANCE_MAX_HEIGHT = 120;

/**
 * Bottom composer — one continuous panel, stacked areas:
 *   • (Player POV only) the scene-direction textarea, above a hairline rule — see below,
 *   • the auto-growing message textarea (Enter sends / Shift+Enter newline), then a gap,
 *   • a compact controls bar — Config on the left (room reserved for future options),
 *     and on the right the circular context dial then a small "Send →" pill.
 * The panel shows a single accent border on focus-within; the textareas themselves have no
 * focus outline (that boxy ring is suppressed). Both stay editable while a turn streams;
 * only sending is blocked (`sendDisabled`).
 *
 * **The scene-direction box** appears only while the player is speaking AS a character
 * (`pov` set) and `onGuidanceChange` is wired. In narrator mode the message box already is
 * the narrator's box — its text *is* the direction — so a second one would duplicate it.
 * Under POV the message box holds the character's own line, which leaves nowhere to steer
 * the scene from; this is that place. The panel grows upward as it fills, so opening it
 * lifts the transcript rather than covering it.
 */
export function Composer({
  value,
  onChange,
  onSend,
  sendDisabled = false,
  inputRef,
  // Scene direction (Player POV only) — the narrator's box, above the message box.
  guidance = "",
  onGuidanceChange,
  // Scene config (rendered on the bottom-left when at least one handler is supplied).
  maxTurns,
  onMaxTurnsChange,
  suggestionsCount,
  onSuggestionsCountChange,
  contextBeats,
  beatLength,
  onBeatLengthChange,
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
  // Ghostwriter (rendered when a handler is supplied, so existing renders are unchanged).
  onGhostwrite,
  onUndoGhostwrite,
  ghostwriting = false,
  canUndoGhostwrite = false,
  // `@` file tagging (omit to disable the feature entirely).
  mentionOptions = [],
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
  /**
   * The narrator direction for this turn — what should happen next and how the cast should
   * react. Rendered only under Player POV (see the component doc); as vague or as specific
   * as the player likes.
   */
  guidance?: string;
  /** Omit to hide the scene-direction box entirely. */
  onGuidanceChange?: (value: string) => void;
  maxTurns?: number;
  onMaxTurnsChange?: (value: number) => void;
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  contextBeats?: number;
  beatLength?: BeatLength;
  onBeatLengthChange?: (value: BeatLength) => void;
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
  /**
   * The storyline's context documents, taggable with `@`. Empty (the default) disables the
   * menu, so every existing render is unchanged. The tagged set is **not** a prop: it is
   * derived from the text in the boxes (see `stripMentions`), which is the same function
   * the parent uses to build the request — so what the chips show is exactly what is sent,
   * and hand-deleting an `@name` untags it with no state to reconcile.
   */
  /**
   * Turn the note in the message box into the line itself. Omit to hide the control — the
   * box is the input, so the button is disabled until there is something in it.
   */
  onGhostwrite?: () => void;
  onUndoGhostwrite?: () => void;
  ghostwriting?: boolean;
  canUndoGhostwrite?: boolean;
  mentionOptions?: MentionOption[];
}) {
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const ref = (inputRef as RefObject<HTMLTextAreaElement>) ?? internalRef;
  const guidanceRef = useRef<HTMLTextAreaElement>(null);

  const hasConfig = Boolean(
    onMaxTurnsChange ?? onSuggestionsCountChange ?? onContextBeatsChange ?? onBeatLengthChange,
  );
  // The direction box belongs to POV mode only — in narrator mode the message box below
  // already carries the direction.
  const showGuidance = Boolean(onGuidanceChange) && Boolean(pov);

  // Placeholder reflects the active POV: "Speaking as Mei…" when the player has chosen a
  // character to voice, else the default guide/narrator prompt.
  const povName = pov ? povOptions.find((o) => o.id === pov)?.name : undefined;
  const placeholder = sendDisabled
    ? "The scene responds…"
    : povName
      ? `Speaking as ${povName}…`
      : "Speak, or describe what you do…";

  /** Resize a textarea to fit its content, capped at `max`. */
  function resize(el: HTMLTextAreaElement, max = MAX_HEIGHT) {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  }

  // Re-run resize whenever `value` changes externally (e.g. suggestion select).
  useLayoutEffect(() => {
    const el = ref.current;
    if (el) resize(el);
  }, [value, ref]);

  // Same for the direction box — it is cleared on send and on leaving POV, both external.
  useLayoutEffect(() => {
    const el = guidanceRef.current;
    if (el) resize(el, GUIDANCE_MAX_HEIGHT);
  }, [guidance, showGuidance]);

  // ---- `@` file tagging ----------------------------------------------------------
  // Which box holds the open mention, where its `@` sits, and what has been typed after it.
  type MentionField = "message" | "guidance";
  const [mention, setMention] = useState<
    { field: MentionField; start: number; query: string } | null
  >(null);
  const [activeIndex, setActiveIndex] = useState(0);
  // Escape closes the menu without clearing the text; remember which `@` was dismissed so
  // the next keystroke does not immediately reopen the same one.
  const dismissedRef = useRef<{ field: MentionField; start: number } | null>(null);
  // Where to put the caret after an insertion rewrites the value through the parent.
  const pendingCaret = useRef<{ field: MentionField; caret: number } | null>(null);
  const listboxId = useId();
  const optionId = (i: number) => `${listboxId}-opt-${i}`;

  const tagging = mentionOptions.length > 0;
  const matches = mention ? filterMentions(mentionOptions, mention.query) : [];
  const menuOpen = tagging && matches.length > 0;

  /** Keys the open menu owns — re-syncing on their keyup would undo what they just did. */
  const MENU_KEYS = new Set(["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"]);

  /** Recompute the open mention from a textarea's current text + caret. */
  function syncMention(field: MentionField, el: HTMLTextAreaElement) {
    if (!tagging) return;
    const found = findMentionQuery(el.value, el.selectionStart ?? el.value.length);
    const dismissed = dismissedRef.current;
    if (found && dismissed && dismissed.field === field && dismissed.start === found.start) {
      setMention(null);
      return;
    }
    dismissedRef.current = null;
    const next = found ? { field, start: found.start, query: found.query } : null;
    setMention(next);
    // Only restart the highlight when the query actually changed — an unrelated re-sync
    // (a caret nudge, a keyup) must not undo the player's arrow-key selection.
    setActiveIndex((prev) =>
      mention && next && mention.field === next.field && mention.query === next.query ? prev : 0,
    );
  }

  /** Insert the chosen file's name over the open `@query` run. */
  function selectMention(option: MentionOption) {
    if (!mention) return;
    const field = mention.field;
    const el = field === "guidance" ? guidanceRef.current : ref.current;
    if (!el) return;
    const edit = applyMention(
      el.value,
      mention.start,
      el.selectionStart ?? el.value.length,
      option.name,
    );
    if (field === "guidance") onGuidanceChange?.(edit.text);
    else onChange(edit.text);
    pendingCaret.current = { field, caret: edit.caret };
    setMention(null);
    setActiveIndex(0);
  }

  // Restore the caret after an insertion — the value round-trips through the parent, so the
  // browser would otherwise drop it to the end of the text.
  useLayoutEffect(() => {
    const pending = pendingCaret.current;
    if (!pending) return;
    const el = pending.field === "guidance" ? guidanceRef.current : ref.current;
    if (el && el.value.length >= pending.caret) {
      el.setSelectionRange(pending.caret, pending.caret);
      el.focus();
      pendingCaret.current = null;
    }
  }, [value, guidance, ref]);

  /**
   * Shared key handling. While the menu is open it owns Arrow/Enter/Tab/Escape — Enter in
   * particular must select rather than send, which is why this lives beside the send
   * shortcut rather than inside the menu.
   */
  function onFieldKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>, field: MentionField) {
    if (menuOpen && mention?.field === field) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % matches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + matches.length) % matches.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        selectMention(matches[Math.min(activeIndex, matches.length - 1)]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        dismissedRef.current = { field, start: mention.start };
        setMention(null);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sendDisabled && value.trim()) onSend();
    }
  }

  // The files currently tagged in either box, in the order they appear. Derived, never
  // stored — the text is the single source of truth for what will be sent.
  const taggedIds = tagging
    ? Array.from(
        new Set([
          ...stripMentions(value, mentionOptions).ids,
          ...(showGuidance ? stripMentions(guidance, mentionOptions).ids : []),
        ]),
      )
    : [];
  const taggedFiles = taggedIds
    .map((id) => mentionOptions.find((o) => o.id === id))
    .filter((o): o is MentionOption => Boolean(o));

  /** Untag a file by removing its `@name` token from both boxes. */
  function removeTag(option: MentionOption) {
    const nextValue = stripMentions(value, [option]);
    if (nextValue.ids.length) onChange(nextValue.text);
    if (showGuidance) {
      const nextGuidance = stripMentions(guidance, [option]);
      if (nextGuidance.ids.length) onGuidanceChange?.(nextGuidance.text);
    }
  }

  const mentionAria = (field: MentionField) =>
    tagging
      ? {
          "aria-expanded": menuOpen && mention?.field === field,
          "aria-controls": menuOpen && mention?.field === field ? listboxId : undefined,
          "aria-activedescendant":
            menuOpen && mention?.field === field
              ? optionId(Math.min(activeIndex, matches.length - 1))
              : undefined,
          "aria-autocomplete": "list" as const,
        }
      : {};

  return (
    /* Outer band: transparent, no background — just positions the centered panel. */
    <div className="flex-none px-[16px] pb-[12px] sm:px-[30px] sm:pb-[14px]">
      {/* The single visual unit: the chat box panel (input area + gap + controls). */}
      {/* `relative` anchors the `@` menu, which opens upward out of the panel. */}
      <div className="relative mx-auto flex max-w-[720px] flex-col rounded-[14px] border border-field-bd bg-field px-[10px] pt-[8px] pb-[7px] focus-within:border-accent transition-colors duration-150">
        {menuOpen ? (
          <MentionMenu
            id={listboxId}
            options={matches}
            activeIndex={Math.min(activeIndex, matches.length - 1)}
            optionId={optionId}
            onSelect={selectMention}
          />
        ) : null}
        {/* Scene direction (Player POV) — the narrator's box, above the character's line and
            separated from it by a hairline so the two are never mistaken for one field. */}
        {showGuidance ? (
          <div className="mb-[6px] border-b border-field-bd pb-[6px]">
            <textarea
              ref={guidanceRef}
              rows={1}
              value={guidance}
              onChange={(e) => {
                onGuidanceChange?.(e.target.value);
                resize(e.currentTarget, GUIDANCE_MAX_HEIGHT);
                syncMention("guidance", e.currentTarget);
              }}
              onKeyDown={(e) => onFieldKeyDown(e, "guidance")}
              onKeyUp={(e) => {
                if (!MENU_KEYS.has(e.key)) syncMention("guidance", e.currentTarget);
              }}
              onClick={(e) => syncMention("guidance", e.currentTarget)}
              onBlur={() => setMention(null)}
              {...mentionAria("guidance")}
              aria-label="Scene direction"
              placeholder="Guide the scene — what happens next…"
              className="composer-input block w-full resize-none bg-transparent px-[4px] py-[2px] font-body text-[13px] text-mute placeholder:text-mute2 focus:outline-none"
              style={{ overflowY: "hidden" }}
            />
          </div>
        ) : null}

        {/* The message input — no focus outline (the container carries the accent border). */}
        <textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            resize(e.currentTarget);
            syncMention("message", e.currentTarget);
          }}
          onKeyDown={(e) => onFieldKeyDown(e, "message")}
          onKeyUp={(e) => {
            if (!MENU_KEYS.has(e.key)) syncMention("message", e.currentTarget);
          }}
          onClick={(e) => syncMention("message", e.currentTarget)}
          onBlur={() => setMention(null)}
          {...mentionAria("message")}
          // textarea is always enabled — only send is blocked while streaming
          aria-label="Your message"
          placeholder={placeholder}
          className="composer-input block w-full resize-none bg-transparent px-[4px] pt-[2px] pb-[8px] font-body text-[14px] text-ink placeholder:text-mute2 focus:outline-none"
          style={{ overflowY: "hidden" }}
        />

        {/* Tagged files — a preview of exactly what this turn will carry as reference. */}
        {taggedFiles.length > 0 ? (
          <ul
            aria-label="Tagged files"
            className="mb-[6px] flex flex-wrap items-center gap-[5px] px-[4px]"
          >
            {taggedFiles.map((file) => (
              <li key={file.id}>
                <span className="flex items-center gap-[4px] rounded-[6px] border border-field-bd py-[1px] pr-[1px] pl-[7px] font-mono text-[10px] text-mute">
                  <span aria-hidden>⎙</span>
                  <span className="max-w-[160px] truncate">{file.name}</span>
                  {/* 24×24 minimum target (WCAG 2.5.8) — the glyph is small, the hit area is not. */}
                  <button
                    type="button"
                    onClick={() => removeTag(file)}
                    aria-label={`Remove ${file.name}`}
                    className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[4px] text-[12px] text-mute hover:bg-hover hover:text-ink"
                  >
                    ×
                  </button>
                </span>
              </li>
            ))}
          </ul>
        ) : null}

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
              beatLength={beatLength}
              onBeatLengthChange={onBeatLengthChange}
              onContextBeatsChange={onContextBeatsChange}
              beatTexts={beatTexts}
              openUp
            />
          ) : null}
          {onPovChange ? (
            <PovSelect pov={pov} onPovChange={onPovChange} options={povOptions} />
          ) : null}
          {onGhostwrite ? (
            <GhostwriteButton
              onGhostwrite={onGhostwrite}
              onUndo={onUndoGhostwrite ?? (() => {})}
              running={ghostwriting}
              canGhostwrite={Boolean(value.trim()) && !sendDisabled}
              canUndo={canUndoGhostwrite}
            />
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
            className="flex flex-none items-center gap-[5px] rounded-[8px] bg-accent px-[11px] py-[5px] font-mono text-[10px] tracking-[0.08em] text-[#F6ECDA] uppercase hover:bg-accent-hover disabled:opacity-50 disabled:hover:bg-accent"
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
