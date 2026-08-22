"use client";

import { useId } from "react";

import { VOICE_MOMENTS, type VoiceSample } from "@/lib/types";

/**
 * The five stops, in order from `-2` to `+2`. Named rather than numbered because "-2" says
 * nothing about what it does to a character, and the number is an implementation detail of
 * the sampler nudge behind it.
 */
export const LOOSENESS_LABELS = [
  "Controlled",
  "Measured",
  "Natural",
  "Expressive",
  "Loose",
];

const TXT =
  "w-full rounded-[2px] border border-field-bd bg-card px-[9px] py-[5px] font-body text-[13.5px] text-ink focus:border-accent focus:outline-none";

/** Author-facing labels for each moment tag (the values match the backend registers). */
const MOMENT_LABELS: Record<string, string> = {
  "": "Any moment",
  light: "Light — nothing at stake",
  neutral: "Ordinary",
  tense: "Tense — something at risk",
  grave: "Grave — someone dying or breaking down",
};

/**
 * Editor for a character's **voice & tone** profile — a small list of
 * situation → single-response pairs that show *how* the character speaks.
 *
 * Each row pairs a previous situation the character was confronted with (often
 * another character's line) with the character's SINGLE response to it, in
 * their own voice — not a back-and-forth exchange. Each row also carries the
 * **moment** it demonstrates (light / ordinary / tense / grave), which the turn
 * loop matches against the beat's register: only the pairs fitting the current
 * moment (plus untagged ones) are injected, so a character has an exemplar of
 * themselves *not at rest* instead of always being shown their baseline voice.
 * A profile whose rows are all light leaves the character unable to change
 * register during play. The parent holds the list on the
 * draft; a "Propose / Redo" control (in the modal) can (re)generate it from the
 * character's background/personality.
 */
export function VoiceSamplesEditor({
  samples,
  onChange,
  looseness = null,
  onLoosenessChange,
}: {
  samples: VoiceSample[];
  onChange: (next: VoiceSample[]) => void;
  /** `[-2, +2]`, or `null` for neutral. See {@link LOOSENESS_LABELS}. */
  looseness?: number | null;
  onLoosenessChange?: (value: number) => void;
}) {
  const loosenessId = useId();

  function patch(i: number, next: Partial<VoiceSample>) {
    onChange(samples.map((s, idx) => (idx === i ? { ...s, ...next } : s)));
  }
  function add() {
    onChange([...samples, { situation: "", sample: "", moment: "" }]);
  }
  function remove(i: number) {
    onChange(samples.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      {/* The dial sits ABOVE the sample rows because it describes the same thing they do —
          how this character sounds — at a coarser grain. A native range keeps keyboard
          operation free, and the readout is TEXT: a slider position alone does not tell a
          reader which of five settings they landed on. */}
      {onLoosenessChange ? (
        <div className="mb-[12px] flex flex-col gap-[4px]">
          <label
            htmlFor={loosenessId}
            className="font-mono text-[9px] tracking-[0.12em] text-mute2 uppercase"
          >
            Word choice{" "}
            <span className="text-ink normal-case">
              · {LOOSENESS_LABELS[(looseness ?? 0) + 2]}
            </span>
          </label>
          <input
            id={loosenessId}
            type="range"
            min={-2}
            max={2}
            step={1}
            value={looseness ?? 0}
            onChange={(e) => onLoosenessChange(Number(e.target.value))}
            aria-describedby={`${loosenessId}-help`}
            aria-valuetext={LOOSENESS_LABELS[(looseness ?? 0) + 2]}
            className="h-[24px] w-full accent-[var(--accent)]"
          />
          <p
            id={`${loosenessId}-help`}
            className="font-body text-[11.5px] leading-[1.45] text-mute2"
          >
            How far this character&apos;s word choice may wander. The moment&apos;s register
            still leads; this only leans against it.
          </p>
        </div>
      ) : null}
      {samples.length === 0 ? (
        <p className="font-body text-[12.5px] text-mute">
          No samples yet — add one (or Propose) to show a past situation and how
          THIS character responded to it, in their own voice.
        </p>
      ) : (
        <ul className="flex flex-col gap-[10px]">
          {samples.map((s, i) => (
            <li
              key={i}
              role="group"
              aria-label={s.situation || `Voice sample ${i + 1}`}
              className="rounded-[5px] border border-cardbd bg-field p-[12px]"
            >
              <div className="flex items-start gap-[10px]">
                <div className="min-w-0 flex-1">
                  <input
                    aria-label={`Sample ${i + 1} situation`}
                    placeholder={
                      'What’s said to them — e.g. "For the right price, I could forget I saw you here."'
                    }
                    value={s.situation}
                    onChange={(e) => patch(i, { situation: e.target.value })}
                    className={TXT}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => remove(i)}
                  aria-label={`Remove sample ${i + 1}`}
                  className="cursor-pointer px-[6px] py-[4px] font-mono text-[10px] tracking-[0.06em] text-accent uppercase hover:underline"
                >
                  Remove
                </button>
              </div>
              <textarea
                aria-label={`Sample ${i + 1} response`}
                placeholder="Their single response to the situation above — in their own voice, not a back-and-forth."
                value={s.sample}
                onChange={(e) => patch(i, { sample: e.target.value })}
                rows={4}
                className={`${TXT} mt-[8px] resize-y`}
              />
              {/* Wraps at the 320px floor rather than pushing the row wide; the select
                  itself is capped so a long option label cannot overflow the card. */}
              <label className="mt-[8px] flex flex-wrap items-center gap-x-[8px] gap-y-[4px]">
                <span className="font-mono text-[10px] tracking-[0.08em] text-mute uppercase">
                  Moment
                </span>
                <select
                  aria-label={`Sample ${i + 1} moment`}
                  value={s.moment ?? ""}
                  onChange={(e) =>
                    patch(i, { moment: e.target.value as VoiceSample["moment"] })
                  }
                  className={`${TXT} w-auto max-w-full min-w-0 cursor-pointer`}
                >
                  <option value="">{MOMENT_LABELS[""]}</option>
                  {VOICE_MOMENTS.map((m) => (
                    <option key={m} value={m}>
                      {MOMENT_LABELS[m]}
                    </option>
                  ))}
                </select>
              </label>
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={add}
        className="mt-[8px] cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:underline"
      >
        + Add sample
      </button>
    </div>
  );
}
