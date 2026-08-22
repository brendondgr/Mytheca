import { LOOSENESS_LABELS } from "@/components/feature/VoiceSamplesEditor";
import { Monogram } from "@/components/ui/Monogram";
import { SmartImage } from "@/components/ui/SmartImage";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { StatSchema, Relationships } from "@/components/feature/DirectorRail";
import { mediaUrl } from "@/lib/api";
import type { Character, StatDefinition } from "@/lib/types";
import type { Relationship, StatChip } from "@/features/story-player/scene-data";

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
  stats,
  relationships,
  onClose,
  onOpenProfile,
}: {
  character: Character;
  statDefs: StatDefinition[];
  /** This character's live stat values (from `state_update` events) — drives the sliders. */
  stats?: StatChip[];
  relationships: Relationship[];
  onClose: () => void;
  /** Clicking the portrait opens the full profile modal for this character. */
  onOpenProfile: (id: string) => void;
}) {
  const c = character;
  // `StatSchema` already renders only `visibility === "public"` defs, so a hidden stat never
  // reaches this rail — the gap was the CHANGES, which used to stream into the transcript
  // (fixed in `turn_effects`), not the values.
  const carriesAnything = statDefs.some((d) => d.visibility === "public" && d.carryOver);

  return (
    <aside
      className="mytheca-rail hidden w-[248px] flex-none overflow-auto border-l border-hair-strong p-[18px_16px] lg:block"
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
          <SmartImage
            src={c.portrait ? mediaUrl(c.portrait) : null}
            alt={`Portrait of ${c.name}`}
            aspect="2 / 3"
            className="h-full w-full"
            imgClassName="transition-transform duration-300 group-hover/portrait:scale-[1.03]"
            placeholder={
              <div className="flex h-full w-full items-center justify-center">
                <Monogram mono={c.mono} color={c.color} size={84} ring={2} fontSize={32} />
              </div>
            }
          />
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
      {/* A stat the author marked `hidden` is not the player's to see. Its changes are
          already withheld from the transcript; showing the value here would give the whole
          thing away in a rail instead. */}
      <StatSchema defs={statDefs} values={stats} />
      {/* The rule, stated where a player can actually find it. They currently cannot learn
          it anywhere, and the answer is not obvious: most stats reset. */}
      <p className="mt-[7px] font-body text-[11.5px] leading-[1.45] text-mute2">
        {carriesAnything
          ? "Some of these carry over into the next scene in this world; the rest start fresh."
          : "These start fresh in every play-through."}
      </p>

      {/* Relationships */}
      <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
        Relationships
      </Eyebrow>
      <Relationships items={relationships} />

      {/* How they sound, read-only. A player watching a character ramble at a funeral
          should be able to find out why without leaving the scene — but editing a
          character mid-play is a different decision, and it is a recorded deferral. */}
      {c.speech || typeof c.looseness === "number" ? (
        <>
          <Eyebrow tracking="0.16em" className="mt-5 mb-[9px] block">
            How they speak
          </Eyebrow>
          {c.speech ? (
            <p className="font-body text-[13px] leading-[1.45] text-ink-soft">{c.speech}</p>
          ) : null}
          {typeof c.looseness === "number" ? (
            <p className="mt-[5px] font-mono text-[10px] tracking-[0.12em] text-mute2 uppercase">
              Word choice · {LOOSENESS_LABELS[c.looseness + 2]}
            </p>
          ) : null}
        </>
      ) : null}

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
