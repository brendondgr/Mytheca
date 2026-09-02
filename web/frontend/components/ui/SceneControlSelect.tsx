import { useId, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { InfoTip } from "@/components/ui/InfoTip";
import { Select } from "@/components/ui/Select";

/**
 * An option whose rendered text differs from its value — for enums like the presence
 * states, where the wire carries `"unconscious"` and the reader should see `"Unconscious"`.
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
 * One scene setting: a **short title**, an **info button**, and a **dropdown**.
 *
 * **What this used to be, and why it changed.** The title was a sentence — "Follow-up ideas
 * offered after each turn" — set in the design system's label style, which is mono, uppercase
 * and tracked at `.12em`. That treatment is right for a label and ruinous for a sentence:
 * measured live, four of the config popover's six titles wrapped, one to 52px of wide-tracked
 * capitals. Underneath each sat its description as a paragraph in flow, 356px of prose across
 * the panel, to say something a reader needs exactly once.
 *
 * So the title is now short enough to stay on one line, and the sentence moved into
 * {@link InfoTip} — where it is still the control's `aria-describedby` target, so a screen
 * reader hears what it always heard. `accessibleName` carries the longer phrasing into the
 * select's own name; the visible title stays a PREFIX of it, which is what WCAG 2.5.3
 * (label in name) requires and what lets a voice user say the words they can see.
 *
 * Generic over `string | number` so an enum and a count can share one control. `onChange`
 * receives the ORIGINAL option value rather than the DOM's string: a native `<select>`
 * stringifies everything, and an unconditional `Number(...)` coercion is exactly why this
 * could not carry an enum. Values are matched by their string form, so a numeric caller
 * still receives a number.
 */
export function SceneControlSelect<T extends string | number>({
  label,
  accessibleName,
  value,
  options,
  onChange,
  description,
  cost,
  action,
  scopeNote,
  disabled = false,
  className,
}: {
  /** The visible title. Keep it short — it must not wrap at 264px. */
  label: string;
  /**
   * The longer phrasing of what this control is, appended to the visible title to form the
   * select's accessible name. Omit when the title already says the whole thing.
   */
  accessibleName?: string;
  value: T;
  /** Selectable values — bare, or `{value, label}` when the text should differ. */
  options: readonly (T | SceneControlOption<T>)[];
  onChange: (value: T) => void;
  /**
   * One or two sentences saying what this control *does*. Reached by pointer, touch or
   * keyboard through the info button, and announced with the control via `aria-describedby`
   * whether the bubble is open or not. A label alone tells a player what a setting is
   * called; it never tells them what happens if they change it.
   */
  description?: ReactNode;
  /** What it costs, when there is an honest number — tokens, seconds, beats. */
  cost?: ReactNode;
  /**
   * A control that acts *on* this setting rather than setting it — today, the pin that
   * decides whether a change sticks to the scene or lasts one turn.
   *
   * Rendered **outside** the `<label>` deliberately: a button inside a label is activated
   * by clicking the label, so a pin nested there would fire whenever the player aimed at
   * the caption.
   */
  action?: ReactNode;
  /**
   * A short suffix on the caption saying what scope the current value has (e.g. *this
   * turn*). Visible text, because scope must never be carried by colour alone — the pin's
   * own accessible name says the same thing for a screen reader.
   */
  scopeNote?: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const items = normalize(options);
  const helpId = useId();
  const selectId = useId();
  return (
    <div className={cn("flex flex-none flex-col gap-3xs", className)}>
      <div className="flex items-center gap-xs">
        <label
          htmlFor={selectId}
          // `text-ink`, not the `text-mute2` this used to carry. Muted was the other half of
          // "the text is hard to read": a 12px tracked mono caption set in the second-quietest
          // ink on the menu ground is legible in a screenshot and not while playing.
          // `truncate` is a backstop, not the plan — the titles are short enough not to need
          // it, and it keeps a longer one from reflowing the row if a later phase adds one.
          className="min-w-0 flex-1 truncate font-mono text-eyebrow tracking-[0.1em] text-ink uppercase"
        >
          {label}
          {scopeNote ? (
            // The leading space is not decoration — the same trap as `cost`: a CSS margin
            // separates these visually but `textContent` concatenates them, so the caption
            // read "…SAYS AT ONCE· this turn".
            <span className="ml-2xs text-ink-soft normal-case">
              {" "}
              {scopeNote}
            </span>
          ) : null}
        </label>
        {description ? (
          <InfoTip id={helpId} label={label}>
            {description}
            {cost ? (
              // The cost sits with the consequence, not in a separate readout: "what it does"
              // and "what it costs" are one decision, and separating them makes the player
              // read twice to make it once. The leading space is the `textContent` trap
              // again — the description ran together as "its own length.≈ 260 tokens a beat".
              <span className="ml-2xs font-mono text-eyebrow tracking-[0.04em] text-ink-soft">
                {" "}
                {cost}
              </span>
            ) : null}
          </InfoTip>
        ) : null}
        {action}
      </div>
      <Select
        id={selectId}
        value={String(value)}
        onChange={(e) => {
          const picked = items.find((o) => String(o.value) === e.target.value);
          if (picked) onChange(picked.value);
        }}
        disabled={disabled}
        aria-label={accessibleName ? `${label} — ${accessibleName}` : label}
        aria-describedby={description ? helpId : undefined}
      >
        {items.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>
            {o.label}
          </option>
        ))}
      </Select>
    </div>
  );
}
