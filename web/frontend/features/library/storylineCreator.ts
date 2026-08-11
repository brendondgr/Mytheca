// Pure helpers + the commit orchestration for the New Storyline page.
//
// The page state lives in `useStorylineCreator`; this module holds the framework-free
// pieces: the field model, validation, triage merging, the context-budget input, and
// `commitWorld` (the ordered create sequence that persists an approved world). Keeping
// these out of the hook keeps both testable.

import * as api from "@/lib/api";
import type { ContextDocumentInput } from "@/lib/api";
import type {
  ContextDocument,
  DocCategory,
  PopulateOptions,
  StatDefinition,
  Storyline,
} from "@/lib/types";
import { concatDocs, type ReadDoc } from "@/lib/readDocs";
import { DEFAULT_SEAL_COLOR, DEFAULT_SEAL_SYMBOL } from "@/lib/seals";

/** A dropped reference doc plus its triage classification (creator-only state). */
export interface CreatorDoc extends ReadDoc {
  category: DocCategory;
  /** True once Triage has classified it. */
  triaged: boolean;
}

/** The document currently being classified during a live (per-file) triage. */
export interface TriageActive {
  name: string;
  index: number;
  total: number;
}

/** The creator's by-hand fields (mirror the storyline wire shape). */
export interface CreatorFields {
  title: string;
  genre: string;
  tagline: string;
  premise: string;
  worldPrimer: string;
  symbol: string;
  symbolColor: string;
}

export const BLANK_FIELDS: CreatorFields = {
  title: "",
  genre: "",
  tagline: "",
  premise: "",
  worldPrimer: "",
  symbol: DEFAULT_SEAL_SYMBOL,
  symbolColor: DEFAULT_SEAL_COLOR,
};

type StorylineLike = Pick<
  Storyline,
  "title" | "genre" | "tagline" | "premise" | "worldPrimer" | "symbol" | "symbolColor"
>;

export function fieldsFromStoryline(sl: StorylineLike): CreatorFields {
  return {
    title: sl.title ?? "",
    genre: sl.genre ?? "",
    tagline: sl.tagline ?? "",
    premise: sl.premise ?? "",
    worldPrimer: sl.worldPrimer ?? "",
    symbol: sl.symbol || DEFAULT_SEAL_SYMBOL,
    symbolColor: sl.symbolColor || DEFAULT_SEAL_COLOR,
  };
}

/** A storyline is creatable/savable once it has a title. */
export function isCreatorValid(f: CreatorFields): boolean {
  return Boolean(f.title.trim());
}

/** Defaults the author can pre-apply to a batch of uploads. */
export interface UploadDefaults {
  category?: DocCategory;
  useDraft?: boolean;
  useRag?: boolean;
  useExtract?: boolean;
}

/**
 * A freshly-dropped doc. By default it is Uncategorized ("select"), **Draft on**, RAG
 * on, Extract off (extraction is opt-in — a new storyline never auto-mines docs for
 * cast/settings). Draft-on is the default because an uploaded file that the assistant
 * cannot see is the surprising case: the author dropped it in to be used. The volume is
 * bounded by `DOCS_CHAR_CAP`, shown live by the context-budget meter, and reversible in
 * one click via the panel's De-select All. When the author picked an upload target
 * (category / Draft / RAG / Extract), those are applied so a whole batch lands
 * pre-categorized — no Triage needed for it. A doc dropped into a real category counts
 * as already triaged (Triage sweeps the rest).
 */
export function toCreatorDoc(doc: ReadDoc, opts: UploadDefaults = {}): CreatorDoc {
  const category = opts.category ?? "select";
  return {
    ...doc,
    useDraft: opts.useDraft ?? doc.useDraft ?? true,
    useRag: opts.useRag ?? doc.useRag ?? true,
    useExtract: opts.useExtract ?? doc.useExtract ?? false,
    category,
    triaged: category !== "select",
  };
}

/**
 * A persisted `ContextDocument` → the creator's `CreatorDoc` shape, so previously
 * saved files reappear in the panel on edit (already triaged/classified). This is
 * the fix for files getting "lost" when re-opening a saved storyline.
 */
export function fromContextDocument(doc: ContextDocument): CreatorDoc {
  return {
    name: doc.name,
    text: doc.content,
    useDraft: doc.includeDraft,
    useRag: doc.includeRag,
    useExtract: doc.includeExtract,
    category: doc.category,
    triaged: true,
  };
}

/** Texts of the Draft-included docs (for the budget meter + grounding). */
export function draftDocTexts(docs: CreatorDoc[]): string[] {
  return docs.filter((d) => d.useDraft && d.text).map((d) => d.text);
}

/** The Draft-included docs as one bounded grounding string (or undefined). */
export function draftGrounding(docs: CreatorDoc[]): string | undefined {
  return concatDocs(docs.filter((d) => d.useDraft));
}

/** Merge Triage results into the dropped docs by name. */
export function applyTriage(
  docs: CreatorDoc[],
  items: {
    name: string;
    category: DocCategory;
    includeDraft: boolean;
    includeRag: boolean;
    includeExtract?: boolean;
  }[],
): CreatorDoc[] {
  const byName = new Map(items.map((i) => [i.name, i]));
  return docs.map((d) => {
    const t = byName.get(d.name);
    if (!t) return d;
    return {
      ...d,
      category: t.category,
      useDraft: t.includeDraft,
      useRag: t.includeRag,
      useExtract: t.includeExtract ?? false,
      triaged: true,
    };
  });
}

export function docToContextInput(d: CreatorDoc): ContextDocumentInput {
  return {
    name: d.name,
    content: d.text,
    // "select" is a UI-only placeholder; fall back to "other" at the API boundary.
    category: d.category === "select" ? "other" : d.category,
    includeDraft: Boolean(d.useDraft),
    includeRag: d.useRag ?? true,
    includeExtract: Boolean(d.useExtract),
    source: "upload",
  };
}

// ---- persistence -----------------------------------------------------------

/** Diff `current` stats vs `original` into create/update/delete calls. */
export async function persistStatsDiff(
  storylineId: string,
  current: StatDefinition[],
  original: StatDefinition[],
): Promise<void> {
  const valid = current.filter((s) => s.key.trim() && s.displayName.trim());
  const currentKeys = new Set(valid.map((s) => s.key));
  const originalByKey = new Map(original.map((s) => [s.key, s]));
  for (const o of original) {
    if (!currentKeys.has(o.key)) await api.deleteStatDefinition(storylineId, o.key);
  }
  for (const s of valid) {
    const prev = originalByKey.get(s.key);
    const fields = {
      displayName: s.displayName,
      description: s.description,
      min: s.min,
      max: s.max,
      default: s.default,
      bands: s.bands,
      visibility: s.visibility,
      appliesTo: s.appliesTo,
      guidance: s.guidance,
    };
    if (!prev) await api.createStatDefinition(storylineId, { key: s.key, ...fields });
    else if (JSON.stringify(prev) !== JSON.stringify(s))
      await api.updateStatDefinition(storylineId, s.key, fields);
  }
}

export interface CommitArgs {
  editId?: string;
  fields: CreatorFields;
  stats: StatDefinition[];
  statsOriginal: StatDefinition[];
  /** The triaged corpus to persist. */
  docs: CreatorDoc[];
  /** Already-persisted docs (edit mode) — skipped so we don't duplicate them. */
  existingDocs?: ContextDocument[];
  /** Create mode: what the author chose in the Build-world dialog. */
  populate?: PopulateOptions;
}

/**
 * Fill the just-created world with a generated cast + settings, reporting progress.
 *
 * Runs last in the create sequence, against the *persisted* world: the roster is
 * grounded in the saved storyline and corpus, and each entity is written straight to
 * it. Failures are reported and swallowed — the world already exists, so a failed
 * population must never strand the author on the create page or lose their work.
 * Returns the non-fatal message to surface, or `null` when everything landed.
 */
export async function populateWorld(
  storylineId: string,
  opts: PopulateOptions,
  docsOverview?: string,
  onProgress?: (msg: string) => void,
): Promise<string | null> {
  let problem: string | null = null;
  try {
    for await (const ev of api.populateWorldStream(storylineId, {
      docsOverview,
      withArtwork: opts.withArtwork,
    })) {
      if (ev.type === "status") {
        onProgress?.(
          ev.total > 1 ? `${ev.message} (${ev.index} / ${ev.total})` : ev.message,
        );
      } else if (ev.type === "entity") {
        onProgress?.(`Added ${ev.name}.`);
      } else if (ev.type === "error") {
        // Non-fatal frames report one item; a fatal one ends the run. Either way the
        // world stands, so the last message is what the author sees.
        problem = ev.message;
      }
    }
  } catch (e) {
    problem = e instanceof Error ? e.message : "Could not build the cast and settings.";
  }
  return problem;
}

function coreInput(f: CreatorFields, clearable: boolean): api.StorylineInput {
  // Create omits empty optionals; edit sends "" so a field can be cleared.
  const opt = (v: string) => (clearable ? v.trim() : v.trim() || undefined);
  return {
    title: f.title.trim(),
    genre: f.genre.trim() || "Uncharted",
    tagline: opt(f.tagline),
    premise: opt(f.premise),
    worldPrimer: opt(f.worldPrimer),
    symbol: f.symbol || DEFAULT_SEAL_SYMBOL,
    symbolColor: f.symbolColor || DEFAULT_SEAL_COLOR,
  };
}

/** The outcome of a commit: the world's id, plus anything worth telling the author. */
export interface CommitResult {
  id: string;
  /** A non-fatal problem (population failed / partly failed); the world still exists. */
  warning: string | null;
}

/**
 * Persist an approved world. In edit mode it updates the core + stats (+ reconciles
 * the storyline-level corpus). In create mode it creates the storyline, its stats,
 * the triaged corpus, and — when the author asked for it in the Build-world dialog —
 * generates and persists the cast + settings, reporting progress per step.
 */
export async function commitWorld(
  args: CommitArgs,
  onProgress?: (msg: string) => void,
): Promise<CommitResult> {
  const { editId, fields, stats, statsOriginal, docs } = args;

  if (editId) {
    onProgress?.("Saving changes…");
    await api.updateStoryline(editId, coreInput(fields, true));
    await persistStatsDiff(editId, stats, statsOriginal);
    // Reconcile the storyline-LEVEL corpus only (entity-scoped docs belong to their
    // own editors): create newly-dropped files, and delete ones the author removed —
    // which prunes their embeddings from the vector store.
    const slExisting = (args.existingDocs ?? []).filter((d) => !d.entityType);
    const existingNames = new Set(slExisting.map((d) => d.name));
    const keepNames = new Set(docs.map((d) => d.name));
    const fresh = docs.filter((d) => d.text && !existingNames.has(d.name));
    if (fresh.length) await api.bulkCreateContextDocuments(editId, fresh.map(docToContextInput));
    await Promise.all(
      slExisting.filter((d) => !keepNames.has(d.name)).map((d) => api.deleteContextDocument(d.id)),
    );
    return { id: editId, warning: null };
  }

  onProgress?.("Creating the world…");
  const created = await api.createStoryline(coreInput(fields, false));
  const id = created.id;

  if (stats.length) {
    onProgress?.("Adding statistics…");
    await persistStatsDiff(id, stats, []);
  }

  const corpus = docs.filter((d) => d.text);
  if (corpus.length) {
    onProgress?.("Saving context files…");
    await api.bulkCreateContextDocuments(id, corpus.map(docToContextInput));
  }

  // Population runs last, against the persisted world: the roster is grounded in the
  // saved storyline + corpus, and the cast/settings are written straight into it.
  let warning: string | null = null;
  if (args.populate?.enabled) {
    warning = await populateWorld(id, args.populate, draftGrounding(docs), onProgress);
  }

  return { id, warning };
}
