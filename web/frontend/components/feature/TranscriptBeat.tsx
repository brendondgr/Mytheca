import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { mediaUrl } from "@/lib/api";
import type { Character } from "@/lib/types";
import type { SceneChoice, SceneMessage } from "@/features/story-player/scene-data";

/** `narration` → teal-accented card (upright, not italic — feedback #6). */
export function NarratorCard({ text }: { text: string }) {
  return (
    <div className="rounded-[0_5px_5px_0] border-l-[3px] border-l-narrator bg-[rgba(31,138,130,.12)] p-[13px_17px]">
      <Eyebrow size={8} tracking="0.18em" color="#1F8A82" className="mb-[6px] block">
        Narrator
      </Eyebrow>
      <p className="font-body text-[15.5px] leading-[1.55] text-ink">{text}</p>
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
        <div className="rounded-[11px_3px_11px_11px] bg-accent p-[11px_15px] font-body text-[15.5px] leading-[1.5] text-[#F6ECDA]">
          {text}
        </div>
      </div>
    </div>
  );
}

/**
 * `character_dialogue` (+ inline `character_action` + private `thought`) — monogram +
 * name + bubble. A character's private thinking (feedback: combine think+speak) renders
 * muted and slightly smaller BETWEEN the name and the spoken bubble, so one beat carries
 * the whole moment: what they think, then what they say.
 */
export function CharacterMessage({
  character,
  action,
  thought,
  text,
  onProfile,
}: {
  character: Character;
  action?: string;
  thought?: string;
  text: string;
  onProfile?: () => void;
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
        className="flex-none rounded-full transition-transform hover:scale-105 disabled:hover:scale-100"
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
        {thought ? (
          <p className="mt-[4px] font-body text-[13px] leading-[1.45] text-ink-soft">
            <span className="mr-[6px] font-mono text-[9px] uppercase tracking-[0.14em] text-mute2">
              thinks
            </span>
            {thought}
          </p>
        ) : null}
        {text ? (
          <div className="mt-[6px] rounded-[3px_11px_11px_11px] border border-cardbd bg-card p-[11px_15px] font-body text-[15.5px] leading-[1.5] text-ink shadow-[0_1px_2px_rgba(20,14,6,.06)]">
            {text}
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
            className="velora-row flex items-center gap-[13px] rounded-[4px] border border-field-bd bg-card p-[12px_15px] text-left hover:translate-x-[3px] hover:border-accent"
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
}: {
  message: SceneMessage;
  charById: (id: string) => Character | undefined;
  onProfile?: (id: string) => void;
  choices: SceneChoice[];
  onChoose: (choice: SceneChoice) => void;
}) {
  const m = message;
  if (m.kind === "narrator") return <NarratorCard text={m.text ?? ""} />;
  if (m.kind === "player") return <PlayerMessage text={m.text ?? ""} />;
  if (m.kind === "choices")
    return <BranchChoices choices={choices} onChoose={onChoose} />;
  const c = charById(m.who ?? "");
  if (!c) return null;
  return (
    <CharacterMessage
      character={c}
      action={m.action}
      thought={m.thought}
      text={m.text ?? ""}
      onProfile={onProfile ? () => onProfile(c.id) : undefined}
    />
  );
}
