"use client";

import type { VoiceSample } from "@/lib/types";

const TXT =
  "w-full rounded-[2px] border border-field-bd bg-card px-[9px] py-[5px] font-body text-[13.5px] text-ink focus:border-accent focus:outline-none";

/**
 * Editor for a character's **voice & tone** profile — a small list of
 * situation → sample-response pairs that show *how* the character speaks.
 *
 * Each row pairs a short situation ("greeted by a stranger", "offered a bribe")
 * with the line the character would actually say in response, written in their
 * voice. These samples are persisted with the character and injected into the
 * turn loop so both spoken lines and the hidden thinking step stay in voice.
 * The parent holds the list on the draft; a "Propose / Redo" control (in the
 * modal) can (re)generate it from the character's background/personality.
 */
export function VoiceSamplesEditor({
  samples,
  onChange,
}: {
  samples: VoiceSample[];
  onChange: (next: VoiceSample[]) => void;
}) {
  function patch(i: number, next: Partial<VoiceSample>) {
    onChange(samples.map((s, idx) => (idx === i ? { ...s, ...next } : s)));
  }
  function add() {
    onChange([...samples, { situation: "", sample: "" }]);
  }
  function remove(i: number) {
    onChange(samples.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      {samples.length === 0 ? (
        <p className="font-body text-[12.5px] text-mute">
          No samples yet — add one (or Propose) to show how this character sounds
          when something happens.
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
                    placeholder="Situation — e.g. offered a bribe"
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
                placeholder="What they'd say — in their own voice."
                value={s.sample}
                onChange={(e) => patch(i, { sample: e.target.value })}
                rows={2}
                className={`${TXT} mt-[8px] resize-y`}
              />
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
