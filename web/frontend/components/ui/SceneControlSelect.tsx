import { cn } from "@/lib/cn";

/**
 * Compact labeled numeric dropdown for the scene composer controls (turn limit,
 * follow-up suggestion count). A tiny mono caption sits above a native `<select>`
 * styled to the field tokens — native so it stays keyboard/screen-reader accessible.
 */
export function SceneControlSelect({
  label,
  value,
  options,
  onChange,
  disabled = false,
  className,
}: {
  label: string;
  value: number;
  /** Selectable values; `optionLabel` overrides the rendered text (else the number). */
  options: number[];
  onChange: (value: number) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-none flex-col gap-[3px]", className)}>
      <span className="font-mono text-[9px] tracking-[0.12em] text-mute2 uppercase">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        aria-label={label}
        className="rounded-[3px] border border-field-bd bg-field p-[7px_8px] font-mono text-[12px] text-ink focus:border-accent focus:outline-none disabled:opacity-60"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}
