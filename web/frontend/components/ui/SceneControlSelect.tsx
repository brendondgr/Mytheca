import { useId, type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * An option whose rendered text differs from its value — for enums like the beat-length
 * tiers, where the wire carries `"short"` and the reader should see `"Short (1–2 ¶)"`.
 */
export type SceneControlOption<T extends string | number> = {
  value: T;
  label: string;
};

function normalize<T extends string | number>(
  options: readonly (T | SceneControlOption<T>)[],
): SceneControlOption<T>[] {
  return options.map((o) =>
    typeof o === "object" ? o : { value: o, label: String(o) },
  );
}

/**
 * Compact labeled dropdown for the scene composer controls (turn limit, follow-up
 * suggestion count, beat length). A tiny mono caption sits above a native `<select>`
 * styled to the field tokens — native so it stays keyboard/screen-reader accessible.
 *
 * Generic over `string | number` so an enum and a count can share one control. The value
 * type is inferred from `value`, and `onChange` is handed back the ORIGINAL option value
 * rather than the DOM's string: a native `<select>` stringifies everything, and the old
 * unconditional `Number(...)` coercion is exactly why this could not carry an enum. Values
 * are matched by their string form, so a numeric caller still receives a number.
 */
export function SceneControlSelect<T extends string | number>({
  label,
  value,
  options,
  onChange,
  help,
  cost,
  disabled = false,
  className,
}: {
  label: string;
  value: T;
  /** Selectable values — bare, or `{value, label}` when the text should differ. */
  options: readonly (T | SceneControlOption<T>)[];
  onChange: (value: T) => void;
  /**
   * One line saying what this control *does* — announced with the control rather than
   * floating beside it, via `aria-describedby`. A label alone tells a player what a setting
   * is called; it never tells them what happens if they change it.
   */
  help?: ReactNode;
  /** What it costs, when there is an honest number — tokens, seconds, beats. */
  cost?: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const items = normalize(options);
  const helpId = useId();
  return (
    <label className={cn("flex flex-none flex-col gap-[3px]", className)}>
      <span className="font-mono text-[9px] tracking-[0.12em] text-mute2 uppercase">
        {label}
      </span>
      <select
        value={String(value)}
        onChange={(e) => {
          const picked = items.find((o) => String(o.value) === e.target.value);
          if (picked) onChange(picked.value);
        }}
        disabled={disabled}
        aria-label={label}
        aria-describedby={help ? helpId : undefined}
        className="rounded-[3px] border border-field-bd bg-field p-[7px_8px] font-mono text-[12px] text-ink focus:border-accent focus:outline-none disabled:opacity-60"
      >
        {items.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>
            {o.label}
          </option>
        ))}
      </select>
      {help ? (
        <p id={helpId} className="font-body text-[11px] leading-[1.4] text-mute2">
          {help}
          {cost ? (
            // The cost sits with the consequence, not in a separate readout: "what it does"
            // and "what it costs" are one decision, and separating them makes the player
            // read twice to make it once.
            // The leading space is not decoration: a CSS margin separates these visually but
            // `textContent` concatenates them, so the accessible description ran the two
            // together — "its own length.≈ 260 tokens a beat".
            <span className="ml-[4px] font-mono text-[10px] tracking-[0.04em] text-ink-soft">
              {" "}
              {cost}
            </span>
          ) : null}
        </p>
      ) : null}
    </label>
  );
}
