"use client";

import { Modal } from "@/components/ui/Modal";
import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { mediaUrl } from "@/lib/api";
import type { Character } from "@/lib/types";

function ProfileCell({
  label,
  color,
  value,
  spanFull,
}: {
  label: string;
  color: string;
  value: string | null | undefined;
  spanFull?: boolean;
}) {
  if (!value) return null;
  return (
    <div className={spanFull ? "col-span-2" : undefined}>
      <Eyebrow size={9} tracking="0.1em" color={color} className="mb-[4px] block">
        {label}
      </Eyebrow>
      <p className="font-body text-[13.5px] leading-[1.45] text-ink">{value}</p>
    </div>
  );
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

  const hasAppearance = Boolean(c.appearance);
  const hasBackground = Boolean(c.background);
  const hasPersonality = Boolean(c.personality);

  return (
    <Modal open onClose={onClose} labelledBy="profile-name" className="sm:w-[560px]" z={70}>
      {/* Header */}
      <div className="flex items-center gap-4 border-b border-hair p-[22px_24px]">
        <Monogram
          mono={c.mono}
          color={c.color}
          size={64}
          ring={3}
          fontSize={24}
          src={c.portrait ? mediaUrl(c.portrait) : undefined}
          alt={c.portrait ? `Portrait of ${c.name}` : undefined}
        />
        <div className="min-w-0 flex-1">
          <div
            id="profile-name"
            className="font-display text-[22px] font-bold leading-[1.05] text-ink"
          >
            {c.name}
          </div>
          <Eyebrow size={9.5} tracking="0.14em" color={c.color} className="mt-[5px] block">
            {c.role}
          </Eyebrow>
          {c.traits ? (
            <p className="mt-[6px] font-body text-[13px] italic leading-[1.35] text-ink-soft">
              {c.traits}
            </p>
          ) : null}
        </div>
        <CloseButton onClose={onClose} />
      </div>

      {/* 2-column body: row-pair grid */}
      <div className="p-[18px_24px_22px]">
        <div className="grid grid-cols-2 gap-x-[20px] gap-y-[14px]">
          {/* Row 1: Appearance | Background (skip row if both empty) */}
          {(hasAppearance || hasBackground) ? (
            <>
              <ProfileCell
                label="Appearance"
                color="#A8762A"
                value={c.appearance}
                spanFull={!hasBackground}
              />
              {hasBackground ? (
                <ProfileCell label="Background" color="#A8762A" value={c.background} />
              ) : null}
            </>
          ) : null}

          {/* Row 2: Personality | Voice */}
          <ProfileCell
            label="Personality"
            color="#A8762A"
            value={c.personality}
            spanFull={!hasPersonality}
          />
          <ProfileCell label="Voice" color="#A8762A" value={c.speech} spanFull={hasPersonality ? false : true} />

          {/* Row 3: Goal | Secret */}
          <ProfileCell label="Goal" color="#A8762A" value={c.goal} />
          <ProfileCell label="Secret" color="var(--accent)" value={c.secret} />

          {/* Row 4: Edit button, full width */}
          {onEdit ? (
            <div className="col-span-2 flex justify-end pt-[4px]">
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
