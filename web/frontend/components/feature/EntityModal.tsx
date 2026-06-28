"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { TextArea } from "@/components/ui/TextArea";
import { ScenarioForm } from "@/components/feature/ScenarioForm";
import { SceneArtModal } from "@/components/feature/SceneArtModal";
import { ContextFilesPanel } from "@/components/feature/ContextFilesPanel";
import { cn } from "@/lib/cn";
import { mediaUrl } from "@/lib/api";
import {
  EDITOR_META,
  PROMPT_EXAMPLES,
  PROMPT_PLACEHOLDERS,
} from "@/features/library/editor";
import type { useLibraryState } from "@/features/library/useLibraryState";

const SEG = "font-mono text-[10.5px] tracking-[0.06em] px-[15px] py-[8px] cursor-pointer";

/**
 * Create/edit modal — scenario-only. Characters and settings each have their own
 * richer agentic modal (CharacterModal / SettingModal); storyline + begin are
 * handled elsewhere.
 *
 * Layout matches CharacterModal / SettingModal: three columns at lg+ —
 * (1) by-hand form, (2) scene-art + Draft-with-Velora aside, (3) ContextFilesPanel.
 * On mobile a By-hand / Agentically toggle swaps columns; the context-files
 * column is only visible in agentic mode on small screens.
 *
 * Dropped context files ground `draftScenario()` in the same way they ground
 * the character and setting drafts — the `_docFiles → draftScenario` wire
 * already exists in useLibraryState.
 */
export function EntityModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  // Declare hook before the early-return guard to keep the hook order stable.
  const [sceneArtOpen, setSceneArtOpen] = useState(false);

  const m = lib.modal;
  if (!m || m.type !== "scenario") return null;
  const type = m.type;
  const meta = EDITOR_META[type];
  const isEdit = lib.isEditing;
  const agentic = m.mode === "agentic";
  const d = lib.draft;

  const imageUrl = d.image ? mediaUrl(d.image) : null;
  const hasDescription = Boolean((d.title || d.goal || d.opening || "").toString().trim());
  const canRenderSceneArt = Boolean((d._sceneArtPositive ?? "").trim());

  return (
    <Modal
      open
      onClose={lib.closeModal}
      labelledBy="entity-modal-title"
      className="sm:w-[520px] md:w-[920px] lg:w-[1120px]"
      externalClose
      splitScroll
    >
      <div className="lg:flex lg:min-h-0 lg:flex-1 lg:items-stretch">
        {/* ── Main column (own scroll on lg+) ─────────────────────────── */}
        <div className="min-w-0 p-[22px_26px_24px] lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
          <div className="flex items-start justify-between gap-[14px]">
            <div
              id="entity-modal-title"
              className="font-display text-[22px] font-bold text-ink"
            >
              {(isEdit ? "Edit " : "New ") + meta.kicker}
            </div>
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
          <div className="md:flex md:items-stretch">
            {/* By-hand form column */}
            <div className={cn("md:min-w-0 md:flex-1 md:pr-[26px]", agentic && "hidden md:block")}>
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

              <ScenarioForm
                draft={d}
                setDraft={lib.setDraft}
                characters={lib.characters}
                settings={lib.settings}
              />
            </div>

            {/* Agentic aside — scene art + Draft with Velora. */}
            <aside
              className={cn(
                "mt-[18px] md:mt-0 md:w-[300px] md:shrink-0 md:border-l md:border-hair-strong md:pl-[26px]",
                !agentic && "hidden md:block",
              )}
            >
              {/* Scene art — compact 16:9 preview + Edit-image trigger. */}
              <div className="mb-[18px] border-b border-hair-strong pb-[16px]">
                <FieldLabel>Scene art</FieldLabel>
                <div className="overflow-hidden rounded-[6px] border border-cardbd bg-field">
                  {imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
                    <img
                      src={imageUrl}
                      alt={`Scene art for ${d.title || "this scenario"}`}
                      className="aspect-[16/9] w-full object-cover"
                    />
                  ) : (
                    <div className="flex aspect-[16/9] w-full flex-col items-center justify-center gap-[6px] px-[10px] text-center">
                      <span aria-hidden className="text-[20px] text-mute2">
                        ◇
                      </span>
                      <span className="font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
                        No scene art yet
                      </span>
                    </div>
                  )}
                </div>
                <Button
                  variant="secondary"
                  onClick={() => setSceneArtOpen(true)}
                  className="mt-[10px] w-full"
                >
                  ✎ Edit image
                </Button>
              </div>

              <Eyebrow
                tracking="0.2em"
                color="#A8762A"
                className="mb-[10px] block"
              >
                ❖ Draft with Velora
              </Eyebrow>
              <p className="mb-[10px] font-body text-[14px] text-ink">
                Describe it in a sentence or two —{" "}
                <span className="text-ink-soft italic">Velora drafts the rest.</span>
              </p>
              <TextArea
                aria-label="Describe what to draft"
                rows={4}
                placeholder={PROMPT_PLACEHOLDERS[type]}
                value={d._prompt || ""}
                onChange={(e) => lib.setDraft("_prompt", e.target.value)}
              />
              <div className="mt-[9px] flex flex-wrap items-center gap-[9px]">
                <Eyebrow tracking="0.14em">
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
              <Button
                onClick={lib.draftScenario}
                disabled={lib.generating}
                className="mt-[12px] w-full"
              >
                {lib.generating ? "Drafting…" : "❖ Draft with Velora"}
              </Button>
              <Button
                variant="ghost"
                onClick={lib.closeModal}
                className="mt-[10px] w-full md:hidden"
              >
                Cancel
              </Button>
              {lib.error ? (
                <p role="alert" className="mt-4 font-body text-[13px] text-accent md:hidden">
                  {lib.error}
                </p>
              ) : null}
            </aside>
          </div>

          {/* Footer — error + delete/cancel/save actions. */}
          <div className={cn(agentic && "hidden md:block")}>
            {lib.error ? (
              <p role="alert" className="mt-4 font-body text-[13px] text-accent">
                {lib.error}
              </p>
            ) : null}
            <div className="mt-[20px] flex items-center justify-between gap-[10px]">
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
        </div>

        {/* ── Detached context-files column ────────────────────────────── */}
        <ContextFilesPanel
          docFiles={d._docFiles ?? []}
          setDocFiles={(docs) => lib.setDraft("_docFiles", docs)}
          inputId="scenario-docs-input"
          show={agentic}
          scroll
        />
      </div>

      {/* Scene-art editor pop-up — prompts, generate, and the rendered preview. */}
      <SceneArtModal
        open={sceneArtOpen}
        onClose={() => setSceneArtOpen(false)}
        name={d.title || ""}
        imageUrl={imageUrl}
        positive={d._sceneArtPositive || ""}
        negative={d._sceneArtNegative || ""}
        onPositiveChange={(v) => lib.setDraft("_sceneArtPositive", v)}
        onNegativeChange={(v) => lib.setDraft("_sceneArtNegative", v)}
        hasDescription={hasDescription}
        generatingPrompts={lib.generatingPrompts}
        onGeneratePrompts={lib.generateScenarioSceneArtPrompts}
        canRender={canRenderSceneArt}
        generatingImage={lib.generatingPortrait}
        onGenerate={lib.generateScenarioSceneArt}
        error={lib.error}
      />
    </Modal>
  );
}
