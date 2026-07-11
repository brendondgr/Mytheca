/** One selectable Player-POV target: a present cast member the player can speak AS. */
export interface PovOption {
  id: string;
  name: string;
}

/** A small drama/identity glyph signalling "speak as a character" (decorative). */
function MaskIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 3.5-6 8-6s8 2 8 6" />
    </svg>
  );
}

/**
 * The **Player POV** control — the "Speaking as" native select that lives in the composer's
 * bottom-left controls row, immediately to the right of the Config button. Choosing a cast
 * member makes the player's next line *that character's* line (see `useScenePlay`/the turn
 * engine); "Narrator" (value `""` → `null`) is the default guide/narrator behavior.
 *
 * Native `<select>` (keyboard + screen-reader accessible by default, same pattern as the
 * cast rail's presence control) with an explicit `aria-label`; the closed display shows the
 * current POV so it doubles as the status readout. Hidden entirely when there is no present
 * cast member to speak as (only "Narrator" would remain).
 */
export function PovSelect({
  pov,
  onPovChange,
  options,
}: {
  pov: string | null;
  onPovChange: (id: string | null) => void;
  options: PovOption[];
}) {
  if (options.length === 0) return null;
  return (
    // `min-w-0` (no `flex-none`) lets the control SHRINK on a narrow composer row instead of
    // overflowing — the select truncates its label; the flex-none icon stays put.
    <div className="flex min-w-0 items-center gap-[5px] rounded-[8px] border border-field-bd px-[9px] py-[5px] text-mute focus-within:border-accent focus-within:text-accent hover:border-accent hover:text-accent">
      <span className="flex-none">
        <MaskIcon />
      </span>
      <select
        aria-label="Speaking as"
        value={pov ?? ""}
        onChange={(e) => onPovChange(e.target.value || null)}
        className="min-w-0 max-w-[112px] cursor-pointer truncate bg-transparent font-mono text-[9px] tracking-[0.12em] text-current uppercase focus:outline-none"
      >
        <option value="">Narrator</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </div>
  );
}
