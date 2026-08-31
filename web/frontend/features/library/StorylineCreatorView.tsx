"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { StatsEditor } from "@/components/feature/StatsEditor";
import { SealModal } from "@/components/feature/SealModal";
import { StyleGuideModal } from "@/components/feature/StyleGuideModal";
import { TriagePanel } from "@/components/feature/TriagePanel";
import { StorylineAgentPanel } from "@/components/feature/StorylineAgentPanel";
import { BuildWorldModal } from "@/components/feature/BuildWorldModal";
import {
  DEFAULT_POPULATE,
  useStorylineCreator,
} from "@/features/library/useStorylineCreator";
import { useStorylineAgent } from "@/features/library/useStorylineAgent";
import type { AppliedFields } from "@/features/library/storylineAgent";
import type { PopulateOptions } from "@/lib/types";

/**
 * The dedicated New / Edit Storyline page (routes `/storylines/new` +
 * `/storylines/[id]/edit`; the empty-state default when no storylines exist).
 *
 * Left: the by-hand fields (title / genre / tagline / premise / World Primer /
 * statistics / seal). Right: the **Triage** context column + budget meter.
 */
export function StorylineCreatorView({ editId }: { editId?: string }) {
  const c = useStorylineCreator(editId);
  const router = useRouter();
  const [sealOpen, setSealOpen] = useState(false);
  const [styleOpen, setStyleOpen] = useState(false);
  const styleCount = Object.values(c.fields.styleBlocks).filter((v) => v.trim()).length;
  const [buildOpen, setBuildOpen] = useState(false);

  const canGeneratePrimer = Boolean(c.fields.premise.trim());

  // The Assistant reads the current form + writes approved changes back into it.
  const onApplied = (patch: AppliedFields) => {
    if (patch.title !== undefined) c.setField("title", patch.title);
    if (patch.genre !== undefined) c.setField("genre", patch.genre);
    if (patch.tagline !== undefined) c.setField("tagline", patch.tagline);
    if (patch.premise !== undefined) c.setField("premise", patch.premise);
    if (patch.worldPrimer !== undefined) c.setField("worldPrimer", patch.worldPrimer);
    if (patch.stats) c.setStats(patch.stats);
    if (patch.styleBlocks) c.setField("styleBlocks", patch.styleBlocks);
  };
  const agent = useStorylineAgent({
    mode: c.isEdit ? "edit" : "create",
    storylineId: editId,
    getFields: () => ({
      title: c.fields.title,
      genre: c.fields.genre,
      tagline: c.fields.tagline,
      premise: c.fields.premise,
      worldPrimer: c.fields.worldPrimer,
      stats: c.stats,
      styleBlocks: c.fields.styleBlocks,
    }),
    // The context files the author kept selected for Draft ground every assistant
    // turn, so a generated title/genre/tagline/premise/primer/stat set is built on
    // the material they uploaded rather than on the form fields alone.
    getDocsOverview: c.docsOverview,
    onApplied,
  });

  // Creating a world asks what to build first (the population step is minutes of
  // generation, so it is never a surprise). Editing saves straight away.
  async function onCommit() {
    if (!c.isEdit) {
      setBuildOpen(true);
      return;
    }
    const id = await c.commit();
    if (id) router.push(`/${id}`);
  }

  // The dialog stays open for the whole run and reports it. A clean finish walks
  // straight into the new world; anything less leaves the dialog up with what was
  // built, so the author decides when to move on.
  async function onBuild(options: PopulateOptions) {
    const { id, state } = await c.createAndBuild(options);
    if (id && state.phase === "done" && state.problems.length === 0) router.push(`/${id}`);
  }

  function enterWorld() {
    setBuildOpen(false);
    if (c.builtId) router.push(`/${c.builtId}`);
  }

  function cancelBuild() {
    c.resetBuild();
    setBuildOpen(false);
  }

  if (c.isEdit && c.loading) {
    return (
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1180px] px-[18px] py-[40px]">
        <p aria-live="polite" className="font-body text-[15px] text-mute">
          Loading the storyline…
        </p>
      </main>
    );
  }

  return (
    // Self-contained one-screen shell: the page never scrolls as a whole. Three columns
    // at lg+ — the **Assistant** left sidebar, the world fields in the center, and the
    // **Context** files right sidebar, each owning an independent vertical scroll. Below
    // lg they stack (the form leads via `order-1`; the two sidebars become bounded strips).
    // `relative` makes this shell the containing block for absolutely-positioned
    // descendants. It used to be what stopped `sr-only` labels escaping `overflow-hidden`
    // and inflating the root scroller; `app/globals.css` now closes that repo-wide by
    // redefining the utility as `position: fixed`, and this stays as a cheap backstop.
    <main id="main" tabIndex={-1} className="relative flex h-dvh min-h-0 flex-col overflow-hidden lg:flex-row">
      {/* ── Left sidebar — the Assistant (own scroll; StorylineAgentPanel is the landmark) ── */}
      <div className="mytheca-rail order-2 flex max-h-[50dvh] min-h-0 shrink-0 flex-col border-t border-hair-strong lg:order-1 lg:max-h-none lg:w-[380px] lg:border-t-0 lg:border-r lg:self-stretch">
        <StorylineAgentPanel agent={agent} mode={c.isEdit ? "edit" : "create"} />
      </div>

      {/* ── Center — the world fields (own scroll) ──────────────────────── */}
      <div className="order-1 min-h-0 flex-1 min-w-0 overflow-y-auto lg:order-2">
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

            {/* Narrative style — how this story is WRITTEN, where the primer above is
                what is true in it. A summary row plus a modal, like the seal below: six
                blocks of prose do not belong inline in a column of form fields. */}
            <div className="mt-[18px] flex items-center justify-between gap-[12px] border-t border-hair-strong pt-[16px]">
              <div className="min-w-0">
                <div className="flex items-end gap-[10px]">
                  <FieldLabel>Narrative style</FieldLabel>
                  <button
                    type="button"
                    onClick={c.generateStyle}
                    disabled={!c.fields.premise.trim() || c.generatingStyle}
                    className="mb-[6px] cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase enabled:hover:underline disabled:opacity-40"
                  >
                    {c.generatingStyle ? "Drafting…" : "❖ Draft style"}
                  </button>
                </div>
                <p className="font-body text-[12.5px] text-ink-soft">
                  {styleCount
                    ? `${styleCount} of 6 set — how the cast writes, not what they know.`
                    : "Optional. How the prose sounds, paces and describes — nothing is said about it until you write one."}
                </p>
              </div>
              <Button variant="secondary" onClick={() => setStyleOpen(true)}>
                {styleCount ? "✎ Edit style" : "❧ Add style"}
              </Button>
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
            <Button onClick={onCommit} disabled={!c.isValid || c.committing}>
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

      {/* ── Right sidebar — Context files (own scroll; TriagePanel is the landmark) ──── */}
      {/* 52dvh, not 42: the stacked strip's sticky header ate ~230px of it, leaving the
          document list about 34px of scroll at 320×720. With the upload setup now collapsed
          by default below `lg` (see `TriagePanel`), the two changes together take the list
          to roughly 260px. Unchanged at `lg`+, where this is a 340px column. */}
      <div className="mytheca-rail order-3 flex max-h-[52dvh] min-h-0 shrink-0 flex-col border-t border-hair-strong lg:max-h-none lg:w-[340px] lg:border-t-0 lg:border-l lg:self-stretch">
        <TriagePanel
          embedded
          docs={c.docs}
          onAddFiles={(files, opts) => void c.addFiles(files, opts)}
          onRemove={c.removeDoc}
          onToggleUse={c.toggleDocUse}
          onSetAllUse={c.setAllDocUse}
          onSetCategory={c.setDocCategory}
          onTriage={c.triage}
          triaging={c.triaging}
          triageActive={c.triageActive}
          budget={c.budget}
        />
      </div>

      <BuildWorldModal
        open={buildOpen}
        build={c.build}
        defaults={DEFAULT_POPULATE}
        worldTitle={c.fields.title}
        sourceFiles={c.sourceFiles}
        onCancel={cancelBuild}
        onConfirm={(options) => void onBuild(options)}
        onStop={c.stopBuild}
        onEnter={enterWorld}
      />

      <SealModal
        open={sealOpen}
        onClose={() => setSealOpen(false)}
        symbol={c.fields.symbol}
        color={c.fields.symbolColor}
        onSymbolChange={(sym) => c.setField("symbol", sym)}
        onColorChange={(col) => c.setField("symbolColor", col)}
      />

      <StyleGuideModal
        open={styleOpen}
        onClose={() => setStyleOpen(false)}
        heading={`${c.fields.title || "This world"} — narrative style`}
        subtitle="How this story is written, not what happens in it. Every field is optional, and a scene can override any of them."
        blocks={c.fields.styleBlocks}
        saveLabel="Keep style"
        // Local only: the guide is saved with the rest of the world when the author
        // commits, so an abandoned edit leaves nothing behind — the same contract every
        // other field on this page has.
        onSave={(next) => c.setField("styleBlocks", next)}
      />
    </main>
  );
}
