"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { ToggleChip } from "@/components/ui/ToggleChip";
import { ContextFilesPanel } from "@/components/feature/ContextFilesPanel";
import { SourceDocumentsPanel } from "@/components/feature/SourceDocumentsPanel";
import {
  ProcessProgress,
  type ProcessStep,
} from "@/components/feature/ProcessProgress";
import { docsForDraft } from "@/lib/readDocs";
import { SceneArtModal } from "@/components/feature/SceneArtModal";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { SETTING_TYPES } from "@/lib/seed-data";
import type { useLibraryState } from "@/features/library/useLibraryState";

const SEG = "font-mono text-[10.5px] tracking-[0.06em] px-[15px] py-[8px] cursor-pointer";

/** The setting prose fields, in reveal order — doubles as the draft progress. */
const SETTING_DRAFT_STEPS: ProcessStep[] = [
  { key: "name", label: "Name" },
  { key: "desc", label: "Description" },
  { key: "atmosphere", label: "Atmosphere" },
  { key: "features", label: "Features" },
  { key: "currentState", label: "Current state" },
];

/**
 * Agentic Setting Creator modal — the setting counterpart to CharacterModal.
 *
 * The author writes a place here (by hand or by prompting Mytheca), fleshing out
 * the by-hand fields (name / type / description) plus the §4.1 node metadata
 * (Atmosphere / Features / Current state). A Scene-art section turns the
 * description into watercolor ComfyUI prompts and renders a persisted WebP
 * establishing image; the read-only **Event timeline** section surfaces the
 * play-accrued §4.1 log as a seam (empty until play exists). A detached
 * context-files column grounds a single generation (never persisted — no RAG).
 *
 * Everything produced is the setting's *own* base description + current state
 * (§1 node properties) — no graph structure (edges/Event/Faction nodes) is built.
 */
export function SettingModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  // Scene-art editor pop-up open state — declared before any early return so the
  // hook order stays stable (rules-of-hooks).
  const [sceneArtOpen, setSceneArtOpen] = useState(false);
  const m = lib.modal;
  if (!m || m.type !== "setting") return null;
  const d = lib.draft;
  const agentic = m.mode === "agentic";
  const isEdit = m.editId != null;
  const seedText = (d._prompt ?? "").trim();
  // Drafting needs either a seed sentence or at least one Draft-tagged reference file.
  const canDraft = Boolean(seedText) || docsForDraft(d._docFiles ?? []).length > 0;
  const imageUrl = d.image ? mediaUrl(d.image) : null;
  const hasDescription = Boolean(
    (d.name || d.desc || d.atmosphere || d.features || "").toString().trim(),
  );
  const canRenderSceneArt = Boolean((d._sceneArtPositive ?? "").trim());
  const timeline = d.timeline ?? [];
  const fieldClass = (key: string) =>
    lib.activeField === key ? "mytheca-field-active" : undefined;

  return (
    <Modal
      open
      onClose={lib.closeModal}
      labelledBy="setting-modal-title"
      className="sm:w-[520px] md:w-[920px] lg:w-[1120px]"
      externalClose
      splitScroll
    >
      <div className="lg:flex lg:min-h-0 lg:flex-1 lg:items-stretch">
        {/* ── Main column (own scroll on lg+) ─────────────────────────── */}
        <div className="min-w-0 p-[22px_26px_24px] lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
          {/* Header — title left; a compact scene-art thumbnail right. */}
          <div className="flex flex-wrap items-center justify-between gap-x-[24px] gap-y-[12px]">
            <div
              id="setting-modal-title"
              className="min-w-0 font-display text-[22px] font-bold text-ink"
            >
              {isEdit ? "Edit Setting" : "New Setting"}
            </div>
            {imageUrl ? (
              <div
                className="h-[48px] w-[85px] flex-none overflow-hidden rounded-[5px] border border-cardbd bg-field"
                aria-hidden
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount */}
                <img src={imageUrl} alt="" className="h-full w-full object-cover" />
              </div>
            ) : null}
          </div>

          {/* Mode toggle — mobile/tablet only. */}
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

          {/* Live draft progress — which field Mytheca is writing right now. */}
          {lib.generating ? (
            <ProcessProgress
              className="mb-[16px]"
              label="Setting draft progress"
              steps={SETTING_DRAFT_STEPS}
              activeKey={lib.activeField}
            />
          ) : null}

          {/* By-hand form (left) + agentic Draft with Mytheca (right). */}
          <div className="md:flex md:items-stretch">
            <div className={cn("md:min-w-0 md:flex-1 md:pr-[26px]", agentic && "hidden md:block")}>
              {d._ai ? (
                <div className="mb-4 flex items-center gap-[9px] rounded-[0_3px_3px_0] border-l-[3px] border-l-narrator bg-[rgba(31,111,107,.12)] p-[9px_12px]">
                  <span aria-hidden className="text-[13px] text-narrator">
                    ❖
                  </span>
                  <span className="font-body text-[13.5px] text-ink">
                    Drafted by Mytheca — review &amp; refine, then save.
                  </span>
                </div>
              ) : null}

              <TextField
                label="Name"
                placeholder="e.g. The Drowned Market"
                value={d.name || ""}
                onChange={(e) => lib.setDraft("name", e.target.value)}
                className={fieldClass("name")}
              />
              <div className="mt-[14px]">
                <FieldLabel>Type</FieldLabel>
                <div className="flex flex-wrap gap-[7px]">
                  {SETTING_TYPES.map((t) => (
                    <ToggleChip
                      key={t}
                      selected={d.type === t}
                      onClick={() => lib.setDraft("type", t)}
                      className="font-mono text-[10px] tracking-[0.05em] uppercase"
                    >
                      {t}
                    </ToggleChip>
                  ))}
                </div>
              </div>
              <TextArea
                label="Description"
                placeholder="One vivid line — the place in a breath (shown on the card)."
                rows={2}
                value={d.desc || ""}
                onChange={(e) => lib.setDraft("desc", e.target.value)}
                className={cn("mt-[14px]", fieldClass("desc"))}
              />
              <TextArea
                label="Atmosphere & senses"
                placeholder="What it feels like to stand here — sights, sounds, smells, light, texture."
                rows={3}
                value={d.atmosphere || ""}
                onChange={(e) => lib.setDraft("atmosphere", e.target.value)}
                className={cn("mt-[14px]", fieldClass("atmosphere"))}
              />
              <TextArea
                label="Notable features"
                placeholder="Fixtures, layout, points of interest a scene can use."
                rows={3}
                value={d.features || ""}
                onChange={(e) => lib.setDraft("features", e.target.value)}
                className={cn("mt-[14px]", fieldClass("features"))}
              />
              <TextArea
                label="Current state"
                placeholder="The here-and-now — time of day, weather, lighting, what's open or barred."
                rows={2}
                value={d.currentState || ""}
                onChange={(e) => lib.setDraft("currentState", e.target.value)}
                className={cn("mt-[14px]", fieldClass("currentState"))}
              />
            </div>

            {/* Agentic draft panel — describe the place; Mytheca drafts it. */}
            <aside
              className={cn(
                "mt-[18px] md:mt-0 md:w-[300px] md:shrink-0 md:border-l md:border-hair-strong md:pl-[26px]",
                !agentic && "hidden md:block",
              )}
            >
              {/* Scene art — compact preview + Edit-image trigger (editor is a pop-up). */}
              <div className="mb-[18px] border-b border-hair-strong pb-[16px]">
                <FieldLabel>Scene art</FieldLabel>
                <div className="overflow-hidden rounded-[6px] border border-cardbd bg-field">
                  {imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
                    <img
                      src={imageUrl}
                      alt={`Establishing image of ${d.name || "the place"}`}
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

              <Eyebrow tracking="0.2em" color="#A8762A" className="mb-[10px] block">
                ❖ Draft with Mytheca
              </Eyebrow>
              <p className="mb-[10px] font-body text-[14px] text-ink">
                Describe the place in a sentence —{" "}
                <span className="text-ink-soft italic">Mytheca drafts the rest.</span>
              </p>
              <TextArea
                aria-label="Describe the place to draft"
                rows={4}
                placeholder="e.g. A flooded undercroft beneath the chapel where the tide leaves strange offerings on the altar…"
                value={d._prompt || ""}
                onChange={(e) => lib.setDraft("_prompt", e.target.value)}
              />
              <Button
                onClick={lib.draftSetting}
                disabled={!canDraft || lib.generating}
                className="mt-[12px] w-full"
              >
                {lib.generating ? "Drafting…" : "❖ Draft with Mytheca"}
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
              {isEdit && m.editId ? (
                <SourceDocumentsPanel
                  storylineId={lib.activeStorylineId}
                  entityType="setting"
                  entityId={m.editId}
                />
              ) : null}
            </aside>
          </div>

          {/* Event timeline — read-only §4.1 seam: empty until play accrues it. */}
          <div
            className={cn(
              "mt-[20px] border-t border-hair-strong pt-[18px]",
              agentic && "hidden md:block",
            )}
          >
            <FieldLabel>Event timeline</FieldLabel>
            {timeline.length ? (
              <ul className="flex flex-col gap-[8px]">
                {timeline.map((entry, i) => (
                  <li
                    key={i}
                    className="rounded-[4px] border border-cardbd bg-field px-[10px] py-[8px] font-body text-[13.5px] text-ink-soft"
                  >
                    {entry.summary}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="font-body text-[12.5px] text-mute">
                A log of what happens here accrues as scenarios play out — it starts
                empty and is written by the story, not authored.
              </p>
            )}
          </div>

          {/* Footer — error + actions. */}
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
                  {lib.pending
                    ? isEdit
                      ? "Saving…"
                      : "Creating…"
                    : isEdit
                      ? "Save Changes"
                      : "Add Setting"}
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Detached context-files column ────────────────────────────── */}
        <ContextFilesPanel
          docFiles={d._docFiles ?? []}
          setDocFiles={(docs) => lib.setDraft("_docFiles", docs)}
          inputId="setting-docs-input"
          show={agentic}
          scroll
        />
      </div>

      {/* Scene-art editor pop-up — prompts, generate, and the rendered preview. */}
      <SceneArtModal
        open={sceneArtOpen}
        onClose={() => setSceneArtOpen(false)}
        name={d.name || ""}
        imageUrl={imageUrl}
        positive={d._sceneArtPositive || ""}
        negative={d._sceneArtNegative || ""}
        onPositiveChange={(v) => lib.setDraft("_sceneArtPositive", v)}
        onNegativeChange={(v) => lib.setDraft("_sceneArtNegative", v)}
        hasDescription={hasDescription}
        generatingPrompts={lib.generatingPrompts}
        onGeneratePrompts={lib.generateSceneArtPrompts}
        canRender={canRenderSceneArt}
        generatingImage={lib.generatingPortrait}
        onGenerate={lib.generateSceneArt}
        error={lib.error}
        activeField={lib.activeField}
      />
    </Modal>
  );
}
