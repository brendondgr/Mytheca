import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { StatSchema, Relationships } from "@/components/feature/DirectorRail";
import { mediaUrl } from "@/lib/api";
import type { Character, StatDefinition } from "@/lib/types";
import type { Relationship } from "@/features/story-player/scene-data";

/**
 * Right-rail character dossier — takes over the Director rail when a cast member
 * is selected (from the cast list, the scene intro, or a transcript bubble). A
 * full-size portrait header sits above the character's name, title, stats, and
 * relationships, so the profile "hops up" in place instead of a modal. "Back to
 * scene" restores the Director rail.
 */
export function CharacterDossier({
  character,
  statDefs,
  relationships,
  onClose,
  onOpenProfile,
}: {
  character: Character;
  statDefs: StatDefinition[];
  relationships: Relationship[];
  onClose: () => void;
  /** Clicking the portrait opens the full profile modal for this character. */
  onOpenProfile: (id: string) => void;
}) {
  const c = character;
  return (
    <aside
      className="velora-rail hidden w-[248px] flex-none overflow-auto border-l border-hair-strong p-[18px_16px] lg:block"
      aria-label={`${c.name} — profile`}
    >
      <button
        type="button"
        onClick={onClose}
        className="mb-[14px] inline-flex items-center gap-[6px] font-mono text-[10px] tracking-[0.12em] text-mute uppercase hover:text-accent"
      >
        ‹ Back to scene
      </button>

      {/* Portrait header — full rail width, character-color frame. Opens the
          full profile modal on click. */}
      <button
        type="button"
        onClick={() => onOpenProfile(c.id)}
        aria-label={`Open ${c.name}'s full profile`}
        title="Open full profile"
        className="group/portrait block w-full p-[4px]"
        style={{
          border: `2px solid ${c.color}`,
          borderRadius: 6,
          background: "var(--card-bg2)",
          boxShadow: "0 4px 16px rgba(40,30,16,.14)",
        }}
      >
        <div
          className="relative aspect-[2/3] w-full overflow-hidden"
          style={{
            border: "1px solid var(--card-bd)",
            borderRadius: 3,
            background: "var(--field-bg)",
          }}
        >
          {c.portrait ? (
            // eslint-disable-next-line @next/next/no-img-element -- generated portrait from our media mount
            <img
              src={mediaUrl(c.portrait)}
              alt={`Portrait of ${c.name}`}
              className="h-full w-full object-cover transition-transform duration-300 group-hover/portrait:scale-[1.03]"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <Monogram mono={c.mono} color={c.color} size={84} ring={2} fontSize={32} />
            </div>
          )}
          <span className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-center bg-gradient-to-t from-black/55 to-transparent pb-[7px] pt-[18px] font-mono text-[8.5px] tracking-[0.14em] text-[#F6ECDA] uppercase opacity-0 transition-opacity duration-200 group-hover/portrait:opacity-100 group-focus-visible/portrait:opacity-100">
            ⤢ Full profile
          </span>
        </div>
      </button>

      {/* Identity */}
      <h3 className="mt-[14px] font-display text-[19px] font-bold leading-[1.12] text-ink">
        {c.name}
      </h3>
      <Eyebrow size={10} tracking="0.16em" color={c.color} className="mt-[5px] block">
        {c.role}
      </Eyebrow>

      {/* Stats */}
      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Stats
      </Eyebrow>
      <StatSchema defs={statDefs} />

      {/* Relationships */}
      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Relationships
      </Eyebrow>
      <Relationships items={relationships} />

      {/* Lightweight scene context (their aim) — more to come later. */}
      {c.goal ? (
        <>
          <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
            In this scene
          </Eyebrow>
          <p className="font-body text-[13px] leading-[1.45] text-ink-soft italic">
            {c.goal}
          </p>
        </>
      ) : null}
    </aside>
  );
}
