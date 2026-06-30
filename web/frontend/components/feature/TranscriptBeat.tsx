import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { mediaUrl } from "@/lib/api";
import type { Character } from "@/lib/types";
import type { SceneChoice, SceneMessage } from "@/features/story-player/scene-data";

/** `narration` → teal-accented italic card. */
export function NarratorCard({ text }: { text: string }) {
  return (
    <div className="rounded-[0_5px_5px_0] border-l-[3px] border-l-narrator bg-[rgba(31,138,130,.12)] p-[13px_17px]">
      <Eyebrow size={8} tracking="0.18em" color="#1F8A82" className="mb-[6px] block">
        Narrator
      </Eyebrow>
      <p className="font-body text-[15.5px] leading-[1.55] text-ink italic">{text}</p>
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

/** `character_dialogue` (+ inline `character_action`) — monogram + name + bubble. */
export function CharacterMessage({
  character,
  action,
  text,
  onProfile,
}: {
  character: Character;
  action?: string;
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
            <span className="font-body text-[13px] text-mute2 italic">{action}</span>
          ) : null}
        </div>
        {text ? (
          <div className="mt-[6px] rounded-[3px_11px_11px_11px] border border-cardbd bg-card p-[11px_15px] font-body text-[15.5px] leading-[1.5] text-ink shadow-[0_1px_2px_rgba(20,14,6,.06)]">
            {text}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Optional dice `check` — gold d20 card with a Success/Failure pill. */
export function CheckCard({
  check,
  roll,
  result,
  text,
}: {
  check: string;
  roll: number;
  result: "Success" | "Failure";
  text: string;
}) {
  const ok = result === "Success";
  return (
    <div className="w-full max-w-[540px] self-center rounded-[6px] border border-[#C8A24A] bg-[linear-gradient(#FBF3DE,#F6EACB)] p-[13px_16px] shadow-[0_2px_10px_rgba(20,14,6,.12)]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-[10px]">
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-[6px] bg-gold font-display text-[14px] font-bold text-[#1f160c]">
            {roll}
          </span>
          <div>
            <div className="font-mono text-[11px] tracking-[0.04em] text-[#7A5A1E]">
              {check}
            </div>
            <Eyebrow size={8} tracking="0.14em" color="#A8762A" className="mt-[3px] block">
              d20 check
            </Eyebrow>
          </div>
        </div>
        <span
          className="rounded-[11px] px-[10px] py-1 font-mono text-[10px] tracking-[0.08em] text-[#F4ECDA] uppercase"
          style={{ background: ok ? "#1F8A5B" : "#9A3520" }}
        >
          {result}
        </span>
      </div>
      <p className="mt-[10px] font-body text-[14.5px] leading-[1.5] text-[#3A3024] italic">
        {text}
      </p>
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
  return (
    <div className="w-full max-w-[600px] self-center">
      <div className="mb-[10px] text-center">
        <Eyebrow tracking="0.16em" color="var(--accent)">
          Your move — choose a path
        </Eyebrow>
      </div>
      <div className="flex flex-col gap-2">
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
            <span className="flex-none font-mono text-[10px] whitespace-nowrap text-accent">
              {ch.check}
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
  if (m.kind === "check")
    return (
      <CheckCard
        check={m.check ?? ""}
        roll={m.roll ?? 0}
        result={m.result ?? "Success"}
        text={m.text ?? ""}
      />
    );
  if (m.kind === "choices")
    return <BranchChoices choices={choices} onChoose={onChoose} />;
  const c = charById(m.who ?? "");
  if (!c) return null;
  return (
    <CharacterMessage
      character={c}
      action={m.action}
      text={m.text ?? ""}
      onProfile={onProfile ? () => onProfile(c.id) : undefined}
    />
  );
}
