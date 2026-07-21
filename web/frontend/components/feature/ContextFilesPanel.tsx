"use client";

import { Eyebrow } from "@/components/ui/Eyebrow";
import { cn } from "@/lib/cn";
import { readDocFiles, type DocUse, type ReadDoc } from "@/lib/readDocs";

// Per-context usage toggles shown on each dropped reference file. "Draft" grounds
// Mytheca's drafting + generation (wired); "RAG" marks the retrieval corpus (the New
// Storyline page persists it; retrieval itself is a later plan).
const DOC_USES: { key: DocUse; label: string; title: string }[] = [
  { key: "useDraft", label: "Draft", title: "Ground Mytheca's drafting" },
  { key: "useRag", label: "RAG", title: "Include in the retrieval corpus" },
];

/**
 * Detached, full-height context-files column shared by the storyline and
 * character creation modals. Showcases each dropped `.txt`/`.md` file (read
 * in-browser to ground a single generation — never uploaded or persisted) with
 * per-use toggles (Draft / RAG / KG) and bulk select/deselect per category.
 *
 * State lives on the caller's draft (`_docFiles`); this is a controlled view over
 * `docFiles` + `setDocFiles`.
 */
export function ContextFilesPanel({
  docFiles,
  setDocFiles,
  inputId,
  show,
  scroll = false,
}: {
  docFiles: ReadDoc[];
  setDocFiles: (docs: ReadDoc[]) => void;
  /** Unique id for the file input (distinct per modal). */
  inputId: string;
  /** Visible on small screens only when the agentic tab is open; always on md+. */
  show: boolean;
  /**
   * Own an independent vertical scroll at `lg+` (paired with the host Modal's
   * `splitScroll`), so this column scrolls separately from the edit column.
   */
  scroll?: boolean;
}) {
  // Read dropped/selected files into memory and merge them by name. New files
  // default to all three uses ON; re-dropping a name keeps the prior choice.
  async function addFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const read = await readDocFiles(Array.from(files));
    if (read.length === 0) return;
    const byName = new Map(docFiles.map((doc) => [doc.name, doc]));
    for (const doc of read) {
      const prev = byName.get(doc.name);
      byName.set(doc.name, {
        ...doc,
        useDraft: prev?.useDraft ?? true,
        useRag: prev?.useRag ?? true,
      });
    }
    setDocFiles(Array.from(byName.values()));
  }
  function removeFile(name: string) {
    setDocFiles(docFiles.filter((doc) => doc.name !== name));
  }
  function toggleDocUse(name: string, key: DocUse) {
    setDocFiles(
      docFiles.map((doc) =>
        doc.name === name ? { ...doc, [key]: !(doc[key] ?? true) } : doc,
      ),
    );
  }
  // Bulk select/deselect every context for one category — essential when many
  // files are dropped in at once.
  function setAllDocUse(key: DocUse, value: boolean) {
    setDocFiles(docFiles.map((doc) => ({ ...doc, [key]: value })));
  }

  return (
    <aside
      className={cn(
        "flex-col bg-card p-[20px_22px_22px] lg:w-[330px] lg:shrink-0",
        "border-t border-hair-strong lg:border-t-0 lg:border-l",
        scroll && "lg:min-h-0 lg:overflow-y-auto",
        show ? "flex md:flex" : "hidden md:flex",
      )}
    >
      <div className="mb-[10px] flex items-center justify-between gap-[8px]">
        <Eyebrow tracking="0.2em" color="#A8762A">
          ⎙ Context files
        </Eyebrow>
        {docFiles.length > 0 ? (
          <span className="font-mono text-[10px] tracking-[0.08em] text-mute2 uppercase">
            {docFiles.length} {docFiles.length === 1 ? "file" : "files"}
          </span>
        ) : null}
      </div>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          void addFiles(e.dataTransfer.files);
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
            void addFiles(e.currentTarget.files);
            e.currentTarget.value = ""; // allow re-selecting the same file
          }}
        />
        <label
          htmlFor={inputId}
          className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:underline"
        >
          Browse files
        </label>
      </div>

      {/* Bulk select/deselect per category — for many dropped files. */}
      {docFiles.length > 0 ? (
        <div className="mt-[12px] rounded-[4px] border border-cardbd bg-field px-[10px] py-[8px]">
          <Eyebrow tracking="0.14em" color="#A8762A">
            Select all
          </Eyebrow>
          <div className="mt-[6px] flex flex-col gap-[5px]">
            {DOC_USES.map(({ key, label, title }) => {
              const onCount = docFiles.filter((doc) => doc[key] ?? true).length;
              return (
                <div key={key} className="flex items-center justify-between gap-[8px]">
                  <span
                    title={title}
                    className="font-mono text-[10.5px] tracking-[0.06em] text-ink-soft uppercase"
                  >
                    {label}{" "}
                    <span className="text-mute2 normal-case">
                      ({onCount}/{docFiles.length})
                    </span>
                  </span>
                  <div className="flex gap-[6px]">
                    <button
                      type="button"
                      aria-label={`Select all for ${label}`}
                      onClick={() => setAllDocUse(key, true)}
                      className="cursor-pointer rounded-full border border-cardbd bg-transparent px-[9px] py-[2px] font-mono text-tag tracking-[0.08em] text-ink-soft uppercase hover:border-accent hover:bg-hover hover:text-ink"
                    >
                      All
                    </button>
                    <button
                      type="button"
                      aria-label={`Deselect all for ${label}`}
                      onClick={() => setAllDocUse(key, false)}
                      className="cursor-pointer rounded-full border border-cardbd bg-transparent px-[9px] py-[2px] font-mono text-tag tracking-[0.08em] text-mute uppercase hover:border-accent hover:bg-hover hover:text-ink"
                    >
                      None
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Showcased contexts — pick which feed Draft / RAG / KG. */}
      <div className="mt-[12px]">
        {docFiles.length > 0 ? (
          <ul className="flex flex-col gap-[8px]">
            {docFiles.map((doc) => (
              <li
                key={doc.name}
                className="rounded-[4px] border border-cardbd bg-field px-[10px] py-[8px]"
              >
                <div className="flex items-center justify-between gap-[8px]">
                  <span className="truncate font-mono text-[11px] text-ink-soft">
                    ⎙ {doc.name}
                  </span>
                  <button
                    type="button"
                    aria-label={`Remove ${doc.name}`}
                    onClick={() => removeFile(doc.name)}
                    className="flex-none cursor-pointer text-mute hover:text-accent"
                  >
                    ×
                  </button>
                </div>
                <div className="mt-[7px] flex flex-wrap gap-[6px]">
                  {DOC_USES.map(({ key, label, title }) => {
                    const on = doc[key] ?? true;
                    return (
                      <button
                        key={key}
                        type="button"
                        title={title}
                        aria-pressed={on}
                        aria-label={`${label} for ${doc.name}`}
                        onClick={() => toggleDocUse(doc.name, key)}
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
            ))}
          </ul>
        ) : (
          <p className="font-body text-[12.5px] text-mute">
            Dropped contexts appear here — choose which feed Mytheca&apos;s drafting,
            the retrieval corpus, and the knowledge graph.
          </p>
        )}
      </div>
      <p className="mt-[10px] font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase">
        Saved with this entry · embedded for retrieval
      </p>
    </aside>
  );
}
