"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { StatsEditor } from "@/components/feature/StatsEditor";
import { SealModal } from "@/components/feature/SealModal";
import { TriagePanel } from "@/components/feature/TriagePanel";
import { StorylineAgentPanel } from "@/components/feature/StorylineAgentPanel";
import { useStorylineCreator } from "@/features/library/useStorylineCreator";
import { useStorylineAgent } from "@/features/library/useStorylineAgent";
import type { AppliedFields } from "@/features/library/storylineAgent";

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
  const [rightTab, setRightTab] = useState<"assistant" | "context">("assistant");

  const canGeneratePrimer = Boolean(c.fields.premise.trim());

  // The Assistant reads the current form + writes approved changes back into it.
  const onApplied = (patch: AppliedFields) => {
    if (patch.title !== undefined) c.setField("title", patch.title);
    if (patch.genre !== undefined) c.setField("genre", patch.genre);
    if (patch.tagline !== undefined) c.setField("tagline", patch.tagline);
    if (patch.premise !== undefined) c.setField("premise", patch.premise);
    if (patch.worldPrimer !== undefined) c.setField("worldPrimer", patch.worldPrimer);
    if (patch.stats) c.setStats(patch.stats);
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
    }),
    onApplied,
  });

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

      {/* ── Right pane — Assistant / Context (segmented) ────────────────── */}
      <div className="flex max-h-[52dvh] min-h-0 shrink-0 flex-col border-t border-hair-strong bg-card md:max-h-none md:w-[380px] md:border-t-0 md:border-l md:self-stretch">
        <div role="tablist" aria-label="Right pane" className="flex shrink-0 border-b border-hair-strong">
          {(["assistant", "context"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={rightTab === tab}
              onClick={() => setRightTab(tab)}
              className={cn(
                "flex-1 cursor-pointer px-[14px] py-[10px] font-mono text-[10.5px] tracking-[0.1em] uppercase",
                rightTab === tab
                  ? "border-b-2 border-accent text-accent"
                  : "border-b-2 border-transparent text-mute hover:text-ink-soft",
              )}
            >
              {tab === "assistant" ? "❖ Assistant" : "⎙ Context"}
            </button>
          ))}
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          {rightTab === "assistant" ? (
            <StorylineAgentPanel agent={agent} mode={c.isEdit ? "edit" : "create"} />
          ) : (
            <TriagePanel
              embedded
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
        </div>
      </div>

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
