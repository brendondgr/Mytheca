"use client";

import Link from "next/link";
import { Modal } from "@/components/ui/Modal";
import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import type { ResolvedScenario } from "@/lib/types";

/** The "enter the scene" preview: narrator opening, cast, setting, goal. */
export function BeginSceneModal({
  scenario,
  storylineId,
  onClose,
}: {
  scenario: ResolvedScenario | null;
  storylineId: string;
  onClose: () => void;
}) {
  if (!scenario) return null;
  const s = scenario;
  return (
    <Modal open onClose={onClose} labelledBy="begin-title" className="sm:w-[560px]">
      <div className="p-[24px_28px]">
        <div className="flex items-center justify-between">
          <div>
            <Eyebrow tracking="0.2em" entity="#A8762A">
              Enter the scene
            </Eyebrow>
            <div id="begin-title" className="mt-1 font-display text-step-2 font-bold text-ink">
              {s.title}
            </div>
          </div>
          <CloseButton onClose={onClose} />
        </div>
        <div className="my-md h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        <div className="rounded-[0_4px_4px_0] border-l-[3px] border-l-narrator bg-[rgba(31,138,130,.12)] p-[14px_16px]">
          <Eyebrow tracking="0.16em" entity="#1F8A82" className="mb-xs block">
            Narrator
          </Eyebrow>
          <p className="font-body text-body-sm leading-[1.5] text-ink italic">{s.opening}</p>
        </div>

        <div className="mt-5 flex gap-xl">
          <div className="flex-1">
            <FieldLabel>Cast at the table</FieldLabel>
            <div className="flex flex-col gap-2">
              {s.cast.map((c) => (
                <div key={c.id} className="flex items-center gap-sm">
                  <Monogram mono={c.mono} color={c.color} size={30} ring={1.5} fontSize={11} />
                  <div className="min-w-0">
                    <div className="font-display text-body-sm font-semibold leading-none text-ink">
                      {c.name}
                    </div>
                    <Eyebrow size={8} tracking="0.1em" entity={c.color} className="mt-3xs block">
                      {c.role}
                    </Eyebrow>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="flex-1">
            <FieldLabel>Setting</FieldLabel>
            <div className="font-display text-body-sm font-semibold text-ink">◆ {s.setting.name}</div>
            <p className="mt-2xs font-body text-label leading-[1.4] text-ink-soft">
              {s.setting.desc}
            </p>
            <FieldLabel className="mt-4">Scene goal</FieldLabel>
            <p className="font-body text-body-sm leading-[1.4] text-ink">{s.goal}</p>
          </div>
        </div>

        <div className="mt-xl flex justify-end gap-sm">
          <Button variant="ghost" onClick={onClose}>
            Not yet
          </Button>
          <Link
            href={`/${storylineId}/${s.id}`}
            className="inline-flex items-center rounded-xs bg-accent px-xl py-md font-mono text-eyebrow uppercase tracking-[0.1em] text-[#F6ECDA] hover-lift press hover:bg-accent-hover hover:shadow-[0_5px_14px_rgba(10,6,3,.3)] active:translate-y-0"
          >
            Enter Scene ▸
          </Link>
        </div>
      </div>
    </Modal>
  );
}
