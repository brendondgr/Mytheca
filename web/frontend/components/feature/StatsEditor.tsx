"use client";

import { FieldLabel } from "@/components/ui/FieldLabel";
import { blankStat, statKeyOf } from "@/features/library/editor";
import type { StatBand, StatDefinition } from "@/lib/types";

const NUM =
  "w-[58px] rounded-[2px] border border-field-bd bg-card px-[7px] py-[4px] text-right font-mono text-[12.5px] text-ink focus:border-accent focus:outline-none";
const TXT =
  "w-full rounded-[2px] border border-field-bd bg-card px-[9px] py-[5px] font-body text-[13.5px] text-ink focus:border-accent focus:outline-none";

/**
 * The universal-stats editor for a Storyline — every character shares these.
 *
 * Each stat is a bounded numeric value (min/max/default) plus labeled **bands**
 * ("tickers") describing what value ranges *mean* (e.g. Health 0–20 = "Nearly
 * dead", 81–100 = "Very healthy"). Bands feed future state-extraction and the
 * Character creator's stat proposal. The parent holds the list on the draft and
 * diffs it into create/update/delete calls on save.
 *
 * `originalKeys` are the keys loaded from the server: those stats keep an
 * immutable `key`, while a brand-new row's key auto-derives from its name.
 */
export function StatsEditor({
  stats,
  originalKeys,
  onChange,
}: {
  stats: StatDefinition[];
  originalKeys: Set<string>;
  onChange: (next: StatDefinition[]) => void;
}) {
  function patchStat(i: number, patch: Partial<StatDefinition>) {
    onChange(stats.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  }
  function setName(i: number, name: string) {
    const locked = originalKeys.has(stats[i].key);
    // New rows: keep the key synced to the name until the stat is persisted.
    patchStat(i, locked ? { displayName: name } : { displayName: name, key: statKeyOf(name) });
  }
  function num(v: string, fallback: number): number {
    const n = Number(v);
    return Number.isFinite(n) ? Math.trunc(n) : fallback;
  }
  function addStat() {
    onChange([...stats, blankStat()]);
  }
  function removeStat(i: number) {
    onChange(stats.filter((_, idx) => idx !== i));
  }

  // ---- bands ----
  function patchBand(si: number, bi: number, patch: Partial<StatBand>) {
    const bands = stats[si].bands.map((b, idx) => (idx === bi ? { ...b, ...patch } : b));
    patchStat(si, { bands });
  }
  function addBand(si: number) {
    const s = stats[si];
    patchStat(si, { bands: [...s.bands, { min: s.min, max: s.max, label: "" }] });
  }
  function removeBand(si: number, bi: number) {
    patchStat(si, { bands: stats[si].bands.filter((_, idx) => idx !== bi) });
  }

  return (
    <div>
      <div className="flex items-end justify-between gap-[10px]">
        <FieldLabel>Statistics</FieldLabel>
        <button
          type="button"
          onClick={addStat}
          className="mb-[6px] cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:underline"
        >
          + Add statistic
        </button>
      </div>
      <p className="mb-[12px] font-body text-[12.5px] text-ink-soft">
        Universal stats shared by every character in this world. Give each a range
        and labeled <span className="italic">bands</span> — what its values mean
        (e.g. Health 0–20 = “Nearly dead”) — so the story engine can read a
        character&apos;s condition from a number.
      </p>

      {stats.length === 0 ? (
        <p className="font-body text-[12.5px] text-mute">
          No stats yet — add one to define what every character tracks.
        </p>
      ) : (
        <ul className="flex flex-col gap-[12px]">
          {stats.map((s, si) => (
            <li
              key={si}
              role="group"
              aria-label={s.displayName || "New statistic"}
              className="rounded-[5px] border border-cardbd bg-field p-[12px]"
            >
              {/* Name + remove */}
              <div className="flex items-start gap-[10px]">
                <div className="min-w-0 flex-1">
                  <input
                    aria-label={`Statistic ${si + 1} name`}
                    placeholder="Name — e.g. Health"
                    value={s.displayName}
                    onChange={(e) => setName(si, e.target.value)}
                    className={TXT}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => removeStat(si)}
                  aria-label={`Remove ${s.displayName || "statistic"}`}
                  className="cursor-pointer px-[6px] py-[4px] font-mono text-[10px] tracking-[0.06em] text-accent uppercase hover:underline"
                >
                  Remove
                </button>
              </div>

              {/* Description */}
              <input
                aria-label={`${s.displayName || "Statistic"} description`}
                placeholder="What it represents (optional)."
                value={s.description}
                onChange={(e) => patchStat(si, { description: e.target.value })}
                className={`${TXT} mt-[8px]`}
              />

              {/* Range */}
              <div className="mt-[10px] flex flex-wrap items-center gap-x-[16px] gap-y-[8px]">
                {(["min", "max", "default"] as const).map((field) => (
                  <label key={field} className="flex items-center gap-[6px]">
                    <span className="font-mono text-[9.5px] tracking-[0.08em] text-mute2 uppercase">
                      {field}
                    </span>
                    <input
                      type="number"
                      aria-label={`${s.displayName || "Statistic"} ${field}`}
                      value={s[field]}
                      onChange={(e) => patchStat(si, { [field]: num(e.target.value, s[field]) })}
                      className={NUM}
                    />
                  </label>
                ))}
              </div>

              {/* Bands ("tickers") */}
              <div className="mt-[12px] border-t border-hair-strong pt-[10px]">
                <div className="flex items-center justify-between gap-[10px]">
                  <span className="font-mono text-[9.5px] tracking-[0.1em] text-mute2 uppercase">
                    Bands · what the ranges mean
                  </span>
                  <button
                    type="button"
                    onClick={() => addBand(si)}
                    className="cursor-pointer font-mono text-[10px] tracking-[0.06em] text-accent uppercase hover:underline"
                  >
                    + Add band
                  </button>
                </div>
                {s.bands.length === 0 ? (
                  <p className="mt-[6px] font-body text-[12px] text-mute">
                    No bands — add one to label a range (e.g. 0–20 “Nearly dead”).
                  </p>
                ) : (
                  <ul className="mt-[8px] flex flex-col gap-[7px]">
                    {s.bands.map((b, bi) => (
                      <li key={bi} className="flex flex-wrap items-center gap-[8px]">
                        <input
                          type="number"
                          aria-label={`Band ${bi + 1} min`}
                          value={b.min}
                          onChange={(e) => patchBand(si, bi, { min: num(e.target.value, b.min) })}
                          className={NUM}
                        />
                        <span aria-hidden className="text-mute2">
                          –
                        </span>
                        <input
                          type="number"
                          aria-label={`Band ${bi + 1} max`}
                          value={b.max}
                          onChange={(e) => patchBand(si, bi, { max: num(e.target.value, b.max) })}
                          className={NUM}
                        />
                        <input
                          aria-label={`Band ${bi + 1} label`}
                          placeholder="Label — e.g. Nearly dead"
                          value={b.label}
                          onChange={(e) => patchBand(si, bi, { label: e.target.value })}
                          className={`${TXT} min-w-[120px] flex-1`}
                        />
                        <button
                          type="button"
                          onClick={() => removeBand(si, bi)}
                          aria-label={`Remove band ${bi + 1}`}
                          className="cursor-pointer px-[5px] font-mono text-[13px] text-accent hover:underline"
                        >
                          ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
