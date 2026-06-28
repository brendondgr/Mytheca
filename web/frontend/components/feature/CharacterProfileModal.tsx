"use client";

import { Modal } from "@/components/ui/Modal";
import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { mediaUrl } from "@/lib/api";
import type { Character } from "@/lib/types";

const GOLD = "#A8762A";

/**
 * One framed content section (Background, Appearance, …). A bordered manuscript
 * box with a circular glyph badge, a small-caps section header on a hairline
 * rule, and the prose below. Renders nothing when the value is empty so the
 * grid stays tidy.
 */
function ProfileSection({
  label,
  glyph,
  value,
  color = GOLD,
}: {
  label: string;
  glyph: string;
  value: string | null | undefined;
  color?: string;
}) {
  if (!value) return null;
  return (
    <section
      style={{
        border: "1px solid var(--card-bd)",
        background: "var(--card-bg2)",
        borderRadius: 4,
        boxShadow: "0 1px 2px rgba(20,14,6,.06)",
      }}
    >
      <div className="flex items-center gap-[10px] px-[14px] pt-[12px]">
        <span
          aria-hidden
          className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-full text-[13px] leading-none"
          style={{
            color,
            border: `1px solid ${color}`,
            background: "var(--card-bg)",
          }}
        >
          {glyph}
        </span>
        <Eyebrow tracking="0.16em" color={color} className="block">
          {label}
        </Eyebrow>
        <span className="h-px flex-1" style={{ background: "var(--hair-strong)" }} />
      </div>
      <p className="px-[14px] pb-[13px] pt-[9px] font-body text-body-sm leading-[1.5] text-ink">
        {value}
      </p>
    </section>
  );
}

/** Split a free-text traits string ("Energetic · Observant") into tokens. */
function splitTraits(traits: string | null | undefined): string[] {
  if (!traits) return [];
  return traits
    .split(/[·,]/)
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Read-only character profile (opened from cast monograms / the cast list). */
export function CharacterProfileModal({
  character,
  onClose,
  onEdit,
}: {
  character: Character | null;
  onClose: () => void;
  /** Omit in read-only contexts (e.g. the story player) to hide the Edit button. */
  onEdit?: (id: string) => void;
}) {
  if (!character) return null;
  const c = character;
  const traits = splitTraits(c.traits);

  return (
    <Modal
      open
      onClose={onClose}
      labelledBy="profile-name"
      className="sm:w-[640px] md:w-[860px] lg:w-[900px]"
      z={70}
    >
      <div className="relative">
        <CloseButton onClose={onClose} className="absolute right-[16px] top-[16px] z-[2]" />

        {/* Hero: tall portrait (left) · identity + Appearance + Background (right) */}
        <div className="border-b border-hair p-[24px_24px_22px] md:flex md:gap-[24px]">
          {/* Portrait — 2:3 framed, character-color frame + inner hairline + medallion */}
          <div className="relative mx-auto w-[190px] flex-none sm:w-[210px] md:mx-0">
            <div
              className="p-[5px]"
              style={{
                border: `2px solid ${c.color}`,
                borderRadius: 6,
                background: "var(--card-bg2)",
                boxShadow: "0 6px 22px rgba(40,30,16,.16)",
              }}
            >
              <div
                className="relative aspect-[2/3] overflow-hidden"
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
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center">
                    <Monogram mono={c.mono} color={c.color} size={96} ring={2} fontSize={36} />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right column: name · role · trait pills · Background */}
          <div className="mt-[26px] min-w-0 flex-1 pr-[36px] md:mt-0">
            <h2
              id="profile-name"
              className="text-center font-display text-[30px] font-bold uppercase leading-[1.02] tracking-[0.04em] text-ink md:text-left"
            >
              {c.name}
            </h2>
            <div className="flex flex-col items-center md:items-start">
              <Eyebrow size={11} tracking="0.18em" color={c.color} className="mt-[7px] block">
                {c.role}
              </Eyebrow>
              <div className="mt-[10px] h-px w-[64px]" style={{ background: "var(--hair-strong)" }} />
            </div>
            {traits.length > 0 ? (
              <ul className="mt-[12px] flex flex-wrap justify-center gap-[7px] md:justify-start">
                {traits.map((t) => (
                  <li
                    key={t}
                    className="inline-flex items-center gap-[6px] rounded-full px-[10px] py-[4px] font-body text-[13px] italic text-ink-soft"
                    style={{ border: "1px solid var(--card-bd)", background: "var(--card-bg)" }}
                  >
                    <span aria-hidden className="text-[9px] not-italic" style={{ color: c.color }}>
                      ◆
                    </span>
                    {t}
                  </li>
                ))}
              </ul>
            ) : null}

            <div className="mt-[16px] grid grid-cols-1 gap-[14px]">
              <ProfileSection label="Background" glyph="❖" value={c.background} />
            </div>
          </div>
        </div>

        {/* Remaining four sections — 2×2 grid */}
        <div className="p-[20px_24px_24px]">
          <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2">
            <ProfileSection label="Appearance" glyph="◈" value={c.appearance} />
            <ProfileSection label="Personality" glyph="✦" value={c.personality} />
            <ProfileSection label="Voice" glyph="◆" value={c.speech} />
            <ProfileSection label="Goal" glyph="◎" value={c.goal} />
          </div>

          {onEdit ? (
            <div className="mt-[18px] flex justify-end">
              <Button variant="secondary" onClick={() => onEdit(c.id)}>
                ✎ Edit Character
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
