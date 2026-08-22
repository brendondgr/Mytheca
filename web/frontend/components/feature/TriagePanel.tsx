"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { cn } from "@/lib/cn";
import type { ContextBudget } from "@/lib/contextBudget";
import type { DocUse } from "@/lib/readDocs";
import type { DocCategory } from "@/lib/types";
import type { UploadDefaults } from "@/features/library/storylineCreator";
import type { CreatorDoc, TriageActive } from "@/features/library/storylineCreator";
import { ContextBudgetMeter } from "@/components/feature/ContextBudgetMeter";

const GROUPS: { key: DocCategory; label: string; hint: string }[] = [
  { key: "character", label: "Characters", hint: "Character details" },
  { key: "other", label: "Other", hint: "Full / multi-subject documents" },
  { key: "setting", label: "Settings", hint: "Setting details" },
];

const USES: { key: DocUse; label: string; title: string }[] = [
  { key: "useDraft", label: "Draft", title: "World-setting doc — grounds the drafting" },
  { key: "useRag", label: "RAG", title: "Member of the retrieval corpus" },
  {
    key: "useExtract",
    label: "Extract",
    title: "Mine this file for named characters/settings during Build the whole world",
  },
];

/** Category options shown in both the upload-target picker and the per-row select.
 *  Order matches the grouped view (Character / Other / Setting), Uncategorized first. */
const CATEGORY_OPTIONS: { value: DocCategory; label: string }[] = [
  { value: "select", label: "Uncategorized" },
  { value: "character", label: "Character" },
  { value: "other", label: "Other" },
  { value: "setting", label: "Setting" },
];

/**
 * The New Storyline page's context column: drop `.txt`/`.md` files, **Triage** them
 * into Characters / Settings / Other (multi-subject docs land in Other), tune each
 * doc's Draft / RAG inclusion, and watch the context budget. Triaged docs persist as
 * the storyline's corpus on commit (retrieval itself is deferred).
 */
export function TriagePanel({
  docs,
  onAddFiles,
  onRemove,
  onToggleUse,
  onSetAllUse,
  onSetCategory,
  onTriage,
  triaging,
  triageActive = null,
  budget,
  inputId = "creator-docs-input",
  embedded = false,
}: {
  docs: CreatorDoc[];
  onAddFiles: (files: FileList | File[] | null, opts?: UploadDefaults) => void;
  onRemove: (name: string) => void;
  onToggleUse: (name: string, key: DocUse) => void;
  /** Bulk-set one use across every doc (drives De-select All / Re-select All). */
  onSetAllUse?: (key: DocUse, value: boolean) => void;
  onSetCategory: (name: string, category: DocCategory) => void;
  onTriage: () => void;
  triaging: boolean;
  /** The file currently being classified during a live (per-file) triage. */
  triageActive?: TriageActive | null;
  budget: ContextBudget;
  inputId?: string;
  /** When hosted inside a segmented right-pane wrapper, drop the outer column sizing. */
  embedded?: boolean;
}) {
  // Show grouped view as soon as any doc has been categorized — either manually by
  // the author (self-triage) or automatically by the AI Triage button.
  const anyGrouped = docs.some((d) => d.triaged || d.category !== "select");

  // The author's chosen upload target: a whole batch dropped now gets this category +
  // Draft/RAG/Extract, so e.g. a folder of character sheets lands as Characters with no
  // triage. Extract defaults OFF (opt-in — a new storyline never auto-mines docs).
  /**
   * Whether the upload setup is showing. Only meaningful below `lg` — above it the panel is
   * a 360px column with room for everything, and `lg:grid-rows-[1fr]` forces it open in CSS
   * regardless of this value.
   */
  const [uploadOpen, setUploadOpen] = useState(false);
  const uploadPanelId = useId();
  const [uploadCategory, setUploadCategory] = useState<DocCategory>("select");
  const [uploadUses, setUploadUses] = useState<Record<DocUse, boolean>>({
    useDraft: true,
    useRag: true,
    useExtract: false,
  });
  const uploadOpts: UploadDefaults = {
    category: uploadCategory,
    useDraft: uploadUses.useDraft,
    useRag: uploadUses.useRag,
    useExtract: uploadUses.useExtract,
  };

  // Triage now sweeps only what's still Uncategorized; pre-bucketed docs are left alone.
  const uncategorizedCount = docs.filter((d) => d.category === "select").length;

  // The bulk Draft control is a single toggle: it clears the selection while anything
  // is still selected, and restores everything once nothing is.
  const draftCount = docs.filter((d) => d.useDraft).length;
  const allDraftSelected = docs.length > 0 && draftCount > 0;

  function DocRow({ doc }: { doc: CreatorDoc }) {
    const classifying = triaging && triageActive?.name === doc.name;
    return (
      <li
        className={cn(
          "rounded-[4px] border bg-field px-[10px] py-[8px]",
          classifying ? "border-accent" : "border-cardbd",
        )}
      >
        <div className="flex items-center justify-between gap-[8px]">
          <span className="flex min-w-0 items-center gap-[8px]">
            <span className="truncate font-mono text-[11px] text-ink-soft">⎙ {doc.name}</span>
            {classifying ? (
              <span className="flex-none animate-pulse font-mono text-[9px] tracking-[0.08em] text-accent uppercase motion-reduce:animate-none">
                classifying…
              </span>
            ) : null}
          </span>
          <button
            type="button"
            aria-label={`Remove ${doc.name}`}
            onClick={() => onRemove(doc.name)}
            className="flex-none cursor-pointer text-mute hover:text-accent"
          >
            ×
          </button>
        </div>
        <div className="mt-[7px] flex flex-wrap items-center gap-[6px]">
          <label className="sr-only" htmlFor={`cat-${doc.name}`}>
            Category for {doc.name}
          </label>
          <select
            id={`cat-${doc.name}`}
            value={doc.category}
            onChange={(e) => onSetCategory(doc.name, e.target.value as DocCategory)}
            className="rounded-[3px] border border-cardbd bg-card px-[6px] py-[3px] font-mono text-tag uppercase tracking-[0.06em] text-ink-soft"
          >
            {CATEGORY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.value === "select" ? "Select" : o.label}
              </option>
            ))}
          </select>
          {USES.map(({ key, label, title }) => {
            const on = Boolean(doc[key]);
            return (
              <button
                key={key}
                type="button"
                title={title}
                aria-pressed={on}
                aria-label={`${label} for ${doc.name}`}
                onClick={() => onToggleUse(doc.name, key)}
                className={cn(
                  "cursor-pointer rounded-full border px-[9px] py-[2px] font-mono text-tag tracking-[0.08em] uppercase focus-visible:border-accent",
                  on
                    ? "border-accent bg-card2 text-ink"
                    : "border-cardbd bg-transparent text-mute hover:border-accent hover:bg-hover hover:text-ink",
                )}
              >
                {on ? "✓ " : ""}
                {label}
              </button>
            );
          })}
        </div>
      </li>
    );
  }

  return (
    // Contained right pane: a fixed-width column at md+, a bounded strip below md.
    // The aside itself does NOT scroll — the sticky top (upload target + triage) stays
    // pinned and the inner body scrolls independently.
    <aside
      aria-label="Context files"
      className={cn(
        "flex min-h-0 flex-col bg-card",
        embedded
          ? "flex-1"
          : "max-h-[42dvh] shrink-0 border-t border-hair-strong md:max-h-none md:w-[360px] md:border-t-0 md:border-l md:self-stretch",
      )}
    >
      {/* ── Sticky top: upload zone + triage button ─────────────────────── */}
      <div className="sticky top-0 z-10 flex flex-col gap-[12px] border-b border-hair-strong bg-card p-[18px_20px]">
        <div className="flex items-center justify-between gap-[8px]">
          <Eyebrow size={10} tracking="0.2em" color="#A8762A">
            ⎙ Context files
          </Eyebrow>
          {docs.length > 0 ? (
            <span className="font-mono text-[11px] tracking-[0.08em] text-mute uppercase">
              {docs.length} {docs.length === 1 ? "file" : "files"}
            </span>
          ) : null}
        </div>

        {/* Always visible, at every width: the file input's own label, and — below `lg` —
            the control that reveals the upload target and the drop zone.

            `Browse files` lives HERE rather than inside the drop zone because it is the
            keyboard alternative to dragging, and an alternative gated behind a disclosure
            (and behind an animation) is not an alternative. The `sr-only` input travels with
            its label so the `htmlFor` association is never split across a collapsed region. */}
        <div className="flex flex-wrap items-center justify-between gap-[8px]">
          <div className="flex items-center gap-[10px]">
            <input
              id={inputId}
              type="file"
              multiple
              accept=".txt,.md,.markdown,text/plain,text/markdown"
              className="sr-only"
              onChange={(e) => {
                onAddFiles(e.currentTarget.files, uploadOpts);
                e.currentTarget.value = "";
              }}
            />
            <label
              htmlFor={inputId}
              className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:underline"
            >
              Browse files
            </label>
          </div>
          <button
            type="button"
            onClick={() => setUploadOpen((o) => !o)}
            aria-expanded={uploadOpen}
            aria-controls={uploadPanelId}
            className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-mute uppercase hover:text-ink lg:hidden"
          >
            {uploadOpen ? "− Add files" : "＋ Add files"}
          </button>
        </div>

        {/* The SETUP half — where a batch lands, and the drop target. Collapsed below `lg`
            and forced open above it, in CSS: no `useMediaQuery`, so the server and client
            trees never diverge and the first paint is not a swap.

            The split is by urgency, not by importance. An upload target is set once per
            batch; the list underneath is scanned continuously, and at 320×720 it had ~34px
            to do that in. */}
        <div
          id={uploadPanelId}
          className={cn(
            "grid transition-[grid-template-rows] duration-base ease-out motion-reduce:transition-none lg:grid-rows-[1fr]",
            uploadOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
          )}
        >
          {/* `invisible`, not merely clipped. `overflow-hidden` at `0fr` hides this region
              visually but leaves its `<select>` and its two chips in the tab order, so a
              keyboard user lands on controls that are not on screen — the same defect the
              header's single-cluster rule exists to avoid. `visibility: hidden` takes them
              out of the tab order and the accessibility tree, and `lg:visible` restores
              them where the region is always open. */}
          <div
            className={cn(
              "overflow-hidden lg:visible",
              uploadOpen ? "visible" : "invisible",
            )}
          >
            <div className="flex flex-col gap-[12px] pt-[2px]">
            {/* Upload target: pick a bucket + Draft/RAG once, then drop a whole batch. */}
            <div className="flex flex-wrap items-center gap-[6px]">
              <span
                id="upload-as-label"
                className="font-mono text-tag tracking-[0.1em] text-mute2 uppercase"
              >
                Add as
              </span>
              <select
                aria-labelledby="upload-as-label"
                value={uploadCategory}
                onChange={(e) => setUploadCategory(e.target.value as DocCategory)}
                className="rounded-[3px] border border-cardbd bg-card px-[6px] py-[3px] font-mono text-tag uppercase tracking-[0.06em] text-ink-soft"
              >
                {CATEGORY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              {USES.map(({ key, label, title }) => {
                const on = uploadUses[key];
                return (
                  <button
                    key={key}
                    type="button"
                    title={title}
                    aria-pressed={on}
                    aria-label={`Default ${label} for uploads`}
                    onClick={() => setUploadUses((prev) => ({ ...prev, [key]: !prev[key] }))}
                    className={cn(
                      "cursor-pointer rounded-full border px-[9px] py-[2px] font-mono text-tag tracking-[0.08em] uppercase focus-visible:border-accent",
                      on
                        ? "border-accent bg-card2 text-ink"
                        : "border-cardbd bg-transparent text-mute hover:border-accent hover:bg-hover hover:text-ink",
                    )}
                  >
                    {on ? "✓ " : ""}
                    {label}
                  </button>
                );
              })}
            </div>

            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                onAddFiles(e.dataTransfer.files, uploadOpts);
              }}
              className="flex flex-col items-center gap-[6px] rounded-[4px] border border-dashed border-cardbd bg-field/50 px-[14px] py-[16px] text-center"
            >
              <span aria-hidden className="text-[18px] text-mute">
                ⤓
              </span>
              <p className="font-body text-[13px] text-ink-soft">
                Drag <code className="font-mono text-[12px]">.txt</code> or{" "}
                <code className="font-mono text-[12px]">.md</code> files here
                {uploadCategory !== "select" ? (
                  <>
                    {" "}
                    as{" "}
                    <span className="text-ink-soft">
                      {CATEGORY_OPTIONS.find((o) => o.value === uploadCategory)?.label}
                    </span>
                  </>
                ) : null}
                .
              </p>
            </div>
            </div>
          </div>
        </div>

        <Button
          variant="secondary"
          onClick={onTriage}
          disabled={uncategorizedCount === 0 || triaging}
          className="w-full"
        >
          {triaging
            ? triageActive
              ? `Triaging ${triageActive.index + 1}/${triageActive.total}…`
              : "Triaging…"
            : uncategorizedCount > 0
              ? `⚖ Triage Uncategorized (${uncategorizedCount})`
              : "⚖ Triage context"}
        </Button>
        {triaging && triageActive ? (
          <p
            aria-live="polite"
            className="font-mono text-[10px] tracking-[0.06em] text-mute"
          >
            Classifying {triageActive.name}…
          </p>
        ) : null}
      </div>

      {/* ── Draft selection strip: always reachable, never scrolls away ─────
          Draft is the use that decides what grounds the Assistant and the primer, so
          it gets one bulk control. A thin fixed row (rather than a slot in the sticky
          header) keeps the scarce vertical space on the stacked mobile layout. */}
      {docs.length > 0 ? (
        <div className="flex flex-none items-center justify-between gap-[8px] border-b border-hair-strong bg-card px-[20px] py-[7px]">
          <span className="font-mono text-tag tracking-[0.1em] text-mute2 uppercase">
            Draft{" "}
            <span className="text-ink-soft normal-case">
              {draftCount}/{docs.length}
            </span>
          </span>
          <button
            type="button"
            onClick={() => onSetAllUse?.("useDraft", !allDraftSelected)}
            disabled={!onSetAllUse}
            // No `title` here on purpose: a tooltip becomes the accessible name in
            // Chrome and would hide the visible "De-select All" / "Re-select All"
            // label from assistive tech (WCAG 2.5.3, Label in Name).
            // min-h/min-w keep the new control at the WCAG 2.5.8 (AA) 24x24 floor —
            // the older per-row chips predate that and are tracked separately.
            className="inline-flex min-h-[24px] min-w-[24px] cursor-pointer items-center justify-center rounded-full border border-cardbd bg-transparent px-[10px] py-[2px] font-mono text-tag tracking-[0.08em] text-ink-soft uppercase hover:border-accent hover:bg-hover hover:text-ink disabled:cursor-default disabled:opacity-40"
          >
            {allDraftSelected ? "De-select All" : "Re-select All"}
          </button>
        </div>
      ) : null}

      {/* ── Scrollable body: doc list + budget meter ─────────────────────────
          `relative` is now belt-and-braces, not the fix. This is where the `sr-only`
          root-scroller bug was found — each DocRow renders an `sr-only` label, and an
          absolutely-positioned one with no positioned ancestor escaped every
          `overflow: hidden` and grew the ROOT scroller to 6212px for 28 files in a 720px
          viewport. The fix now lives once, in `app/globals.css`, which redefines the
          utility as `position: fixed`; this `relative` is kept because it costs nothing
          and makes the containing block explicit for anything else positioned in here. */}
      <div className="relative flex min-h-0 flex-1 flex-col gap-[14px] overflow-y-auto p-[18px_20px] pt-[16px]">
        {docs.length === 0 ? (
          <p className="font-body text-[13px] text-ink-soft">
            Drop reference files, then use Self-Triage to categorize each one manually —
            or let Triage sort them into Characters, Settings, or Other automatically.
            They persist as this world&apos;s corpus.
          </p>
        ) : anyGrouped ? (
          // Grouped view: one bucket per category, with Uncategorized at the top.
          <>
            {(() => {
              const uncategorized = docs.filter((d) => d.category === "select");
              if (uncategorized.length === 0) return null;
              return (
                <div key="select">
                  <div className="mb-[8px] flex items-baseline gap-[8px]">
                    <span className="font-mono text-[11.5px] font-semibold tracking-[0.12em] text-ink uppercase">
                      Uncategorized
                    </span>
                    <span className="font-mono text-[10.5px] text-mute">· Not yet categorized</span>
                  </div>
                  <ul className="flex flex-col gap-[8px]">
                    {uncategorized.map((doc) => (
                      <DocRow key={doc.name} doc={doc} />
                    ))}
                  </ul>
                </div>
              );
            })()}
            {GROUPS.map(({ key, label, hint }) => {
              const inGroup = docs.filter((d) => d.category === key);
              if (inGroup.length === 0) return null;
              return (
                <div key={key}>
                  <div className="mb-[8px] flex items-baseline gap-[8px]">
                    <span className="font-mono text-[11.5px] font-semibold tracking-[0.12em] text-ink uppercase">
                      {label}
                    </span>
                    <span className="font-mono text-[10.5px] text-mute">· {hint}</span>
                  </div>
                  <ul className="flex flex-col gap-[8px]">
                    {inGroup.map((doc) => (
                      <DocRow key={doc.name} doc={doc} />
                    ))}
                  </ul>
                </div>
              );
            })}
          </>
        ) : (
          // Flat list — no doc has been categorized yet.
          <ul className="flex flex-col gap-[8px]">
            {docs.map((doc) => (
              <DocRow key={doc.name} doc={doc} />
            ))}
          </ul>
        )}

        <ContextBudgetMeter budget={budget} />
      </div>
    </aside>
  );
}
