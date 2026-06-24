"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { cn } from "@/lib/cn";
import {
  DEFAULT_SEAL_COLOR,
  DEFAULT_SEAL_SYMBOL,
  SEAL_COLORS,
  SEAL_SYMBOLS,
} from "@/lib/seals";
import type { useLibraryState } from "@/features/library/useLibraryState";

const SEG = "font-mono text-[10.5px] tracking-[0.06em] px-[15px] py-[8px] cursor-pointer";

/**
 * Write-first storyline creation modal. Replaces the old one-shot "Untitled
 * Storyline" create: the author writes the world here — a title, genre, one-line
 * tagline, and a multi-paragraph premise — before it's persisted.
 *
 * On desktop (`md+`) the By-hand form fills the left and a right rail holds two
 * forward-looking seams: a drag-and-drop **context files** zone and an agentic
 * **Draft with Velora** panel. Both are visible but **non-functional** — the
 * wiring (file ingest + agentic draft-into-fields) lands later. On mobile a
 * By-hand / Agentically toggle swaps a single column.
 */
export function StorylineModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
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
      className="sm:w-[560px] md:w-[900px]"
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-start justify-between gap-[14px]">
          <div>
            <Eyebrow size={8.5} tracking="0.2em" color="#A8762A">
              {isEdit ? "Edit Storyline" : "New Storyline"}
            </Eyebrow>
            <div
              id="storyline-modal-title"
              className="mt-1 font-display text-[22px] font-bold text-ink"
            >
              {isEdit ? "Edit this World" : "Forge a New World"}
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

        {/* Body — form left, context/agentic seams right (desktop); one at a time (mobile). */}
        <div className="md:flex md:items-stretch md:gap-[26px]">
          {/* By-hand form column */}
          <div className={cn("md:min-w-0 md:flex-1", agentic && "hidden md:block")}>
            {/* Seal — the shape + color shown left of the storyline's name. */}
            <FieldLabel>Seal</FieldLabel>
            <div className="mb-[14px] flex items-start gap-[14px]">
              <div
                aria-hidden
                className="flex h-[46px] w-[46px] flex-none items-center justify-center rounded-[4px] border border-cardbd bg-field text-[24px] leading-none"
                style={{ color: sealColor }}
              >
                {seal}
              </div>
              <div className="min-w-0 flex-1">
                <div role="group" aria-label="Seal symbol" className="flex flex-wrap gap-[6px]">
                  {SEAL_SYMBOLS.map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      aria-label={`Symbol ${sym}`}
                      aria-pressed={seal === sym}
                      onClick={() => lib.setDraft("symbol", sym)}
                      className={cn(
                        "flex h-[28px] w-[28px] items-center justify-center rounded-[4px] border text-[15px] leading-none focus-visible:border-accent",
                        seal === sym
                          ? "border-accent bg-card2 text-ink"
                          : "border-cardbd bg-field text-ink-soft hover:border-accent",
                      )}
                    >
                      {sym}
                    </button>
                  ))}
                </div>
                <div role="group" aria-label="Seal color" className="mt-[8px] flex flex-wrap gap-[7px]">
                  {SEAL_COLORS.map((col) => (
                    <button
                      key={col}
                      type="button"
                      aria-label={`Color ${col}`}
                      aria-pressed={sealColor === col}
                      onClick={() => lib.setDraft("symbolColor", col)}
                      className="h-[22px] w-[22px] rounded-full focus-visible:outline-none"
                      style={{
                        background: col,
                        boxShadow:
                          sealColor === col
                            ? `0 0 0 2px var(--modal-bg), 0 0 0 4px ${col}`
                            : "0 0 0 1px rgba(0,0,0,.15)",
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
            <TextField
              label="Title"
              placeholder="e.g. Embergate"
              value={d.title || ""}
              onChange={(e) => lib.setDraft("title", e.target.value)}
              className="mb-[14px]"
            />
            <TextField
              label="Genre"
              placeholder="e.g. Maritime Intrigue"
              value={d.genre || ""}
              onChange={(e) => lib.setDraft("genre", e.target.value)}
              className="mb-[14px]"
            />
            <TextField
              label="Tagline"
              placeholder="One line for the switcher — what the world is, in a breath."
              value={d.tagline || ""}
              onChange={(e) => lib.setDraft("tagline", e.target.value)}
              className="mb-[14px]"
            />
            <TextArea
              label="Premise"
              placeholder="Write the world in full — its setting, mood, the powers in play, what it's about. Multiple paragraphs welcome."
              rows={7}
              value={d.premise || ""}
              onChange={(e) => lib.setDraft("premise", e.target.value)}
            />

            {/* World Primer — agent-facing runtime context (generated, editable). */}
            <div className="mt-[14px]">
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
                Agent-facing context injected into every scene — what the model
                needs to play this world without looking things up.
              </p>
              <TextArea
                aria-label="World Primer"
                rows={5}
                placeholder="Generate from the seed and premise — or write it yourself. Front-load the always-true facts: tone, the constant proper nouns, the load-bearing rules."
                value={d.worldPrimer || ""}
                onChange={(e) => lib.setDraft("worldPrimer", e.target.value)}
              />
            </div>

            {lib.error ? (
              <p role="alert" className="mt-4 font-body text-[13px] text-accent">
                {lib.error}
              </p>
            ) : null}

            <div className="mt-[22px] flex items-center justify-end gap-[10px]">
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

          {/* Seams column — fixed right rail on desktop, tab panel on mobile. */}
          <aside
            className={cn(
              "md:w-[300px] md:shrink-0 md:border-l md:border-hair-strong md:pl-[26px]",
              !agentic && "hidden md:block",
            )}
          >
            {/* Context files drop zone — visible, non-functional seam. */}
            <Eyebrow size={8.5} tracking="0.2em" color="#A8762A" className="mb-[10px]">
              ⎙ Context files
            </Eyebrow>
            <div
              aria-disabled="true"
              className="flex flex-col items-center gap-[6px] rounded-[4px] border border-dashed border-cardbd bg-field/50 px-[14px] py-[20px] text-center opacity-70"
            >
              <span aria-hidden className="text-[18px] text-mute">
                ⤓
              </span>
              <p className="font-body text-[13.5px] text-ink-soft">
                Drag context files here to ground the world.
              </p>
              <span className="font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase">
                Coming soon
              </span>
            </div>

            {/* Agentic draft panel — visible, non-functional seam. */}
            <Eyebrow size={8.5} tracking="0.2em" color="#A8762A" className="mt-[20px] mb-[10px]">
              ❖ Draft with Velora
            </Eyebrow>
            <p className="mb-[10px] font-body text-[14px] text-ink">
              Describe the world in a sentence —{" "}
              <span className="text-ink-soft italic">Velora drafts the rest.</span>
            </p>
            <TextArea
              aria-label="Describe the world to draft"
              rows={3}
              placeholder="e.g. A rotting harbor town where every secret has a price…"
              value={d._prompt || ""}
              onChange={(e) => lib.setDraft("_prompt", e.target.value)}
            />
            <div className="mt-[12px] flex items-center justify-end gap-[10px]">
              <Button variant="ghost" onClick={lib.closeModal} className="md:hidden">
                Cancel
              </Button>
              <Button onClick={lib.draftStoryline} disabled={!canDraft || lib.generating}>
                {lib.generating ? "Drafting…" : "❖ Draft with Velora"}
              </Button>
            </div>

            {/* Mobile-only error echo: the form column (with its own alert) is
                hidden while the agentic tab is open on small screens. */}
            {lib.error ? (
              <p role="alert" className="mt-4 font-body text-[13px] text-accent md:hidden">
                {lib.error}
              </p>
            ) : null}
          </aside>
        </div>
      </div>
    </Modal>
  );
}
