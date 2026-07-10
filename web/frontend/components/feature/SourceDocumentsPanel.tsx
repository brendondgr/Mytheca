"use client";

import { useCallback, useEffect, useState } from "react";
import { Eyebrow } from "@/components/ui/Eyebrow";
import * as api from "@/lib/api";
import type { ContextDocument, EntityScope } from "@/lib/types";

/**
 * The **Source documents** section on a Character/Setting editor's right side: the
 * corpus documents this entity was used as context FOR — auto-captured when **Build the
 * whole world** mined a doc into this entity, plus any the author links by hand. These
 * are provenance *references* (distinct from the files owned by this editor via
 * `ContextFilesPanel`): unlinking removes only the link, never the document.
 *
 * Self-fetching (its own `listContextDocuments` + `add/removeDocumentLink` calls) so it
 * drops into either modal without threading through the library state hook. Only shown
 * for a saved entity (a brand-new one has no id to link to yet).
 */
export function SourceDocumentsPanel({
  storylineId,
  entityType,
  entityId,
}: {
  storylineId: string;
  entityType: EntityScope;
  entityId: string;
}) {
  const [linked, setLinked] = useState<ContextDocument[]>([]);
  const [corpus, setCorpus] = useState<ContextDocument[]>([]);
  const [pick, setPick] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [links, all] = await Promise.all([
        api.listContextDocuments(storylineId, {
          linkedEntityType: entityType,
          linkedEntityId: entityId,
        }),
        api.listContextDocuments(storylineId),
      ]);
      setLinked(links);
      setCorpus(all);
    } catch {
      /* best-effort — leave the section empty on a load failure */
    } finally {
      setLoading(false);
    }
  }, [storylineId, entityType, entityId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const linkedIds = new Set(linked.map((d) => d.id));
  const options = corpus.filter((d) => !linkedIds.has(d.id));

  async function linkPicked() {
    if (!pick) return;
    await api.addDocumentLink(pick, { entityType, entityId });
    setPick("");
    await load();
  }
  async function unlink(docId: string) {
    await api.removeDocumentLink(docId, { entityType, entityId });
    await load();
  }

  return (
    <div className="mt-[18px] border-t border-hair-strong pt-[16px]">
      <Eyebrow tracking="0.2em" color="#A8762A" className="mb-[8px] block">
        ⎙ Source documents
      </Eyebrow>
      <p className="mb-[10px] font-body text-[12.5px] text-ink-soft">
        Documents used as context for this {entityType} — mined during a build or linked
        by hand.
      </p>

      {loading ? (
        <p className="font-mono text-[10.5px] tracking-[0.06em] text-mute uppercase">Loading…</p>
      ) : linked.length > 0 ? (
        <ul className="flex flex-col gap-[6px]">
          {linked.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center justify-between gap-[8px] rounded-[4px] border border-cardbd bg-field px-[10px] py-[6px]"
            >
              <span className="truncate font-mono text-[11px] text-ink-soft" title={doc.name}>
                ⎙ {doc.name}
              </span>
              <button
                type="button"
                aria-label={`Unlink ${doc.name}`}
                onClick={() => void unlink(doc.id)}
                className="flex-none cursor-pointer text-mute hover:text-danger focus-visible:text-danger"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="font-body text-[12px] text-mute">
          No documents linked yet.
        </p>
      )}

      {/* Link an existing corpus document by hand. */}
      {options.length > 0 ? (
        <div className="mt-[10px] flex items-center gap-[6px]">
          <label className="sr-only" htmlFor={`link-doc-${entityId}`}>
            Link a document to this {entityType}
          </label>
          <select
            id={`link-doc-${entityId}`}
            value={pick}
            onChange={(e) => setPick(e.target.value)}
            className="min-w-0 flex-1 rounded-[3px] border border-cardbd bg-field px-[8px] py-[5px] font-mono text-[11px] text-ink-soft focus-visible:border-accent"
          >
            <option value="">Link a document…</option>
            {options.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!pick}
            onClick={() => void linkPicked()}
            className="flex-none cursor-pointer rounded-[3px] border border-cardbd px-[10px] py-[5px] font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:border-accent disabled:opacity-40"
          >
            Link
          </button>
        </div>
      ) : null}
    </div>
  );
}
