"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { ContextFilesPanel } from "@/components/feature/ContextFilesPanel";
import { StatsEditor } from "@/components/feature/StatsEditor";
import { SealModal } from "@/components/feature/SealModal";
import { cn } from "@/lib/cn";
import { DEFAULT_SEAL_COLOR, DEFAULT_SEAL_SYMBOL } from "@/lib/seals";
import type { useLibraryState } from "@/features/library/useLibraryState";

const SEG = "font-mono text-[10.5px] tracking-[0.06em] px-[15px] py-[8px] cursor-pointer";

/**
 * Write-first storyline creation modal. The author writes the world here — a
 * title, genre, one-line tagline, and a multi-paragraph premise — before it's
 * persisted, with a generated agent-facing World Primer spanning the bottom.
 *
 * Layout (desktop, `lg+`): the **main** column holds the by-hand form (Title +
 * Genre on one row, Tagline, Premise), the agentic **Draft with Velora** seed,
 * and the full-width **World Primer** + actions; a **detached context-files
 * column** runs the full height down the right side, showcasing each dropped
 * `.txt`/`.md` file (read in-browser to ground a single generation — never
 * uploaded/persisted) with per-use toggles (Draft / RAG / KG). On mobile a
 * By-hand / Agentically toggle swaps the form for the draft + context panels.
 */
export function StorylineModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  // Seal editor pop-up open state — declared before the early return so the hook
  // order stays stable (rules-of-hooks).
  const [sealOpen, setSealOpen] = useState(false);
  const m = lib.modal;
  if (!m || m.type !== "storyline") return null;
  const d = lib.draft;
  const agentic = m.mode === "agentic";
  const isEdit = m.editId != null;
  const seal = d.symbol || DEFAULT_SEAL_SYMBOL;
  const sealColor = d.symbolColor || DEFAULT_SEAL_COLOR;
  // Agentic authoring: a seed drafts the metadata; seed-or-premise feeds the primer.
  const seedText = (d._prompt ?? "").trim();
  const premiseText = (d.premise ?? "").trim();
  const canDraft = Boolean(seedText);
  const canGeneratePrimer = Boolean(seedText || premiseText);

  return (
    <Modal
      open
      onClose={lib.closeModal}
      labelledBy="storyline-modal-title"
      className="sm:w-[560px] md:w-[860px] lg:w-[1120px]"
      externalClose
      splitScroll
    >
      {/* Root: main column + detached full-height context column (lg). */}
      <div className="lg:flex lg:min-h-0 lg:flex-1 lg:items-stretch">
        {/* ── Main column (own scroll on lg+) ─────────────────────────── */}
        <div className="min-w-0 p-[22px_26px_24px] lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
          {/* Header — promoted title with the seal right-justified on the same
              row (preview glyph + Edit → the full SealModal pop-up). */}
          <div className="flex flex-wrap items-center justify-between gap-x-[16px] gap-y-[10px]">
            <div
              id="storyline-modal-title"
              className="font-display text-[22px] font-bold text-ink"
            >
              {isEdit ? "Edit Storyline" : "New Storyline"}
            </div>
            <div className="flex items-center gap-[10px]">
              <span className="font-mono text-[9.5px] tracking-[0.1em] text-mute2 uppercase">
                Seal
              </span>
              <div
                aria-hidden
                className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[5px] border border-cardbd bg-field text-[19px] leading-none"
                style={{ color: sealColor }}
              >
                {seal}
              </div>
              <Button variant="secondary" onClick={() => setSealOpen(true)}>
                ✎ Edit
              </Button>
            </div>
          </div>

          {/* Mode toggle — mobile/tablet only. On md+ every panel shows at once. */}
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

          {/* Authoring form (left) + agentic Draft with Velora (right). */}
          <div className="md:flex md:items-stretch">
            <div className={cn("md:min-w-0 md:flex-1 md:pr-[26px]", agentic && "hidden md:block")}>
              {/* Title + Genre share a row; Tagline then Premise span full width. */}
              <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2">
                <TextField
                  label="Title"
                  placeholder="e.g. Embergate"
                  value={d.title || ""}
                  onChange={(e) => lib.setDraft("title", e.target.value)}
                />
                <TextField
                  label="Genre"
                  placeholder="e.g. Maritime Intrigue"
                  value={d.genre || ""}
                  onChange={(e) => lib.setDraft("genre", e.target.value)}
                />
              </div>
              <TextField
                label="Tagline"
                placeholder="One line for the switcher — what the world is, in a breath."
                value={d.tagline || ""}
                onChange={(e) => lib.setDraft("tagline", e.target.value)}
                className="mt-[14px]"
              />
              <TextArea
                label="Premise"
                placeholder="Write the world in full — its setting, mood, the powers in play, what it's about. Multiple paragraphs welcome."
                rows={7}
                value={d.premise || ""}
                onChange={(e) => lib.setDraft("premise", e.target.value)}
                className="mt-[14px]"
              />
            </div>

            {/* Agentic draft panel — describe the world; Velora drafts the fields. */}
            <aside
              className={cn(
                "mt-[18px] md:mt-0 md:w-[300px] md:shrink-0 md:border-l md:border-hair-strong md:pl-[26px]",
                !agentic && "hidden md:block",
              )}
            >
              <Eyebrow size={8.5} tracking="0.2em" color="#A8762A" className="mb-[10px] block">
                ❖ Draft with Velora
              </Eyebrow>
              <p className="mb-[10px] font-body text-[14px] text-ink">
                Describe the world in a sentence —{" "}
                <span className="text-ink-soft italic">Velora drafts the rest.</span>
              </p>
              <TextArea
                aria-label="Describe the world to draft"
                rows={4}
                placeholder="e.g. A rotting harbor town where every secret has a price…"
                value={d._prompt || ""}
                onChange={(e) => lib.setDraft("_prompt", e.target.value)}
              />
              {/* The action spans the full width of the seed box above it. */}
              <Button
                onClick={lib.draftStoryline}
                disabled={!canDraft || lib.generating}
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

              {/* Mobile-only error echo: the main footer (with the alert) is hidden
                  while the agentic tab is open on small screens. */}
              {lib.error ? (
                <p role="alert" className="mt-4 font-body text-[13px] text-accent md:hidden">
                  {lib.error}
                </p>
              ) : null}
            </aside>
          </div>

          {/* World Primer — full-width row beneath the form + draft columns. */}
          <div
            className={cn(
              "mt-[20px] border-t border-hair-strong pt-[18px]",
              agentic && "hidden md:block",
            )}
          >
            <div className="flex items-end justify-between gap-[10px]">
              <FieldLabel>World Primer</FieldLabel>
              <button
                type="button"
                onClick={lib.generatePrimer}
                disabled={!canGeneratePrimer || lib.generatingPrimer}
                className="mb-[6px] cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase enabled:hover:underline disabled:opacity-40"
              >
                {lib.generatingPrimer ? "Generating…" : "❖ Generate primer"}
              </button>
            </div>
            <p className="mb-[8px] font-body text-[12.5px] text-ink-soft">
              Agent-facing context injected into every scene — what the model needs
              to play this world without looking things up.
            </p>
            <TextArea
              aria-label="World Primer"
              rows={6}
              placeholder="Generate from the seed and premise — or write it yourself. Front-load the always-true facts: tone, the constant proper nouns, the load-bearing rules."
              value={d.worldPrimer || ""}
              onChange={(e) => lib.setDraft("worldPrimer", e.target.value)}
            />
          </div>

          {/* Statistics — universal stats + labeled bands, beneath the primer. */}
          <div
            className={cn(
              "mt-[20px] border-t border-hair-strong pt-[18px]",
              agentic && "hidden md:block",
            )}
          >
            <StatsEditor
              stats={d._stats ?? []}
              originalKeys={new Set((d._statsOriginal ?? []).map((s) => s.key))}
              onChange={(next) => lib.setDraft("_stats", next)}
            />
          </div>

          {/* Footer — sticky action bar pinned to the column's bottom so Cancel +
              Save Changes stay visible while the form/stats scroll. Negative
              margins span the column padding; bg-modal hides content beneath. */}
          <div
            className={cn(
              "sticky bottom-0 z-[1] -mx-[26px] -mb-[24px] mt-[20px] border-t border-hair-strong bg-modal px-[26px] pt-[14px] pb-[16px]",
              agentic && "hidden md:block",
            )}
          >
            {lib.error ? (
              <p role="alert" className="mb-3 font-body text-[13px] text-accent">
                {lib.error}
              </p>
            ) : null}
            <div className="flex items-center justify-end gap-[10px]">
              <Button variant="ghost" onClick={lib.closeModal}>
                Cancel
              </Button>
              <Button
                onClick={lib.submitStoryline}
                disabled={!lib.isStorylineValid || lib.pending}
              >
                {lib.pending
                  ? isEdit
                    ? "Saving…"
                    : "Creating…"
                  : isEdit
                    ? "Save Changes"
                    : "Create World"}
              </Button>
            </div>
          </div>
        </div>

        {/* ── Detached context-files column — full height, right side ──── */}
        <ContextFilesPanel
          docFiles={d._docFiles ?? []}
          setDocFiles={(docs) => lib.setDraft("_docFiles", docs)}
          inputId="storyline-docs-input"
          show={agentic}
          scroll
        />
      </div>

      {/* Seal editor pop-up — expanded shapes, colors, and a custom color wheel. */}
      <SealModal
        open={sealOpen}
        onClose={() => setSealOpen(false)}
        symbol={seal}
        color={sealColor}
        onSymbolChange={(sym) => lib.setDraft("symbol", sym)}
        onColorChange={(col) => lib.setDraft("symbolColor", col)}
      />
    </Modal>
  );
}
