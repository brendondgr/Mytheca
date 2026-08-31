"use client";

import { HeaderBar, HeaderLead, HeaderTrail } from "@/components/layout/HeaderBar";
import { useMemo, useState } from "react";
import Link from "next/link";
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
    <>
    {/* No <AppShell> here. The root layout already wraps every route in one;
        rendering a second nested it — two `.mytheca-themed` grounds, two
        MotionProviders, two ToastProviders, and (once the frame gained one) TWO
        skip links, so the first Tab and the second Tab both said "Skip to
        content". A fragment is all this needs: the shell supplies the ground
        and the flex column. */}
      <HeaderBar elevated>
        <HeaderLead>
          <span aria-hidden className="text-step-0 text-accent-ink">
            ❖
          </span>
          <span className="font-display text-step-1 font-bold tracking-[0.2em] text-ink">
            MYTHECA
          </span>
          <span className="h-5 w-px flex-none bg-hair-strong" aria-hidden />
          {/* Shown at EVERY width. This was `hidden md:block`, which meant the
              storyline's name — the only thing telling you WHICH world's
              documents these are — vanished below 768px. That is information
              loss under WCAG 1.4.10, not a responsive technique: the fix for a
              cramped label is to truncate it, which `truncate` + `min-w-0` on
              the lead already does, not to delete it. */}
          <span className="min-w-0 truncate font-mono text-eyebrow tracking-[0.18em] text-mute uppercase">
            {dm.title ? `${dm.title} · Documents` : "Documents"}
          </span>
        </HeaderLead>
        <HeaderTrail>
          <Link
            href={`/${storylineId}`}
            className="rounded-xs border border-cardbd px-md py-xs font-mono text-ui tracking-[0.1em] text-mute uppercase hover:border-accent hover:text-accent-ink focus-visible:border-accent"
          >
            ‹ Library
          </Link>
        </HeaderTrail>
      </HeaderBar>

      <main id="main" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto px-lg py-xl sm:px-xl">
        <div className="mx-auto flex max-w-[900px] flex-col gap-lg">
          <div>
            <h1 className="font-display text-step-2 font-bold tracking-[0.04em] text-ink">
              Context documents
            </h1>
            <p className="mt-3xs font-body text-label text-ink-soft">
              Every reference document uploaded to this world — adjust how each is used
              (Draft grounding, the retrieval corpus, build-time extraction) or remove it.
            </p>
          </div>

          {/* Toolbar: search + category filter + upload */}
          <div className="flex flex-wrap items-center gap-sm">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name or contents…"
              aria-label="Search documents"
              className="min-w-[180px] flex-1 rounded-sm border border-cardbd bg-field px-md py-xs font-body text-field text-ink placeholder:text-mute2 focus-visible:border-accent"
            />
            <div role="group" aria-label="Filter by category" className="flex flex-wrap gap-2xs">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  aria-pressed={filter === f.key}
                  onClick={() => setFilter(f.key)}
                  className={cn(
                    "cursor-pointer rounded-full border px-md py-2xs font-mono text-eyebrow tracking-[0.08em] uppercase focus-visible:border-accent",
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
              className="flex cursor-pointer items-center gap-xs rounded-sm border border-dashed border-accent/60 bg-field px-md py-xs font-mono text-eyebrow tracking-[0.08em] text-accent-ink uppercase hover:bg-hover"
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
              className="content-enter flex flex-wrap items-center justify-between gap-sm rounded-sm border border-danger/40 bg-danger/10 px-md py-sm font-body text-label text-danger-ink"
            >
              <span>{dm.error}</span>
              {/* Without this the corpus is simply gone until a full page
                  reload — a recoverable failure presented as a dead end. */}
              <button
                type="button"
                onClick={dm.retry}
                className="press touch-target cursor-pointer rounded-xs border border-danger/50 px-sm py-2xs font-mono text-eyebrow tracking-[0.08em] uppercase transition-colors duration-fast ease-soft hover:bg-danger/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Try again
              </button>
            </div>
          ) : null}

          {showLoading ? (
            /* Skeleton rows that trace the real table, rather than a bare
               "Loading documents…" line that says nothing about what is
               coming and shifts the layout when it goes. */
            <div aria-busy="true" aria-label="Loading documents" className="flex flex-col gap-sm">
              <SkeletonLine width="28%" height="11px" />
              {Array.from({ length: 5 }, (_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-md rounded-sm border border-cardbd bg-card px-md py-sm"
                >
                  <SkeletonLine width="34%" height="13px" />
                  <SkeletonLine width="18%" height="11px" />
                  <SkeletonLine width="22%" height="11px" />
                </div>
              ))}
            </div>
          ) : dm.loading ? null : dm.docs.length === 0 ? (
            <p className="font-body text-body-sm text-mute">
              No documents uploaded to this world yet. Drop <code className="font-mono text-eyebrow">.txt</code>/
              <code className="font-mono text-eyebrow">.md</code> files above, or add them from the
              New/Edit Storyline page.
            </p>
          ) : (
            <div className="flex flex-col gap-lg">
              <p className="font-mono text-eyebrow tracking-[0.06em] text-mute2 uppercase">
                {filtered.length} of {dm.docs.length}{" "}
                {dm.docs.length === 1 ? "document" : "documents"}
              </p>
              {groups.map(([category, catDocs]) => (
                <section key={category} aria-label={`${category} documents`}>
                  <h2 className="mb-sm font-mono text-eyebrow tracking-[0.16em] text-accent-ink uppercase">
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
    </>
  );
}
