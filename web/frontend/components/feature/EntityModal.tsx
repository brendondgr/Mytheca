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

// Single-column widths (mobile / tablet, tab-switched) grow into a wide
// two-column layout on desktop, where the agentic chat sits beside the form.
const WIDTH: Record<EntityType, string> = {
  character: "sm:w-[560px] md:w-[920px]",
  setting: "sm:w-[520px] md:w-[880px]",
  scenario: "sm:w-[600px] md:w-[960px]",
};

const SEG = "font-mono text-[10.5px] tracking-[0.06em] px-[15px] py-[8px] cursor-pointer";

/**
 * Create/edit modal. On mobile a By-hand / Agentically toggle swaps between the
 * per-type form and the agentic draft panel. On desktop both show at once — the
 * form fills the left, the agentic chat panel sits in a fixed right column so you
 * can prompt Velora and watch it build live into the form fields.
 */
export function EntityModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  const m = lib.modal;
  if (!m || m.type === "begin" || m.type === "storyline") return null;
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

        {/* Mode toggle — mobile/tablet only. On desktop both panels show at once. */}
        <div className="mt-[14px] inline-flex overflow-hidden rounded-full border border-field-bd bg-card md:hidden">
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

        {/* Body — form left, agentic chat right (desktop); one at a time (mobile). */}
        <div className="md:flex md:items-stretch md:gap-[26px]">
          {/* By-hand form column */}
          <div className={cn("md:min-w-0 md:flex-1", agentic && "hidden md:block")}>
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

          {/* Agentic chat column — fixed right rail on desktop, tab panel on mobile. */}
          <aside
            className={cn(
              "md:w-[330px] md:shrink-0 md:border-l md:border-hair-strong md:pl-[26px]",
              !agentic && "hidden md:block",
            )}
          >
            <Eyebrow
              size={8.5}
              tracking="0.2em"
              color="#A8762A"
              className="mb-[12px] hidden md:block"
            >
              ❖ Draft with Velora
            </Eyebrow>
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
              <Button variant="ghost" onClick={lib.closeModal} className="md:hidden">
                Cancel
              </Button>
              <Button onClick={lib.generate} disabled={lib.generating}>
                {lib.generating ? "Drafting…" : "❖ Draft with Velora"}
              </Button>
            </div>
          </aside>
        </div>
      </div>
    </Modal>
  );
}
