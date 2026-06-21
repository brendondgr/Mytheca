"use client";

import { Modal } from "@/components/ui/Modal";
import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import type { Character } from "@/lib/types";

function ProfileLine({
  label,
  color,
  children,
}: {
  label: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <p className="font-body text-[14px] leading-[1.45] text-ink">
      <Eyebrow size={9} tracking="0.1em" color={color} className="mr-[7px]">
        {label}
      </Eyebrow>
      {children}
    </p>
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
  return (
    <Modal open onClose={onClose} labelledBy="profile-name" className="sm:w-[440px]" z={70}>
      <div className="flex items-center gap-4 border-b border-hair p-[22px_24px]">
        <Monogram mono={c.mono} color={c.color} size={64} ring={3} fontSize={24} />
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
        </div>
        <CloseButton onClose={onClose} />
      </div>
      <div className="flex flex-col gap-[13px] p-[18px_24px_22px]">
        <p className="font-body text-[14.5px] leading-[1.4] text-ink-soft italic">
          {c.traits}
        </p>
        <ProfileLine label="Voice" color="#A8762A">
          {c.speech}
        </ProfileLine>
        <ProfileLine label="Goal" color="#A8762A">
          {c.goal}
        </ProfileLine>
        <ProfileLine label="Secret" color="var(--accent)">
          {c.secret}
        </ProfileLine>
        {onEdit ? (
          <div className="flex justify-end pt-1">
            <Button variant="secondary" onClick={() => onEdit(c.id)}>
              ✎ Edit Character
            </Button>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
