"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import type { ContextDocument, DocCategory, EntityScope } from "@/lib/types";
import type { EntityLabeler } from "@/features/documents/useDocuments";

// The usage flags an author adjusts per document (mirrors the New Storyline triage row):
// "Draft" grounds generation, "RAG" is the retrieval corpus, "Extract" opts the doc into
// build-time mining. Each maps to a persisted ContextDocument flag.
const USES: { key: "includeDraft" | "includeRag" | "includeExtract"; label: string; title: string }[] = [
  { key: "includeDraft", label: "Draft", title: "Ground Mytheca's drafting" },
  { key: "includeRag", label: "RAG", title: "Include in the retrieval corpus" },
  { key: "includeExtract", label: "Extract", title: "Mine for cast/settings on Build the whole world" },
];

const CATEGORIES: DocCategory[] = ["character", "setting", "other"];

function fmtCount(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}K` : `${n}`;
}

/**
 * One document's row in the manager: name + size, its triage category, the three
 * usage toggles, its scope (storyline-level vs. owned by an entity) and any provenance
 * links (entities it is context FOR), plus view-content + delete. Controlled — all
 * mutations bubble to the parent hook.
 */
function DocRow({
  doc,
  entityLabel,
  onUpdate,
  onRemove,
}: {
  doc: ContextDocument;
  entityLabel: EntityLabeler;
  onUpdate: (docId: string, patch: Partial<ContextDocument>) => void;
  onRemove: (docId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const links = doc.links ?? [];

  return (
    <li className="rounded-sm border border-cardbd bg-field px-md py-sm">
      <div className="flex flex-wrap items-center justify-between gap-x-md gap-y-xs">
        <div className="flex min-w-0 items-center gap-sm">
          <span aria-hidden className="text-mute">
            ⎙
          </span>
          <span className="truncate font-mono text-eyebrow text-ink" title={doc.name}>
            {doc.name}
          </span>
          <span className="flex-none font-mono text-eyebrow tracking-[0.06em] text-mute2 uppercase">
            {fmtCount(doc.charCount)} ch
          </span>
        </div>
        <div className="flex items-center gap-xs">
          <label className="sr-only" htmlFor={`cat-${doc.id}`}>
            Category for {doc.name}
          </label>
          <select
            id={`cat-${doc.id}`}
            value={doc.category === "select" ? "other" : doc.category}
            onChange={(e) => onUpdate(doc.id, { category: e.target.value as DocCategory })}
            className="rounded-xs border border-cardbd bg-card px-xs py-3xs font-mono text-field tracking-[0.04em] text-ink-soft uppercase focus-visible:border-accent"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
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
                onClick={() => onUpdate(doc.id, { [key]: !on })}
                className={cn(
                  "cursor-pointer rounded-full border px-sm py-3xs font-mono text-tag tracking-[0.08em] uppercase focus-visible:border-accent",
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
          <button
            type="button"
            aria-expanded={open}
            aria-label={`${open ? "Hide" : "View"} contents of ${doc.name}`}
            onClick={() => setOpen((v) => !v)}
            className="cursor-pointer rounded-xs border border-cardbd px-sm py-3xs font-mono text-tag tracking-[0.08em] text-mute uppercase hover:border-accent hover:text-accent-ink"
          >
            {open ? "Hide" : "View"}
          </button>
          <button
            type="button"
            aria-label={`Delete ${doc.name}`}
            onClick={() => onRemove(doc.id)}
            className="cursor-pointer rounded-xs px-xs py-3xs text-mute hover:text-danger-ink focus-visible:text-danger-ink"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Scope + provenance — where this doc is used. */}
      <div className="mt-xs flex flex-wrap items-center gap-xs font-mono text-eyebrow tracking-[0.04em] uppercase">
        {doc.entityType && doc.entityId ? (
          <span className="rounded-xs border border-cardbd bg-card px-xs py-3xs text-ink-soft">
            ⌂ Owned by {entityLabel(doc.entityType as EntityScope, doc.entityId)}
          </span>
        ) : (
          <span className="text-mute2 normal-case">Storyline-level</span>
        )}
        {links.length > 0 ? (
          <>
            <span className="text-mute2 normal-case">· context for:</span>
            {links.map((lk) => (
              <span
                key={lk.id}
                className="rounded-full border border-accent/50 bg-card2 px-sm py-3xs text-accent-ink normal-case"
              >
                {entityLabel(lk.entityType, lk.entityId)}
              </span>
            ))}
          </>
        ) : null}
      </div>

      {open ? (
        <pre className="mt-sm max-h-[240px] overflow-auto rounded-xs border border-cardbd bg-card p-sm font-mono text-eyebrow leading-[1.6] whitespace-pre-wrap text-ink-soft">
          {doc.content || "(empty)"}
        </pre>
      ) : null}
    </li>
  );
}

/** A sectioned list of context documents with per-doc usage controls. */
export function DocumentsTable({
  docs,
  entityLabel,
  onUpdate,
  onRemove,
}: {
  docs: ContextDocument[];
  entityLabel: EntityLabeler;
  onUpdate: (docId: string, patch: Partial<ContextDocument>) => void;
  onRemove: (docId: string) => void;
}) {
  if (docs.length === 0) {
    return (
      <p className="font-body text-label text-mute">
        No documents match. Upload <code className="font-mono text-eyebrow">.txt</code>/
        <code className="font-mono text-eyebrow">.md</code> files, or clear the filter.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-sm">
      {docs.map((doc) => (
        <DocRow
          key={doc.id}
          doc={doc}
          entityLabel={entityLabel}
          onUpdate={onUpdate}
          onRemove={onRemove}
        />
      ))}
    </ul>
  );
}
