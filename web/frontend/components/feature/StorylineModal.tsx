"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { cn } from "@/lib/cn";
import {
  DEFAULT_SEAL_COLOR,
  DEFAULT_SEAL_SYMBOL,
  SEAL_COLORS,
  SEAL_SYMBOLS,
} from "@/lib/seals";
import { readDocFiles, type DocUse } from "@/lib/readDocs";
import type { useLibraryState } from "@/features/library/useLibraryState";

const SEG = "font-mono text-[10.5px] tracking-[0.06em] px-[15px] py-[8px] cursor-pointer";

// Per-context usage toggles shown on each dropped reference file. Only "Draft"
// is wired today (it grounds Velora's drafting + World Primer generation); "RAG"
// and "KG" are forward-looking seams for the deferred retrieval / knowledge-graph
// systems — selected here but not yet persisted or sent anywhere.
const DOC_USES: { key: DocUse; label: string; title: string }[] = [
  { key: "useDraft", label: "Draft", title: "Ground Velora's drafting & World Primer" },
  { key: "useRag", label: "RAG", title: "Include in the retrieval corpus (coming soon)" },
  { key: "useKg", label: "KG", title: "Source for the knowledge graph (coming soon)" },
];

/**
 * Write-first storyline creation modal. The author writes the world here — a
 * title, genre, one-line tagline, and a multi-paragraph premise — before it's
 * persisted, with a generated agent-facing World Primer spanning the bottom.
 *
 * Layout (desktop, `lg+`): the **main** column holds the by-hand form (Title +
 * Genre on one row, Tagline, Premise), the agentic **Draft with Velora** seed,
 * and the full-width **World Primer** + actions; a **detached context-files
 * column** runs the full height down the right side, showcasing each dropped
 * `.txt`/`.md` file (read in-browser to ground a single generation — never
 * uploaded/persisted) with per-use toggles (Draft / RAG / KG). On mobile a
 * By-hand / Agentically toggle swaps the form for the draft + context panels.
 */
export function StorylineModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  const m = lib.modal;
  if (!m || m.type !== "storyline") return null;
  const d = lib.draft;
  const agentic = m.mode === "agentic";
  const isEdit = m.editId != null;
  const seal = d.symbol || DEFAULT_SEAL_SYMBOL;
  const sealColor = d.symbolColor || DEFAULT_SEAL_COLOR;
  // Agentic authoring: a seed drafts the metadata; seed-or-premise feeds the primer.
  const seedText = (d._prompt ?? "").trim();
  const premiseText = (d.premise ?? "").trim();
  const canDraft = Boolean(seedText);
  const canGeneratePrimer = Boolean(seedText || premiseText);
  const docFiles = d._docFiles ?? [];

  // Read dropped/selected reference files into memory and merge them by name.
  // They ground a single generation only — never uploaded or persisted (no RAG).
  // New files default to all three uses ON; re-dropping keeps the prior choice.
  async function addFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const read = await readDocFiles(Array.from(files));
    if (read.length === 0) return;
    const byName = new Map((d._docFiles ?? []).map((doc) => [doc.name, doc]));
    for (const doc of read) {
      const prev = byName.get(doc.name);
      byName.set(doc.name, {
        ...doc,
        useDraft: prev?.useDraft ?? true,
        useRag: prev?.useRag ?? true,
        useKg: prev?.useKg ?? true,
      });
    }
    lib.setDraft("_docFiles", Array.from(byName.values()));
  }
  function removeFile(name: string) {
    lib.setDraft(
      "_docFiles",
      (d._docFiles ?? []).filter((doc) => doc.name !== name),
    );
  }
  function toggleDocUse(name: string, key: DocUse) {
    lib.setDraft(
      "_docFiles",
      (d._docFiles ?? []).map((doc) =>
        doc.name === name ? { ...doc, [key]: !(doc[key] ?? true) } : doc,
      ),
    );
  }
  // Bulk select/deselect every context for one category at once — essential when
  // hundreds of files are dropped in.
  function setAllDocUse(key: DocUse, value: boolean) {
    lib.setDraft(
      "_docFiles",
      (d._docFiles ?? []).map((doc) => ({ ...doc, [key]: value })),
    );
  }

  return (
    <Modal
      open
      onClose={lib.closeModal}
      labelledBy="storyline-modal-title"
      className="sm:w-[560px] md:w-[860px] lg:w-[1120px]"
      externalClose
    >
      {/* Root: main column + detached full-height context column (lg). */}
      <div className="lg:flex lg:items-stretch">
        {/* ── Main column ─────────────────────────────────────────────── */}
        <div className="min-w-0 p-[22px_26px_24px] lg:flex-1">
          {/* Header — title left; seal picker right-justified (preview left of
              the symbol/color grids). The × close hovers outside the panel. */}
          <div className="relative">
            <div className="flex flex-wrap items-end justify-between gap-x-[24px] gap-y-[14px]">
              <div className="min-w-0">
                <Eyebrow size={8.5} tracking="0.2em" color="#A8762A">
                  {isEdit ? "Edit Storyline" : "New Storyline"}
                </Eyebrow>
                <div
                  id="storyline-modal-title"
                  className="mt-1 font-display text-[22px] font-bold text-ink"
                >
                  {isEdit ? "Edit this World" : "Forge a New World"}
                </div>
              </div>

              {/* Seal — preview to the left of the symbol + color grids. */}
              <div className="flex items-center gap-[12px]">
                <div
                  aria-hidden
                  className="flex h-[44px] w-[44px] flex-none items-center justify-center rounded-[4px] border border-cardbd bg-field text-[23px] leading-none"
                  style={{ color: sealColor }}
                >
                  {seal}
                </div>
                <div className="flex flex-col gap-[8px]">
                  <div
                    role="group"
                    aria-label="Seal symbol"
                    className="flex max-w-[280px] flex-wrap gap-[6px]"
                  >
                    {SEAL_SYMBOLS.map((sym) => (
                      <button
                        key={sym}
                        type="button"
                        aria-label={`Symbol ${sym}`}
                        aria-pressed={seal === sym}
                        onClick={() => lib.setDraft("symbol", sym)}
                        className={cn(
                          "flex h-[26px] w-[26px] items-center justify-center rounded-[4px] border text-[14px] leading-none focus-visible:border-accent",
                          seal === sym
                            ? "border-accent bg-card2 text-ink"
                            : "border-cardbd bg-field text-ink-soft hover:border-accent",
                        )}
                      >
                        {sym}
                      </button>
                    ))}
                  </div>
                  <div
                    role="group"
                    aria-label="Seal color"
                    className="flex max-w-[280px] flex-wrap gap-[7px]"
                  >
                    {SEAL_COLORS.map((col) => (
                      <button
                        key={col}
                        type="button"
                        aria-label={`Color ${col}`}
                        aria-pressed={sealColor === col}
                        onClick={() => lib.setDraft("symbolColor", col)}
                        className="h-[20px] w-[20px] rounded-full focus-visible:outline-none"
                        style={{
                          background: col,
                          boxShadow:
                            sealColor === col
                              ? `0 0 0 2px var(--modal-bg), 0 0 0 4px ${col}`
                              : "0 0 0 1px rgba(0,0,0,.15)",
                        }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Mode toggle — mobile/tablet only. On md+ every panel shows at once. */}
          <div className="mt-[14px] inline-flex overflow-hidden rounded-full border border-field-bd bg-card md:hidden">
            <button
              type="button"
              onClick={() => lib.setMode("manual")}
              className={cn(SEG, agentic ? "bg-transparent text-mute" : "bg-accent text-[#F6ECDA]")}
            >
              ✎ By hand
            </button>
            <button
              type="button"
              onClick={() => lib.setMode("agentic")}
              className={cn(SEG, agentic ? "bg-accent text-[#F6ECDA]" : "bg-transparent text-mute")}
            >
              ❖ Agentically
            </button>
          </div>
          <div className="my-[16px] h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

          {/* Authoring form (left) + agentic Draft with Velora (right). */}
          <div className="md:flex md:items-stretch">
            <div className={cn("md:min-w-0 md:flex-1 md:pr-[26px]", agentic && "hidden md:block")}>
              {/* Title + Genre share a row; Tagline then Premise span full width. */}
              <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2">
                <TextField
                  label="Title"
                  placeholder="e.g. Embergate"
                  value={d.title || ""}
                  onChange={(e) => lib.setDraft("title", e.target.value)}
                />
                <TextField
                  label="Genre"
                  placeholder="e.g. Maritime Intrigue"
                  value={d.genre || ""}
                  onChange={(e) => lib.setDraft("genre", e.target.value)}
                />
              </div>
              <TextField
                label="Tagline"
                placeholder="One line for the switcher — what the world is, in a breath."
                value={d.tagline || ""}
                onChange={(e) => lib.setDraft("tagline", e.target.value)}
                className="mt-[14px]"
              />
              <TextArea
                label="Premise"
                placeholder="Write the world in full — its setting, mood, the powers in play, what it's about. Multiple paragraphs welcome."
                rows={7}
                value={d.premise || ""}
                onChange={(e) => lib.setDraft("premise", e.target.value)}
                className="mt-[14px]"
              />
            </div>

            {/* Agentic draft panel — describe the world; Velora drafts the fields. */}
            <aside
              className={cn(
                "mt-[18px] md:mt-0 md:w-[300px] md:shrink-0 md:border-l md:border-hair-strong md:pl-[26px]",
                !agentic && "hidden md:block",
              )}
            >
              <Eyebrow size={8.5} tracking="0.2em" color="#A8762A" className="mb-[10px] block">
                ❖ Draft with Velora
              </Eyebrow>
              <p className="mb-[10px] font-body text-[14px] text-ink">
                Describe the world in a sentence —{" "}
                <span className="text-ink-soft italic">Velora drafts the rest.</span>
              </p>
              <TextArea
                aria-label="Describe the world to draft"
                rows={4}
                placeholder="e.g. A rotting harbor town where every secret has a price…"
                value={d._prompt || ""}
                onChange={(e) => lib.setDraft("_prompt", e.target.value)}
              />
              {/* The action spans the full width of the seed box above it. */}
              <Button
                onClick={lib.draftStoryline}
                disabled={!canDraft || lib.generating}
                className="mt-[12px] w-full"
              >
                {lib.generating ? "Drafting…" : "❖ Draft with Velora"}
              </Button>
              <Button
                variant="ghost"
                onClick={lib.closeModal}
                className="mt-[10px] w-full md:hidden"
              >
                Cancel
              </Button>

              {/* Mobile-only error echo: the main footer (with the alert) is hidden
                  while the agentic tab is open on small screens. */}
              {lib.error ? (
                <p role="alert" className="mt-4 font-body text-[13px] text-accent md:hidden">
                  {lib.error}
                </p>
              ) : null}
            </aside>
          </div>

          {/* World Primer — full-width row beneath the form + draft columns. */}
          <div
            className={cn(
              "mt-[20px] border-t border-hair-strong pt-[18px]",
              agentic && "hidden md:block",
            )}
          >
            <div className="flex items-end justify-between gap-[10px]">
              <FieldLabel>World Primer</FieldLabel>
              <button
                type="button"
                onClick={lib.generatePrimer}
                disabled={!canGeneratePrimer || lib.generatingPrimer}
                className="mb-[6px] cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase enabled:hover:underline disabled:opacity-40"
              >
                {lib.generatingPrimer ? "Generating…" : "❖ Generate primer"}
              </button>
            </div>
            <p className="mb-[8px] font-body text-[12.5px] text-ink-soft">
              Agent-facing context injected into every scene — what the model needs
              to play this world without looking things up.
            </p>
            <TextArea
              aria-label="World Primer"
              rows={6}
              placeholder="Generate from the seed and premise — or write it yourself. Front-load the always-true facts: tone, the constant proper nouns, the load-bearing rules."
              value={d.worldPrimer || ""}
              onChange={(e) => lib.setDraft("worldPrimer", e.target.value)}
            />
          </div>

          {/* Footer — main error + actions (full width, right-justified). */}
          <div className={cn(agentic && "hidden md:block")}>
            {lib.error ? (
              <p role="alert" className="mt-4 font-body text-[13px] text-accent">
                {lib.error}
              </p>
            ) : null}
            <div className="mt-[20px] flex items-center justify-end gap-[10px]">
              <Button variant="ghost" onClick={lib.closeModal}>
                Cancel
              </Button>
              <Button
                onClick={lib.submitStoryline}
                disabled={!lib.isStorylineValid || lib.pending}
              >
                {lib.pending
                  ? isEdit
                    ? "Saving…"
                    : "Creating…"
                  : isEdit
                    ? "Save Changes"
                    : "Create World"}
              </Button>
            </div>
          </div>
        </div>

        {/* ── Detached context-files column — full height, right side ──── */}
        <aside
          className={cn(
            "flex-col bg-card p-[20px_22px_22px] lg:w-[330px] lg:shrink-0",
            "border-t border-hair-strong lg:border-t-0 lg:border-l",
            agentic ? "flex md:flex" : "hidden md:flex",
          )}
        >
          <div className="mb-[10px] flex items-center justify-between gap-[8px]">
            <Eyebrow size={8.5} tracking="0.2em" color="#A8762A">
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
              id="storyline-docs-input"
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
              htmlFor="storyline-docs-input"
              className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:underline"
            >
              Browse files
            </label>
          </div>

          {/* Bulk select/deselect per category — for hundreds of dropped files. */}
          {docFiles.length > 0 ? (
            <div className="mt-[12px] rounded-[4px] border border-cardbd bg-field px-[10px] py-[8px]">
              <Eyebrow size={8.5} tracking="0.14em" color="#A8762A">
                Select all
              </Eyebrow>
              <div className="mt-[6px] flex flex-col gap-[5px]">
                {DOC_USES.map(({ key, label, title }) => {
                  const onCount = docFiles.filter((doc) => doc[key] ?? true).length;
                  return (
                    <div
                      key={key}
                      className="flex items-center justify-between gap-[8px]"
                    >
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
                          className="cursor-pointer rounded-full border border-cardbd bg-transparent px-[9px] py-[2px] font-mono text-[9.5px] tracking-[0.08em] text-ink-soft uppercase hover:border-accent"
                        >
                          All
                        </button>
                        <button
                          type="button"
                          aria-label={`Deselect all for ${label}`}
                          onClick={() => setAllDocUse(key, false)}
                          className="cursor-pointer rounded-full border border-cardbd bg-transparent px-[9px] py-[2px] font-mono text-[9.5px] tracking-[0.08em] text-mute uppercase hover:border-accent"
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

          {/* Showcased contexts — pick which feed Draft / RAG / KG. The whole
              modal scrolls (no nested scroll) so long lists stay usable. */}
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
                ))}
              </ul>
            ) : (
              <p className="font-body text-[12.5px] text-mute">
                Dropped contexts appear here — choose which feed Velora&apos;s
                drafting, the retrieval corpus, and the knowledge graph.
              </p>
            )}
          </div>
          <p className="mt-[10px] font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase">
            Grounds this generation only — not stored yet
          </p>
        </aside>
      </div>
    </Modal>
  );
}
