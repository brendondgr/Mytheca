import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { mediaUrl } from "@/lib/api";
import { PORTRAIT_SCRIM, OVER_ART } from "@/lib/cardArt";
import { cn } from "@/lib/cn";
import type { Character, StatDefinition } from "@/lib/types";

/**
 * Compact "beneath the name/role" list of this character's public stat values —
 * the storyline's persisted value when known, else the schema default (matching
 * the backend's own "unset stat = default" semantics). The Library counterpart to
 * the in-scene cast rail's per-character stat rows.
 */
function CardStats({
  statDefs,
  statValues,
  overArt,
}: {
  statDefs: StatDefinition[];
  statValues?: Record<string, number>;
  overArt: boolean;
}) {
  const visible = statDefs.filter((d) => d.visibility === "public");
  if (visible.length === 0) return null;
  return (
    <div className="mt-[6px] flex flex-col gap-[1px]">
      {visible.map((d) => (
        <div key={d.key} className="flex items-baseline justify-between gap-2">
          <span
            className="min-w-0 truncate font-mono text-[9px] tracking-[0.02em]"
            style={{ color: overArt ? OVER_ART.body : "var(--ink-soft)" }}
          >
            {d.displayName}
          </span>
          <span
            className="flex-none font-mono text-[9px]"
            style={{ color: overArt ? OVER_ART.eyebrow : "var(--accent)" }}
          >
            {statValues?.[d.key] ?? d.default}
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * Character card — a tall, portrait-dominant tile (2:3) framed in the character's
 * own color so the picture is the focus. The portrait fills the card behind a
 * bottom scrim that carries the name + role; with no portrait it falls back to a
 * large centered monogram on a solid surface. Clicking the card opens the profile
 * modal (a single stretched button); the edit pencil is a sibling above it (no
 * nested interactives). Cast members of the selected scenario are lit with an
 * animated glow in the character's own color + "◆ In this scene" label
 * (never color alone).
 */
export function CharacterCard({
  character,
  onPreview,
  onEdit,
  highlighted = false,
  statDefs,
  statValues,
}: {
  character: Character;
  /** Opens the character profile modal. */
  onPreview: () => void;
  onEdit?: () => void;
  /** Lit up when this character is in the selected scenario's cast. */
  highlighted?: boolean;
  /** The storyline's stat schema — when given, shows this character's public stat
   * values beneath their name/role (real persisted value, else the schema default). */
  statDefs?: StatDefinition[];
  statValues?: Record<string, number>;
}) {
  const c = character;
  const hasPortrait = Boolean(c.portrait);
  return (
    <div
      className={cn(
        "velora-card group relative aspect-[2/3] overflow-hidden rounded-[4px] hover:-translate-y-[2px] hover:shadow-[0_8px_20px_rgba(20,14,6,.22)]",
        !hasPortrait && "bg-card2",
        highlighted && "velora-glow",
      )}
      style={{
        border: `2px solid ${c.color}`,
        ...(highlighted ? { "--glow-color": c.color } : {}),
      }}
    >
      {hasPortrait ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element -- generated portrait from our media mount */}
          <img
            src={mediaUrl(c.portrait!)}
            alt={`Portrait of ${c.name}`}
            className="pointer-events-none absolute inset-0 h-full w-full object-cover"
          />
          <div
            className="pointer-events-none absolute inset-0"
            style={{ background: PORTRAIT_SCRIM }}
          />
        </>
      ) : (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center pb-[64px]">
          <Monogram mono={c.mono} color={c.color} size={96} ring={2} fontSize={36} />
        </div>
      )}

      {/* Whole-card affordance: open the profile. */}
      <button
        type="button"
        onClick={onPreview}
        aria-label={`View ${c.name}`}
        className="absolute inset-0 z-0 cursor-pointer rounded-[4px]"
      />

      {/* Edit pencil (top-right) — sibling above the stretched button. */}
      {onEdit ? (
        <IconButton
          label={`Edit ${c.name}`}
          onClick={onEdit}
          className="absolute right-[10px] top-[10px] z-[2]"
        >
          ✎
        </IconButton>
      ) : null}

      {/* Footer band: name + role (+ cast badge). Over art it sits on the scrim
          with light text; without art it uses theme ink on the solid surface. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] p-[12px_13px_13px]">
        {highlighted ? (
          <span
            className="mb-[5px] block font-mono text-[8.5px] uppercase tracking-[0.12em]"
            style={{ color: hasPortrait ? OVER_ART.accent : "var(--accent)" }}
          >
            ◆ In this scene
          </span>
        ) : null}
        <span
          className={cn(
            "block font-display text-[16px] font-semibold leading-[1.1]",
            !hasPortrait && "text-ink",
          )}
          style={hasPortrait ? { color: OVER_ART.title } : undefined}
        >
          {c.name}
        </span>
        <Eyebrow
          tracking="0.12em"
          color={hasPortrait ? OVER_ART.eyebrow : c.color}
          className="mt-[3px] block"
        >
          {c.role}
        </Eyebrow>
        {statDefs ? (
          <CardStats statDefs={statDefs} statValues={statValues} overArt={hasPortrait} />
        ) : null}
      </div>
    </div>
  );
}
