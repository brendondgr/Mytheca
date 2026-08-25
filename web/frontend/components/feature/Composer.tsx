import { useId, useLayoutEffect, useRef, useState, type RefObject } from "react";
import {
  SceneConfigMenu,
  type SceneControlKey,
  type Register,
  type SceneFlow,
  type TieScope,
} from "@/components/feature/SceneConfigMenu";
import { PovSelect, type PovOption } from "@/components/feature/PovSelect";
import { PlanModeButton, type PlanMode } from "@/components/feature/PlanModeButton";
import { GhostwriteButton } from "@/components/feature/GhostwriteButton";
import { ContextUsageDial } from "@/components/feature/ContextUsageDial";
import { Monogram } from "@/components/ui/Monogram";
import { mediaUrl } from "@/lib/api";
import { MentionMenu } from "@/components/feature/MentionMenu";
import { DirectionRow } from "@/components/feature/DirectionRow";
import { SceneVerbBar } from "@/components/feature/SceneVerbBar";
import type { SceneVerb } from "@/lib/sceneVerbs";
import type { SceneMemory } from "@/features/story-player/turn-stream";
import {
  applyMention,
  filterMentions,
  findMentionQuery,
  removeMention,
  stripMentions,
  type MentionOption,
} from "@/features/story-player/mentions";

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
 * (`pov` set) and `onGuidanceChange` is wired. In Playwright mode the message box already is
 * the direction box — its text *is* the direction — so a second one would duplicate it.
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
  // Scene direction (Player POV only) — the direction box, above the message box.
  guidance = "",
  onGuidanceChange,
  // Scene config (rendered on the bottom-left when at least one handler is supplied).
  suggestionsCount,
  onSuggestionsCountChange,
  plannerMode,
  onPlannerModeChange,
  register,
  onRegisterChange,
  sceneFlow,
  onSceneFlowChange,
  tieScope,
  onTieScopeChange,
  graphAvailable,
  pinned,
  onPinnedChange,
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
  verbs = [],
  onExpandCast,
  castMenu,
  sceneMemory = null,
  summarised = false,
  secondsPerBeat,
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
   * The Playwright's direction for this turn — what should happen next and how the cast
   * should react. Rendered only under Player POV (see the component doc); as vague or as
   * specific as the player likes.
   */
  guidance?: string;
  /** Omit to hide the scene-direction box entirely. */
  onGuidanceChange?: (value: string) => void;
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  /**
   * Which scene controls are pinned to the scene. Anything unpinned applies to the next
   * message only, which the Config button reports with a dot so the state is visible
   * without opening the popover.
   */
  plannerMode?: PlanMode;
  onPlannerModeChange?: (value: PlanMode) => void;
  register?: Register | null;
  onRegisterChange?: (value: Register | null) => void;
  sceneFlow?: SceneFlow;
  onSceneFlowChange?: (value: SceneFlow) => void;
  tieScope?: TieScope;
  onTieScopeChange?: (value: TieScope) => void;
  graphAvailable?: boolean;
  pinned?: Record<SceneControlKey, boolean>;
  onPinnedChange?: (key: SceneControlKey, pinned: boolean) => void;
  /** Real transcript beats (one string each) — feeds the config's content-real readout. */
  /** Player POV: the id of the character the player is speaking AS (`null` = Playwright). */
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
  /** The direction verbs to offer. Empty (the default) hides the bar entirely. */
  verbs?: SceneVerb[];
  /** "Someone arrives" was tapped — the parent opens its cast submenu. */
  onExpandCast?: () => void;
  /** The open cast submenu, rendered inside the panel so it anchors like the `@` menu. */
  castMenu?: React.ReactNode;
  /** How far back the last turn reached — reported in the config menu. */
  sceneMemory?: SceneMemory | null;
  summarised?: boolean;
  secondsPerBeat?: number;
}) {
  // Plan mode's disclosure. Owned here rather than inside the button so a streaming turn can
  // collapse it: leaving it expanded over a turn already in flight offers a choice that
  // cannot apply to that message.
  //
  // DERIVED, not an effect. `open={planOpen && !sendDisabled}` closes it for the duration of
  // the turn and restores it afterwards with no setState in an effect and no cascading
  // render — and, unlike clearing the state, it does not forget that the player had it open.
  const [planOpen, setPlanOpen] = useState(false);

  const internalRef = useRef<HTMLTextAreaElement>(null);
  const ref = (inputRef as RefObject<HTMLTextAreaElement>) ?? internalRef;
  const guidanceRef = useRef<HTMLTextAreaElement>(null);

  const hasConfig = Boolean(onSuggestionsCountChange ?? onPlannerModeChange);
  // The direction ROW is always rendered when the parent owns a direction at all; what
  // changes between modes is its role. `showGuidance` remains the narrower question — is
  // there a direction *textarea* on screen — because the mention plumbing, the tagged-id
  // derivation and the untag path all key off a real second input existing.
  const hasDirection = Boolean(onGuidanceChange);
  const showGuidance = hasDirection && Boolean(pov);

  // Placeholder reflects the active POV: "Speaking as Mei…" when the player has chosen a
  // character to voice, else the default Playwright prompt.
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

  // There is something to send when the player wrote a line **or** a direction. A
  // direction-only turn is a real turn (the scene is steered without the character
  // speaking), so guarding on the message box alone would make the direction box a field
  // you can fill and cannot send.
  //
  // `showGuidance`, not `hasDirection`: in Playwright mode the direction value is inert — the
  // message box IS the direction, so `send()` drops it. A direction kept across a POV switch
  // (or restored on resume) would otherwise light up Send with nothing to post, and the turn
  // would come back a 400.
  const hasContent = Boolean(value.trim() || (showGuidance && (guidance ?? "").trim()));

  /**
   * Write a verb's phrasing into whichever box carries the direction, and **select it**.
   *
   * Under POV that is the direction textarea; in Playwright mode the message box *is* the
   * direction, so it goes there. One concept, two targets — the same split the direction
   * row states in words.
   *
   * The inserted text is selected rather than left with the caret after it, because the
   * point of a verb is to give the player a sentence to argue with: with it selected, one
   * keystroke replaces it and typing over it is the fast path rather than a chore.
   */
  function insertDirection(text: string) {
    if (!text) return;
    const target = showGuidance ? guidanceRef.current : ref.current;
    const write = showGuidance ? onGuidanceChange : onChange;
    const current = showGuidance ? (guidance ?? "") : value;
    // A verb is a new line of direction, not an append to the sentence in progress.
    const prefix = current.trim() ? `${current.replace(/\s+$/, "")}\n` : "";
    write?.(prefix + text);
    requestAnimationFrame(() => {
      if (!target) return;
      target.focus();
      target.setSelectionRange(prefix.length, prefix.length + text.length);
    });
  }

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
      if (!sendDisabled && hasContent) onSend();
    }
  }

  // The files currently tagged in either box, in the order they appear. Derived, never
  // stored — the text is the single source of truth for what will be sent.
  // Both kinds, in the order they appear: a cast mention aims the line, a doc mention
  // grounds it, and the row previews everything the turn will carry either way.
  const taggedIds = tagging
    ? Array.from(
        new Set(
          [value, ...(showGuidance ? [guidance] : [])].flatMap((box) => {
            const m = stripMentions(box, mentionOptions);
            return [...m.castIds, ...m.docIds];
          }),
        ),
      )
    : [];
  const taggedFiles = taggedIds
    .map((id) => mentionOptions.find((o) => o.id === id))
    .filter((o): o is MentionOption => Boolean(o));

  /**
   * Untag a file by removing its `@name` token from both boxes.
   *
   * `removeMention`, not `stripMentions`: stripping now keeps the name and drops only the
   * sigil (so the sent prose still says who it was about), which would have left the chip's
   * "×" removing nothing at all.
   */
  function removeTag(option: MentionOption) {
    const nextValue = removeMention(value, option);
    if (nextValue !== value) onChange(nextValue);
    if (showGuidance) {
      const nextGuidance = removeMention(guidance, option);
      if (nextGuidance !== guidance) onGuidanceChange?.(nextGuidance);
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
        {castMenu}
        {menuOpen ? (
          <MentionMenu
            id={listboxId}
            options={matches}
            activeIndex={Math.min(activeIndex, matches.length - 1)}
            optionId={optionId}
            onSelect={selectMention}
          />
        ) : null}
        {/* Scene direction — always present, above the message box and separated from it by
            a hairline. A labelled strip in Playwright mode (the message box IS the direction);
            the direction textarea under POV, where the message box is the character's line.
            The mention plumbing only rides along when there is a textarea to attach it to. */}
        {hasDirection ? (
          <DirectionRow
            mode={pov ? "pov" : "playwright"}
            value={guidance}
            onChange={(next) => onGuidanceChange?.(next)}
            povName={povName}
            textareaRef={guidanceRef}
            textareaProps={{
              // Side-effects only — DirectionRow writes the value.
              onChange: (e) => {
                resize(e.currentTarget, GUIDANCE_MAX_HEIGHT);
                syncMention("guidance", e.currentTarget);
              },
              onKeyDown: (e) => onFieldKeyDown(e, "guidance"),
              onKeyUp: (e) => {
                if (!MENU_KEYS.has(e.key)) syncMention("guidance", e.currentTarget);
              },
              onClick: (e) => syncMention("guidance", e.currentTarget),
              onBlur: () => setMention(null),
              ...mentionAria("guidance"),
            }}
          >
            {/* The verb bar lives on the direction row in BOTH modes; only the target it
                writes into changes. That is exactly the distinction the row's two modes
                exist to make. */}
            {verbs.length ? (
              <SceneVerbBar
                verbs={verbs}
                onVerb={insertDirection}
                onExpandCast={onExpandCast}
                disabled={sendDisabled}
              />
            ) : null}
          </DirectionRow>
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
          // Under POV this box is the CHARACTER's words, not the player's — naming it "Your
          // message" in both modes was the one place the interface still failed to say which
          // of the two you were writing.
          aria-label={povName ? `Your line as ${povName}` : "Your message"}
          placeholder={placeholder}
          className="composer-input block w-full resize-none bg-transparent px-[4px] pt-[2px] pb-[8px] font-body text-[14px] text-ink placeholder:text-mute2 focus:outline-none"
          style={{ overflowY: "hidden" }}
        />

        {/* Tagged in this turn — a preview of exactly what it will carry: who it is aimed
            at (cast) and what grounds it (files). A cast chip wears the character's colour
            and monogram so the two kinds are never confused at a glance. */}
        {taggedFiles.length > 0 ? (
          <ul
            aria-label="Tagged in this turn"
            className="mb-[6px] flex flex-wrap items-center gap-[5px] px-[4px]"
          >
            {taggedFiles.map((file) => (
              <li key={file.id}>
                <span
                  className={`flex items-center gap-[4px] rounded-[6px] border py-[1px] pr-[1px] pl-[7px] font-mono text-[10px] text-mute ${
                    file.kind === "cast" && file.color ? "" : "border-field-bd"
                  }`}
                  style={
                    file.kind === "cast" && file.color
                      ? { borderColor: file.color }
                      : undefined
                  }
                >
                  {file.kind === "cast" ? (
                    <Monogram
                      mono={file.mono ?? file.name.slice(0, 1).toUpperCase()}
                      color={file.color ?? "#8E2B1C"}
                      size={14}
                      ring={1}
                      fontSize={7}
                      src={file.portrait ? mediaUrl(file.portrait) : null}
                    />
                  ) : (
                    <span aria-hidden>⎙</span>
                  )}
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
              suggestionsCount={suggestionsCount}
              onSuggestionsCountChange={onSuggestionsCountChange}
              plannerMode={plannerMode}
              onPlannerModeChange={onPlannerModeChange}
              register={register}
              onRegisterChange={onRegisterChange}
              sceneFlow={sceneFlow}
              onSceneFlowChange={onSceneFlowChange}
              tieScope={tieScope}
              onTieScopeChange={onTieScopeChange}
              graphAvailable={graphAvailable}
              pinned={pinned}
              onPinnedChange={onPinnedChange}
              sceneMemory={sceneMemory}
              summarised={summarised}
              secondsPerBeat={secondsPerBeat}
              openUp
            />
          ) : null}
          {onPovChange ? (
            <PovSelect pov={pov} onPovChange={onPovChange} options={povOptions} />
          ) : null}
          {/* Plan mode sits between who you are speaking as and the send cluster: both are
              decisions about the message you are about to send, and this is the third. */}
          {onPlannerModeChange ? (
            <PlanModeButton
              mode={plannerMode ?? "auto"}
              onModeChange={onPlannerModeChange}
              open={planOpen && !sendDisabled}
              onOpenChange={setPlanOpen}
              disabled={sendDisabled}
            />
          ) : null}
          <div className="min-w-0 flex-1" />

          {/* Right cluster: the context dial, the ghostwriter, then the Send pill. */}
          <ContextUsageDial
            usedTokens={usedTokens}
            maxTokens={maxContextTokens ?? 0}
            exact={usedTokensExact}
            size={24}
          />
          {onGhostwrite ? (
            <GhostwriteButton
              onGhostwrite={onGhostwrite}
              onUndo={onUndoGhostwrite ?? (() => {})}
              running={ghostwriting}
              canGhostwrite={Boolean(value.trim()) && !sendDisabled}
              canUndo={canUndoGhostwrite}
            />
          ) : null}
          <button
            type="button"
            onClick={onSend}
            disabled={sendDisabled || !hasContent}
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
