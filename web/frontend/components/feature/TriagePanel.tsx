"use client";

import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { cn } from "@/lib/cn";
import type { ContextBudget } from "@/lib/contextBudget";
import type { DocCategory } from "@/lib/types";
import type { CreatorDoc } from "@/features/library/storylineCreator";
import { ContextBudgetMeter } from "@/components/feature/ContextBudgetMeter";

const GROUPS: { key: DocCategory; label: string; hint: string }[] = [
  { key: "character", label: "Characters", hint: "Character details" },
  { key: "setting", label: "Settings", hint: "Setting details" },
  { key: "other", label: "Other", hint: "Full / multi-subject documents" },
];

const USES: { key: "useDraft" | "useRag"; label: string; title: string }[] = [
  { key: "useDraft", label: "Draft", title: "World-setting doc — grounds the drafting" },
  { key: "useRag", label: "RAG", title: "Member of the retrieval corpus" },
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
  onSetCategory,
  onTriage,
  triaging,
  budget,
  inputId = "creator-docs-input",
}: {
  docs: CreatorDoc[];
  onAddFiles: (files: FileList | File[] | null) => void;
  onRemove: (name: string) => void;
  onToggleUse: (name: string, key: "useDraft" | "useRag") => void;
  onSetCategory: (name: string, category: DocCategory) => void;
  onTriage: () => void;
  triaging: boolean;
  budget: ContextBudget;
  inputId?: string;
}) {
  const anyTriaged = docs.some((d) => d.triaged);

  function DocRow({ doc }: { doc: CreatorDoc }) {
    return (
      <li className="rounded-[4px] border border-cardbd bg-field px-[10px] py-[8px]">
        <div className="flex items-center justify-between gap-[8px]">
          <span className="truncate font-mono text-[11px] text-ink-soft">⎙ {doc.name}</span>
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
            className="rounded-[3px] border border-cardbd bg-card px-[6px] py-[3px] font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-soft"
          >
            <option value="character">Character</option>
            <option value="setting">Setting</option>
            <option value="other">Other</option>
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
                  "cursor-pointer rounded-full border px-[9px] py-[2px] font-mono text-[9.5px] tracking-[0.08em] uppercase focus-visible:border-accent",
                  on
                    ? "border-accent bg-card2 text-ink"
                    : "border-cardbd bg-transparent text-mute hover:border-accent",
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
    // Full-height right pane on lg+. The aside itself does NOT scroll — the sticky
    // top (upload + triage) stays pinned, and the inner body scrolls independently.
    <aside className="flex flex-col border-t border-hair-strong bg-card lg:w-[360px] lg:shrink-0 lg:border-t-0 lg:border-l lg:min-h-0 lg:self-stretch">
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

        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            onAddFiles(e.dataTransfer.files);
          }}
          className="flex flex-col items-center gap-[6px] rounded-[4px] border border-dashed border-cardbd bg-field/50 px-[14px] py-[16px] text-center"
        >
          <span aria-hidden className="text-[18px] text-mute">
            ⤓
          </span>
          <p className="font-body text-[13px] text-ink-soft">
            Drag <code className="font-mono text-[12px]">.txt</code> or{" "}
            <code className="font-mono text-[12px]">.md</code> files here.
          </p>
          <input
            id={inputId}
            type="file"
            multiple
            accept=".txt,.md,.markdown,text/plain,text/markdown"
            className="sr-only"
            onChange={(e) => {
              onAddFiles(e.currentTarget.files);
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

        <Button
          variant="secondary"
          onClick={onTriage}
          disabled={docs.length === 0 || triaging}
          className="w-full"
        >
          {triaging ? "Triaging…" : "⚖ Triage context"}
        </Button>
      </div>

      {/* ── Scrollable body: doc list + budget meter ─────────────────────── */}
      <div className="flex flex-1 flex-col gap-[14px] overflow-y-auto p-[18px_20px] pt-[16px]">
        {docs.length === 0 ? (
          <p className="font-body text-[13px] text-ink-soft">
            Drop reference files, then Triage sorts each into Characters, Settings, or
            Other and tags it for Draft / RAG. They persist as this world&apos;s corpus.
          </p>
        ) : anyTriaged ? (
          // After triage: grouped by bucket.
          GROUPS.map(({ key, label, hint }) => {
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
          })
        ) : (
          // Before triage: a flat list.
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
