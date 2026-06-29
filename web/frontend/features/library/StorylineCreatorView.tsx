"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { StatsEditor } from "@/components/feature/StatsEditor";
import { SealModal } from "@/components/feature/SealModal";
import { TriagePanel } from "@/components/feature/TriagePanel";
import { WorldBuildPanel } from "@/components/feature/WorldBuildPanel";
import { useStorylineCreator } from "@/features/library/useStorylineCreator";

/**
 * The dedicated New / Edit Storyline page (routes `/storylines/new` +
 * `/storylines/[id]/edit`; the empty-state default when no storylines exist).
 *
 * Left: the by-hand fields (title / genre / tagline / premise / World Primer /
 * statistics / seal). Right: the **Triage** context column + budget meter. Top
 * (create only): the prominent **Build the whole world** entry — it makes plain the
 * world can be built agentically from the start, but requires context (a sentence or
 * dropped files). A build produces a reviewable proposal; nothing persists until
 * "Create World".
 */
export function StorylineCreatorView({ editId }: { editId?: string }) {
  const c = useStorylineCreator(editId);
  const router = useRouter();
  const [sealOpen, setSealOpen] = useState(false);

  const seedText = c.seed.trim();
  const hasDraftDocs = c.docs.some((d) => d.useDraft && d.text);
  const canBuild = Boolean(seedText || hasDraftDocs);
  const canGeneratePrimer = Boolean(seedText || c.fields.premise.trim());
  // While building (or once a proposal exists) the right column shows the live
  // world being built; otherwise it's the Triage / Context-files column.
  const showWorldPanel = c.building || Boolean(c.proposed);

  async function onCommit() {
    const id = await c.commit();
    if (id) router.push(`/${id}`);
  }

  if (c.isEdit && c.loading) {
    return (
      <main className="mx-auto w-full max-w-[1180px] px-[18px] py-[40px]">
        <p aria-live="polite" className="font-body text-[15px] text-mute">
          Loading the storyline…
        </p>
      </main>
    );
  }

  return (
    // Self-contained one-screen shell at every width: the page never scrolls as a
    // whole — the left (world fields) and the right (Context files) each own an
    // independent vertical scroll. Two columns at md+; below md they stack, the
    // fields taking the bulk and the context pane a bounded, scrollable strip.
    <main className="flex h-dvh min-h-0 flex-col overflow-hidden md:flex-row">
      {/* ── Left pane — the world fields (own scroll) ───────────────────── */}
      <div className="min-h-0 flex-1 min-w-0 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[840px] flex-col px-[22px] py-[20px]">
          <Link
            href="/"
            className="font-mono text-[11px] tracking-[0.08em] text-mute uppercase hover:text-accent"
          >
            ‹ Library
          </Link>
          <h1 className="mt-[8px] font-display text-[26px] font-bold text-ink">
            {c.isEdit ? "Edit Storyline" : "New Storyline"}
          </h1>

          {c.error ? (
            <p
              role="alert"
              className="mt-[12px] rounded-[4px] border border-danger/40 bg-card px-[14px] py-[10px] font-body text-[13.5px] text-danger"
            >
              {c.error}
            </p>
          ) : null}

          {/* Build the whole world — agentic entry (create only). */}
          {!c.isEdit ? (
            <section
              aria-label="Build the whole world"
              className="mt-[16px] rounded-[6px] border border-accent/40 bg-card p-[18px_20px]"
            >
              <Eyebrow size={9.5} tracking="0.2em" color="#A8762A">
                ❖ Build the whole world
              </Eyebrow>
              <p className="mt-[8px] font-body text-[14px] text-ink">
                Provide context — a sentence and/or dropped files — and Velora drafts the{" "}
                <span className="italic text-ink-soft">
                  entire world: metadata, World Primer, statistics, a full cast, and settings.
                </span>{" "}
                You review everything before anything is saved.
              </p>
              <TextArea
                label="Describe the world (optional once you've added context files)"
                rows={3}
                placeholder="e.g. A rotting harbor town where every secret has a price…"
                value={c.seed}
                onChange={(e) => c.setSeed(e.target.value)}
                className="mt-[12px]"
              />
              <div className="mt-[12px] flex flex-wrap items-center gap-[10px]">
                <Button onClick={c.build} disabled={!canBuild || c.building}>
                  {c.building ? "Building the world…" : "❖ Build the whole world"}
                </Button>
                <Button variant="ghost" onClick={c.draftMeta} disabled={!seedText || c.drafting}>
                  {c.drafting ? "Drafting…" : "Draft fields only"}
                </Button>
                {!canBuild ? (
                  <span className="font-body text-[12.5px] text-mute">
                    Add a sentence or drop context files to enable.
                  </span>
                ) : null}
              </div>
            </section>
          ) : null}

          {/* The reviewable proposal lives in the right column (WorldBuildPanel),
              building live as Velora drafts it. */}

          {/* Fields */}
          <div className="mt-[16px] min-w-0">
            <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2">
              <TextField
                label="Title"
                placeholder="e.g. Embergate"
                value={c.fields.title}
                onChange={(e) => c.setField("title", e.target.value)}
              />
              <TextField
                label="Genre"
                placeholder="e.g. Maritime Intrigue"
                value={c.fields.genre}
                onChange={(e) => c.setField("genre", e.target.value)}
              />
            </div>
            <TextField
              label="Tagline"
              placeholder="One line for the switcher — what the world is, in a breath."
              value={c.fields.tagline}
              onChange={(e) => c.setField("tagline", e.target.value)}
              className="mt-[14px]"
            />
            <TextArea
              label="Premise"
              placeholder="Write the world in full — setting, mood, the powers in play. Multiple paragraphs welcome."
              rows={6}
              value={c.fields.premise}
              onChange={(e) => c.setField("premise", e.target.value)}
              className="mt-[14px]"
            />

            {/* World Primer */}
            <div className="mt-[18px] border-t border-hair-strong pt-[16px]">
              <div className="flex items-end justify-between gap-[10px]">
                <FieldLabel>World Primer</FieldLabel>
                <button
                  type="button"
                  onClick={c.generatePrimer}
                  disabled={!canGeneratePrimer || c.generatingPrimer}
                  className="mb-[6px] cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase enabled:hover:underline disabled:opacity-40"
                >
                  {c.generatingPrimer ? "Generating…" : "❖ Generate primer"}
                </button>
              </div>
              <p className="mb-[8px] font-body text-[12.5px] text-ink-soft">
                Agent-facing context injected into every scene — keep it lean (see the budget).
              </p>
              <TextArea
                aria-label="World Primer"
                rows={5}
                placeholder="Front-load the always-true facts: tone, the constant proper nouns, the load-bearing rules."
                value={c.fields.worldPrimer}
                onChange={(e) => c.setField("worldPrimer", e.target.value)}
              />
            </div>

            {/* Seal */}
            <div className="mt-[18px] flex items-center justify-between gap-[12px] border-t border-hair-strong pt-[16px]">
              <div className="flex items-center gap-[10px]">
                <span className="font-mono text-tag tracking-[0.1em] text-mute2 uppercase">
                  Seal
                </span>
                <span
                  aria-hidden
                  className="flex h-[34px] w-[34px] items-center justify-center rounded-[5px] border border-cardbd bg-field text-[19px] leading-none"
                  style={{ color: c.fields.symbolColor }}
                >
                  {c.fields.symbol}
                </span>
              </div>
              <Button variant="secondary" onClick={() => setSealOpen(true)}>
                ✎ Edit seal
              </Button>
            </div>

            {/* Statistics */}
            <div className="mt-[18px] border-t border-hair-strong pt-[16px]">
              <StatsEditor
                stats={c.stats}
                originalKeys={c.statsOriginalKeys}
                onChange={c.setStats}
              />
            </div>
          </div>

          {/* Footer actions — sticky to the bottom of the scrolling left pane. */}
          <div className="sticky bottom-0 z-[1] -mx-[22px] mt-[20px] flex flex-wrap items-center justify-end gap-[12px] border-t border-hair-strong bg-page px-[22px] pt-[14px] pb-[16px]">
            {c.committing && c.progress ? (
              <span aria-live="polite" className="mr-auto font-body text-[13px] text-mute">
                {c.progress}
              </span>
            ) : c.isEdit ? (
              <div className="mr-auto flex items-center gap-[10px]">
                <span
                  aria-live="polite"
                  className="font-mono text-[10px] tracking-[0.12em] text-mute2 uppercase"
                >
                  {c.reembedProgress
                    ? c.reembedProgress
                    : c.ragStatus?.available
                      ? `✦ ${c.ragStatus.indexed} embedded`
                      : "✦ vector store off"}
                </span>
                <button
                  type="button"
                  onClick={() => void c.reembed()}
                  disabled={c.reembedding || !c.ragStatus?.available}
                  className="font-mono text-[10px] tracking-[0.1em] text-accent uppercase hover:underline disabled:text-mute2 disabled:no-underline"
                >
                  {c.reembedding ? "Embedding…" : "Re-embed"}
                </button>
              </div>
            ) : null}
            <Link
              href="/"
              className="font-mono text-[11px] tracking-[0.08em] text-mute uppercase hover:text-accent"
            >
              Cancel
            </Link>
            <Button onClick={onCommit} disabled={!c.isValid || c.committing || c.building}>
              {c.committing
                ? c.isEdit
                  ? "Saving…"
                  : "Creating…"
                : c.isEdit
                  ? "Save Changes"
                  : "Create World"}
            </Button>
          </div>
        </div>
      </div>

      {/* ── Right pane — live world build, or the Context files column ───── */}
      {showWorldPanel ? (
        <WorldBuildPanel
          proposed={c.proposed}
          planConcepts={c.planConcepts}
          building={c.building}
          buildStage={c.buildStage}
          renderingImages={c.committing || c.buildingImages}
          onUpdateCharacter={c.updateProposedCharacter}
          onRemoveCharacter={c.removeProposedCharacter}
          onUpdateSetting={c.updateProposedSetting}
          onRemoveSetting={c.removeProposedSetting}
          onDiscard={c.discardProposal}
          imagesAvailable={c.imagesAvailable}
          generateImages={c.generateImages}
          onToggleImages={c.setGenerateImages}
        />
      ) : (
        <TriagePanel
          docs={c.docs}
          onAddFiles={(files, opts) => void c.addFiles(files, opts)}
          onRemove={c.removeDoc}
          onToggleUse={c.toggleDocUse}
          onSetCategory={c.setDocCategory}
          onTriage={c.triage}
          triaging={c.triaging}
          triageActive={c.triageActive}
          budget={c.budget}
        />
      )}

      <SealModal
        open={sealOpen}
        onClose={() => setSealOpen(false)}
        symbol={c.fields.symbol}
        color={c.fields.symbolColor}
        onSymbolChange={(sym) => c.setField("symbol", sym)}
        onColorChange={(col) => c.setField("symbolColor", col)}
      />
    </main>
  );
}
