import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TypingDots } from "@/components/ui/TypingDots";
import { QuotedText } from "@/components/ui/QuotedText";
import { SceneImageBeat } from "@/components/feature/SceneImageBeat";
import { mediaUrl } from "@/lib/api";
import type { Character } from "@/lib/types";
import type { SceneChoice, SceneImage, SceneMessage } from "@/features/story-player/scene-data";

/**
 * The 2px block caret that rides the tail of prose still being written.
 *
 * It is the difference between "the scene has paused" and "the scene is still
 * being written" — a distinction the transcript otherwise leaves the reader to
 * guess at. Purely decorative (`aria-hidden`): the same fact reaches assistive
 * tech through `aria-busy` and the completion announcement.
 *
 * Note there is no per-chunk fade-in to go with it. The backend's delta frames
 * re-emit each event's **full accumulated text** rather than the new fragment,
 * so there are no chunk boundaries on the client to wrap — animating what
 * arrived would re-animate the whole paragraph on every delta.
 */
function StreamCaret() {
  return <span aria-hidden="true" className="stream-caret" />;
}

/**
 * The colour a character's spoken words take: their own, mixed 30% toward the theme's
 * `--quote-tint`. On the dark themes that lifts the hue off the bubble; on parchment the
 * tint is the ink colour instead, because a straight lighten washes out on cream. Only
 * quoted speech is tinted — the surrounding prose stays plain body text.
 */
function speechColor(color: string | undefined): string | undefined {
  return color ? `color-mix(in oklab, ${color} 70%, var(--quote-tint))` : undefined;
}

/** `narration` → teal-accented card (upright, not italic — feedback #6). */
export function NarratorCard({ text, streaming }: { text: string; streaming?: boolean }) {
  return (
    <div className="rounded-[0_5px_5px_0] border-l-[3px] border-l-narrator bg-[rgba(31,138,130,.12)] p-[13px_17px]">
      <Eyebrow size={8} tracking="0.18em" color="#1F8A82" className="mb-[6px] block">
        Narrator
      </Eyebrow>
      <p className="font-body text-[15.5px] leading-[1.55] whitespace-pre-line text-ink">
        <QuotedText text={text} />
        {streaming ? <StreamCaret /> : null}
      </p>
    </div>
  );
}

/** The player's own turn — right-aligned accent bubble. */
export function PlayerMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%]">
        <div className="mb-[5px] text-right">
          <Eyebrow size={8} tracking="0.14em" color="var(--accent)">
            You
          </Eyebrow>
        </div>
        <div className="rounded-[11px_3px_11px_11px] bg-accent p-[11px_15px] font-body text-[15.5px] leading-[1.5] whitespace-pre-line text-[#F6ECDA]">
          <QuotedText text={text} />
        </div>
      </div>
    </div>
  );
}

/**
 * A player-authored character beat (Player POV) — the player's own line, but spoken AS a
 * character. Right-aligned like {@link PlayerMessage} so it reads as *your* turn, but wearing
 * the character's identity (monogram + name in their color) instead of "You". The bubble keeps
 * the accent fill (guaranteed AA contrast — a character's color can be light), so only the
 * header carries the character color.
 */
export function PlayerAsCharacterMessage({
  character,
  action,
  text,
}: {
  character: Character;
  action?: string;
  text: string;
}) {
  const c = character;
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%]">
        <div className="mb-[5px] flex items-center justify-end gap-[7px]">
          {action ? (
            <span className="font-body text-[13px] text-mute2">{action}</span>
          ) : null}
          <Eyebrow size={8} tracking="0.14em" color={c.color}>
            {c.name}
          </Eyebrow>
          <Monogram
            mono={c.mono}
            color={c.color}
            src={c.portrait ? mediaUrl(c.portrait) : undefined}
            size={22}
            fontSize={9}
            ring={1.5}
          />
        </div>
        <div className="rounded-[11px_3px_11px_11px] bg-accent p-[11px_15px] font-body text-[15.5px] leading-[1.5] whitespace-pre-line text-[#F6ECDA]">
          <QuotedText text={text} />
        </div>
      </div>
    </div>
  );
}

/**
 * `character_dialogue` (+ inline `character_action` + private `thought`) — monogram +
 * name + one bubble. A character's private thinking and their speech share a SINGLE box at
 * the SAME text size (request #4): the thought reads muted + italic at the top, the spoken
 * line upright below it, so one beat carries the whole moment — what they think, then what
 * they say. Quoted dialogue is bolded within the bubble via {@link QuotedText}.
 */
export function CharacterMessage({
  character,
  action,
  thought,
  reasoning,
  text,
  onProfile,
  streaming,
  pending,
}: {
  character: Character;
  streaming?: boolean;
  action?: string;
  thought?: string;
  /**
   * The model's raw, in-flight deliberation (Reasoning visibility = "full"). Live only —
   * it is cleared once the beat lands, so it never appears on a finished or resumed beat.
   */
  reasoning?: string;
  text: string;
  onProfile?: () => void;
  /**
   * The speaker is chosen but nothing is written yet. Reserves the beat's place so the
   * thought → speech sequence fills one stable spot rather than pushing the transcript
   * around as it arrives.
   */
  pending?: boolean;
}) {
  const c = character;
  return (
    <div className="flex items-start gap-3">
      <button
        type="button"
        onClick={onProfile}
        disabled={!onProfile}
        aria-label={`View ${c.name}`}
        title={c.name}
        className="flex-none rounded-full hover-grow"
      >
        <Monogram mono={c.mono} color={c.color} src={c.portrait ? mediaUrl(c.portrait) : undefined} size={40} fontSize={14} />
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-[9px]">
          <button
            type="button"
            onClick={onProfile}
            disabled={!onProfile}
            className="font-display text-[15px] font-semibold hover:underline disabled:no-underline"
            style={{ color: c.color }}
          >
            {c.name}
          </button>
          {action ? (
            <span className="font-body text-[13px] text-mute2">{action}</span>
          ) : null}
        </div>
        {/* Raw deliberation, while it is happening. Deliberately subordinate to everything
            else — smaller, dimmer, and collapsed by default — because it is machinery, it
            is long and rambling, and it must never compete with the prose. It sits ABOVE
            the bubble so the beat itself never shifts as the reasoning grows. */}
        {reasoning ? (
          <details className="mt-[6px] group">
            <summary className="cursor-pointer list-none font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
              working…
            </summary>
            <p className="mt-[4px] max-h-[8lh] overflow-y-auto border-l border-hair pl-[9px] font-mono text-[11px] leading-[1.45] text-mute2">
              {reasoning}
            </p>
          </details>
        ) : null}
        {/* Nothing written yet: hold the beat's height with the same bubble geometry the
            prose will land in, so filling it in does not shift the page. */}
        {pending && !thought && !text ? (
          <div className="mt-[6px] flex min-h-[2.4em] items-center rounded-[3px_11px_11px_11px] border border-cardbd bg-card p-[11px_15px]">
            <TypingDots className="text-mute2" />
            <span className="sr-only">{c.name} is composing a reply</span>
          </div>
        ) : null}
        {thought || text ? (
          <div className="mt-[6px] rounded-[3px_11px_11px_11px] border border-cardbd bg-card p-[11px_15px] shadow-[0_1px_2px_rgba(20,14,6,.06)]">
            {thought ? (
              <p className="font-body text-[15.5px] leading-[1.5] text-ink-soft italic">
                <span className="mr-[6px] align-baseline font-mono text-[9px] not-italic uppercase tracking-[0.14em] text-mute2">
                  thinks
                </span>
                <QuotedText text={thought} />
              </p>
            ) : null}
            {text ? (
              <p
                // `whitespace-pre-line` keeps the paragraph breaks inside a first-person
                // passage, which may legitimately run to two or three paragraphs. Plain
                // body text throughout — only the quoted speech is bolded, by QuotedText.
                className={`font-body text-[15.5px] leading-[1.5] whitespace-pre-line text-ink${
                  thought ? " mt-[8px] border-t border-hair pt-[8px]" : ""
                }`}
              >
                <QuotedText text={text} color={speechColor(c.color)} />
                {streaming ? <StreamCaret /> : null}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** `branch_choices` — centered ◆ choice rows. */
export function BranchChoices({
  choices,
  onChoose,
}: {
  choices: SceneChoice[];
  onChoose: (choice: SceneChoice) => void;
}) {
  // 3–4 follow-ups lay out in a 2-column grid (4 → a 2×2 grid); 1–2 stack in a column.
  const layout = choices.length >= 3 ? "grid grid-cols-2 gap-2" : "flex flex-col gap-2";
  return (
    <div className="w-full max-w-[600px] self-center">
      <div className="mb-[10px] text-center">
        <Eyebrow tracking="0.16em" color="var(--accent)">
          Your move — choose a path
        </Eyebrow>
      </div>
      <div className={layout}>
        {choices.map((ch) => (
          <button
            key={ch.id}
            type="button"
            onClick={() => onChoose(ch)}
            className="mytheca-row flex items-center gap-[13px] rounded-[4px] border border-field-bd bg-card p-[12px_15px] text-left hover-nudge hover:border-accent hover:bg-hover"
          >
            <span aria-hidden className="flex-none text-[13px] text-accent">
              ◆
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-display text-[15px] text-ink">{ch.label}</span>
              <span className="mt-[2px] block font-body text-[13px] text-ink-soft">
                {ch.outcome}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Routes one transcript message to its renderer (the event→component contract). */
export function TranscriptBeat({
  message,
  charById,
  onProfile,
  choices,
  onChoose,
  onOpenImage,
  streaming = false,
  reasoningByChar,
}: {
  message: SceneMessage;
  charById: (id: string) => Character | undefined;
  onProfile?: (id: string) => void;
  choices: SceneChoice[];
  onChoose: (choice: SceneChoice) => void;
  /** Open a scene image in the enlarged view (omit to render it non-clickable). */
  onOpenImage?: (image: SceneImage) => void;
  /** This beat is the one currently being written — show the caret at its tail. */
  streaming?: boolean;
  /**
   * Live model deliberation for this beat's speaker, keyed by character id (Reasoning
   * visibility = "full"). Ephemeral — cleared as the beat lands.
   */
  reasoningByChar?: Record<string, string>;
}) {
  const m = message;
  if (m.kind === "narrator") return <NarratorCard text={m.text ?? ""} streaming={streaming} />;
  if (m.kind === "player") return <PlayerMessage text={m.text ?? ""} />;
  if (m.kind === "image")
    return m.image ? <SceneImageBeat image={m.image} onOpen={onOpenImage} /> : null;
  if (m.kind === "choices")
    return <BranchChoices choices={choices} onChoose={onChoose} />;
  const c = charById(m.who ?? "");
  if (!c) return null;
  // Player POV: a `char` beat the player authored (they spoke AS this character) renders on
  // the player's side of the transcript, wearing the character's identity.
  if (m.fromPlayer)
    return <PlayerAsCharacterMessage character={c} action={m.action} text={m.text ?? ""} />;
  return (
    <CharacterMessage
      character={c}
      action={m.action}
      thought={m.thought}
      reasoning={reasoningByChar?.[c.id]}
      text={m.text ?? ""}
      pending={m.pending}
      onProfile={onProfile ? () => onProfile(c.id) : undefined}
      streaming={streaming}
    />
  );
}
