"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { DocumentsTable } from "@/components/feature/DocumentsTable";
import { SkeletonLine } from "@/components/ui/Skeleton";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";
import { cn } from "@/lib/cn";
import type { DocCategory } from "@/lib/types";
import { groupByCategory, useDocuments } from "@/features/documents/useDocuments";

type Filter = "all" | DocCategory;
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "character", label: "Characters" },
  { key: "setting", label: "Settings" },
  { key: "other", label: "Other" },
];

/**
 * The dedicated document-manager surface (`/storylines/[id]/documents`): the post-
 * creation home for a world's uploaded reference corpus. Lists EVERY context document
 * (storyline-level + entity-owned) with its usage (category + Draft/RAG/Extract), scope,
 * and the entities it is provenance for — searchable, filterable, and editable in place,
 * so an author with dozens of `.md` files can finally see and adjust what's uploaded.
 */
export function DocumentsView({ storylineId }: { storylineId: string }) {
  const dm = useDocuments(storylineId);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  // A cached corpus lands well inside 300ms; without the gate the skeleton is
  // the flicker it exists to prevent.
  const showLoading = useDelayedFlag(dm.loading);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return dm.docs.filter((d) => {
      const cat = d.category === "select" ? "other" : d.category;
      if (filter !== "all" && cat !== filter) return false;
      if (!q) return true;
      return d.name.toLowerCase().includes(q) || d.content.toLowerCase().includes(q);
    });
  }, [dm.docs, query, filter]);

  const groups = useMemo(() => groupByCategory(filtered), [filtered]);

  return (
    <AppShell>
      <header className="mytheca-header relative z-[15] flex h-[52px] flex-none items-center justify-between gap-3 border-b border-hair-strong px-[16px] shadow-[0_3px_14px_rgba(10,6,2,0.22)] sm:px-[26px]">
        <div className="flex min-w-0 items-center gap-[13px]">
          <span aria-hidden className="text-[16px] text-accent">
            ❖
          </span>
          <span className="font-display text-[20px] font-bold tracking-[0.2em] text-ink">
            MYTHECA
          </span>
          <span className="hidden h-5 w-px bg-hair-strong md:block" aria-hidden />
          <span className="hidden truncate font-mono text-[10.5px] tracking-[0.18em] text-mute uppercase md:block">
            {dm.title ? `${dm.title} · Documents` : "Documents"}
          </span>
        </div>
        <Link
          href={`/${storylineId}`}
          className="rounded-[3px] border border-cardbd px-[11px] py-[5px] font-mono text-[11px] tracking-[0.1em] text-mute uppercase hover:border-accent hover:text-accent focus-visible:border-accent"
        >
          ‹ Library
        </Link>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-[16px] py-[22px] sm:px-[26px]">
        <div className="mx-auto flex max-w-[900px] flex-col gap-[16px]">
          <div>
            <h1 className="font-display text-[26px] font-bold tracking-[0.04em] text-ink">
              Context documents
            </h1>
            <p className="mt-[3px] font-body text-[13.5px] text-ink-soft">
              Every reference document uploaded to this world — adjust how each is used
              (Draft grounding, the retrieval corpus, build-time extraction) or remove it.
            </p>
          </div>

          {/* Toolbar: search + category filter + upload */}
          <div className="flex flex-wrap items-center gap-[10px]">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name or contents…"
              aria-label="Search documents"
              className="min-w-[180px] flex-1 rounded-[4px] border border-cardbd bg-field px-[11px] py-[7px] font-body text-[13px] text-ink placeholder:text-mute2 focus-visible:border-accent"
            />
            <div role="group" aria-label="Filter by category" className="flex flex-wrap gap-[5px]">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  aria-pressed={filter === f.key}
                  onClick={() => setFilter(f.key)}
                  className={cn(
                    "cursor-pointer rounded-full border px-[11px] py-[4px] font-mono text-[10.5px] tracking-[0.08em] uppercase focus-visible:border-accent",
                    filter === f.key
                      ? "border-accent bg-card2 text-ink"
                      : "border-cardbd bg-transparent text-mute hover:border-accent hover:bg-hover hover:text-ink",
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <label
              className="flex cursor-pointer items-center gap-[6px] rounded-[4px] border border-dashed border-accent/60 bg-field px-[12px] py-[7px] font-mono text-[10.5px] tracking-[0.08em] text-accent uppercase hover:bg-hover"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                void dm.addFiles(e.dataTransfer.files, filter === "all" ? "other" : filter);
              }}
            >
              ⤓ {dm.busy ? "Uploading…" : "Upload files"}
              <input
                type="file"
                multiple
                accept=".txt,.md,.markdown,text/plain,text/markdown"
                className="sr-only"
                onChange={(e) => {
                  void dm.addFiles(e.currentTarget.files, filter === "all" ? "other" : filter);
                  e.currentTarget.value = "";
                }}
              />
            </label>
          </div>

          {dm.error ? (
            <div
              role="alert"
              className="content-enter flex flex-wrap items-center justify-between gap-[10px] rounded-[4px] border border-danger/40 bg-danger/10 px-[12px] py-[8px] font-body text-[13px] text-danger"
            >
              <span>{dm.error}</span>
              {/* Without this the corpus is simply gone until a full page
                  reload — a recoverable failure presented as a dead end. */}
              <button
                type="button"
                onClick={dm.retry}
                className="press touch-target cursor-pointer rounded-[3px] border border-danger/50 px-[10px] py-[4px] font-mono text-[10.5px] tracking-[0.08em] uppercase transition-colors duration-fast ease-soft hover:bg-danger/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Try again
              </button>
            </div>
          ) : null}

          {showLoading ? (
            /* Skeleton rows that trace the real table, rather than a bare
               "Loading documents…" line that says nothing about what is
               coming and shifts the layout when it goes. */
            <div aria-busy="true" aria-label="Loading documents" className="flex flex-col gap-[8px]">
              <SkeletonLine width="28%" height="11px" />
              {Array.from({ length: 5 }, (_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-[12px] rounded-[4px] border border-cardbd bg-card px-[12px] py-[10px]"
                >
                  <SkeletonLine width="34%" height="13px" />
                  <SkeletonLine width="18%" height="11px" />
                  <SkeletonLine width="22%" height="11px" />
                </div>
              ))}
            </div>
          ) : dm.loading ? null : dm.docs.length === 0 ? (
            <p className="font-body text-[14px] text-mute">
              No documents uploaded to this world yet. Drop <code className="font-mono text-[12px]">.txt</code>/
              <code className="font-mono text-[12px]">.md</code> files above, or add them from the
              New/Edit Storyline page.
            </p>
          ) : (
            <div className="flex flex-col gap-[18px]">
              <p className="font-mono text-[11px] tracking-[0.06em] text-mute2 uppercase">
                {filtered.length} of {dm.docs.length}{" "}
                {dm.docs.length === 1 ? "document" : "documents"}
              </p>
              {groups.map(([category, catDocs]) => (
                <section key={category} aria-label={`${category} documents`}>
                  <h2 className="mb-[8px] font-mono text-[11px] tracking-[0.16em] text-accent uppercase">
                    {category === "character"
                      ? "Characters"
                      : category === "setting"
                        ? "Settings"
                        : "Other"}{" "}
                    <span className="text-mute2">({catDocs.length})</span>
                  </h2>
                  <DocumentsTable
                    docs={catDocs}
                    entityLabel={dm.entityLabel}
                    onUpdate={dm.updateDoc}
                    onRemove={dm.removeDoc}
                  />
                </section>
              ))}
              {groups.length === 0 ? (
                <DocumentsTable
                  docs={filtered}
                  entityLabel={dm.entityLabel}
                  onUpdate={dm.updateDoc}
                  onRemove={dm.removeDoc}
                />
              ) : null}
            </div>
          )}
        </div>
      </main>
    </AppShell>
  );
}
