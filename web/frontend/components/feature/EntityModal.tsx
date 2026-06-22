"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextArea } from "@/components/ui/TextArea";
import { CharacterForm } from "@/components/feature/CharacterForm";
import { SettingForm } from "@/components/feature/SettingForm";
import { ScenarioForm } from "@/components/feature/ScenarioForm";
import { cn } from "@/lib/cn";
import {
  EDITOR_META,
  PROMPT_EXAMPLES,
  PROMPT_PLACEHOLDERS,
  type EntityType,
} from "@/features/library/editor";
import type { useLibraryState } from "@/features/library/useLibraryState";

const WIDTH: Record<EntityType, string> = {
  character: "sm:w-[560px]",
  setting: "sm:w-[520px]",
  scenario: "sm:w-[600px]",
};

const SEG = "font-mono text-[10.5px] tracking-[0.06em] px-[15px] py-[8px] cursor-pointer";

/** Create/edit modal: a By-hand / Agentically mode toggle over a per-type form. */
export function EntityModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  const m = lib.modal;
  if (!m || m.type === "begin") return null;
  const type: EntityType = m.type;
  const meta = EDITOR_META[type];
  const isEdit = lib.isEditing;
  const agentic = m.mode === "agentic";
  const d = lib.draft;

  return (
    <Modal
      open
      onClose={lib.closeModal}
      labelledBy="entity-modal-title"
      className={WIDTH[type]}
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-start justify-between gap-[14px]">
          <div>
            <Eyebrow size={8.5} tracking="0.2em" color="#A8762A">
              {(isEdit ? "Edit " : "New ") + meta.kicker}
            </Eyebrow>
            <div
              id="entity-modal-title"
              className="mt-1 font-display text-[22px] font-bold text-ink"
            >
              {isEdit ? meta.edit : meta.create}
            </div>
          </div>
          <CloseButton onClose={lib.closeModal} />
        </div>

        <div className="mt-[14px] inline-flex overflow-hidden rounded-full border border-field-bd bg-card">
          <button
            type="button"
            onClick={() => lib.setMode("manual")}
            className={cn(SEG, agentic ? "bg-transparent text-mute" : "bg-accent text-[#F6ECDA]")}
          >
            ✎ By hand
          </button>
          <button
            type="button"
            onClick={() => lib.setMode("agentic")}
            className={cn(SEG, agentic ? "bg-accent text-[#F6ECDA]" : "bg-transparent text-mute")}
          >
            ❖ Agentically
          </button>
        </div>
        <div className="my-[16px] h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        {agentic ? (
          <div>
            <div className="mb-[11px] flex items-center gap-[9px]">
              <span aria-hidden className="text-[15px] text-accent">
                ❖
              </span>
              <p className="font-body text-[15px] text-ink">
                Describe it in a sentence or two —{" "}
                <span className="text-ink-soft italic">Velora drafts the rest.</span>
              </p>
            </div>
            <TextArea
              aria-label="Describe what to draft"
              rows={4}
              placeholder={PROMPT_PLACEHOLDERS[type]}
              value={d._prompt || ""}
              onChange={(e) => lib.setDraft("_prompt", e.target.value)}
            />
            <div className="mt-[9px] flex flex-wrap items-center gap-[9px]">
              <Eyebrow size={8.5} tracking="0.14em">
                Try
              </Eyebrow>
              {PROMPT_EXAMPLES[type].map((ex) => (
                <button
                  key={ex.short}
                  type="button"
                  onClick={() => lib.setDraft("_prompt", ex.full)}
                  className="rounded-[14px] border border-dashed border-cardbd bg-field px-[11px] py-1 font-body text-[12.5px] text-ink-soft italic hover:border-accent hover:text-accent"
                >
                  {ex.short}
                </button>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-[10px]">
              <Button variant="ghost" onClick={lib.closeModal}>
                Cancel
              </Button>
              <Button onClick={lib.generate} disabled={lib.generating}>
                {lib.generating ? "Drafting…" : "❖ Draft with Velora"}
              </Button>
            </div>
          </div>
        ) : (
          <div>
            {d._ai ? (
              <div className="mb-4 flex items-center gap-[9px] rounded-[0_3px_3px_0] border-l-[3px] border-l-narrator bg-[rgba(31,111,107,.12)] p-[9px_12px]">
                <span aria-hidden className="text-[13px] text-narrator">
                  ❖
                </span>
                <span className="font-body text-[13.5px] text-ink">
                  Drafted by Velora — review &amp; refine, then save.
                </span>
              </div>
            ) : null}

            {type === "character" ? <CharacterForm draft={d} setDraft={lib.setDraft} /> : null}
            {type === "setting" ? <SettingForm draft={d} setDraft={lib.setDraft} /> : null}
            {type === "scenario" ? (
              <ScenarioForm
                draft={d}
                setDraft={lib.setDraft}
                toggleCast={lib.toggleDraftCast}
                characters={lib.characters}
                settings={lib.settings}
              />
            ) : null}
            {lib.error ? (
              <p role="alert" className="mt-4 font-body text-[13px] text-accent">
                {lib.error}
              </p>
            ) : null}

            <div className="mt-[22px] flex items-center justify-between gap-[10px]">
              {isEdit ? (
                <button
                  type="button"
                  onClick={lib.deleteEntity}
                  disabled={lib.pending}
                  className="cursor-pointer p-[6px] font-mono text-[10.5px] tracking-[0.06em] text-accent uppercase hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {lib.pending ? "Deleting…" : "Delete"}
                </button>
              ) : (
                <span />
              )}
              <div className="flex gap-[10px]">
                <Button variant="ghost" onClick={lib.closeModal}>
                  Cancel
                </Button>
                <Button onClick={lib.submit} disabled={!lib.isValid || lib.pending}>
                  {lib.pending ? "Saving…" : isEdit ? meta.save : meta.ok}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
