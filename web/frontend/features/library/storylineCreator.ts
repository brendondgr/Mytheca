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
import {
  type BuildState,
  emptyBuild,
  finishBuild,
  foldPopulateFrame,
} from "@/features/library/worldBuild";

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
  /**
   * The world's narrative style guide ({block id → text}) — how this story is written,
   * where `worldPrimer` is what is true in it. A map rather than a string because it is
   * six independently-clearable blocks, edited in a modal rather than a form field.
   */
  styleBlocks: Record<string, string>;
}

export const BLANK_FIELDS: CreatorFields = {
  title: "",
  genre: "",
  tagline: "",
  premise: "",
  worldPrimer: "",
  symbol: DEFAULT_SEAL_SYMBOL,
  symbolColor: DEFAULT_SEAL_COLOR,
  styleBlocks: {},
};

type StorylineLike = Pick<
  Storyline,
  | "title"
  | "genre"
  | "tagline"
  | "premise"
  | "worldPrimer"
  | "symbol"
  | "symbolColor"
  | "styleBlocks"
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
    styleBlocks: sl.styleBlocks ?? {},
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
}

/**
 * Fill the just-created world with a generated cast + settings, folding every frame
 * into build state the dialog renders live.
 *
 * Runs against the *persisted* world: the roster is grounded in the saved storyline
 * and corpus, and each entity is written straight to it. Nothing is thrown — the world
 * already exists, so a failed build is reported as a `failed` state rather than losing
 * the author's work. `finishBuild` is what makes a truncated stream a failure instead
 * of a silent success.
 */
/** How many times a dropped stream is silently re-attached before giving up. */
export const RECONNECT_ATTEMPTS = 4;
const RECONNECT_DELAY_MS = 1500;

const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function runPopulate(
  storylineId: string,
  opts: PopulateOptions,
  docsOverview: string | undefined,
  onState: (state: BuildState) => void,
  signal?: AbortSignal,
  /** Pause between re-attach attempts (0 in tests). */
  retryDelayMs: number = RECONNECT_DELAY_MS,
): Promise<BuildState> {
  let state: BuildState = { ...emptyBuild(), phase: "building", step: "Planning the world…" };
  onState(state);

  // The build runs server-side, so a dropped socket is only a lost *view* of it: we
  // re-attach from the last frame we saw and carry on. Without this the author lost a
  // ten-minute build to a blip and was told "Lost the connection while the server was
  // still working." — which was true, and useless.
  for (let attempt = 0; ; attempt++) {
    try {
      for await (const frame of api.populateWorldStream(
        storylineId,
        {
          docsOverview,
          source: opts.source,
          withArtwork: opts.withArtwork,
          ...(opts.artStyle ? { artStyle: opts.artStyle } : {}),
          fromSeq: state.lastSeq + 1,
        },
        signal,
      )) {
        state = foldPopulateFrame(state, frame);
        onState(state);
      }
      state = finishBuild(state);
      break;
    } catch (e) {
      if (signal?.aborted || attempt >= RECONNECT_ATTEMPTS) {
        state = finishBuild(state, e);
        break;
      }
      state = { ...state, step: "Lost the connection — picking the build back up…" };
      onState(state);
      await wait(retryDelayMs);
    }
  }

  onState(state);
  return state;
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
    // Always sent, on create as well as edit: an empty guide is a real, saveable state
    // (a world opting out), and `opt()`'s create-mode "omit if blank" would make clearing
    // every block indistinguishable from never having set one.
    styleBlocks: f.styleBlocks,
  };
}

/**
 * Persist an approved world and return its id. In edit mode it updates the core +
 * stats (+ reconciles the storyline-level corpus). In create mode it creates the
 * storyline, its stats, then the triaged corpus, reporting progress per step.
 *
 * Population is deliberately NOT part of this: it is a long, watchable run that the
 * Build-world dialog drives through `runPopulate` once the world exists.
 */
export async function commitWorld(
  args: CommitArgs,
  onProgress?: (msg: string) => void,
): Promise<string> {
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
    return editId;
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

  return id;
}
