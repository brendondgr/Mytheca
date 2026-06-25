// Pure helpers + the commit orchestration for the New Storyline page.
//
// The page state lives in `useStorylineCreator`; this module holds the framework-free
// pieces: the field model, validation, proposed-world → CRUD-payload mappers, triage
// merging, the context-budget input, and `commitWorld` (the ordered create sequence
// that persists an approved world). Keeping these out of the hook keeps both testable.

import * as api from "@/lib/api";
import type { ContextDocumentInput } from "@/lib/api";
import type {
  ContextDocument,
  DocCategory,
  ProposedCharacter,
  ProposedSetting,
  ProposedWorld,
  StatDefinition,
  Storyline,
} from "@/lib/types";
import type { ReadDoc } from "@/lib/readDocs";
import { DEFAULT_SEAL_COLOR, DEFAULT_SEAL_SYMBOL } from "@/lib/seals";

/** A dropped reference doc plus its triage classification (creator-only state). */
export interface CreatorDoc extends ReadDoc {
  category: DocCategory;
  /** True once Triage has classified it. */
  triaged: boolean;
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

/** A freshly-dropped doc: not yet triaged → "other", RAG on, Draft off. */
export function toCreatorDoc(doc: ReadDoc): CreatorDoc {
  return {
    ...doc,
    useDraft: doc.useDraft ?? false,
    useRag: doc.useRag ?? true,
    category: "other",
    triaged: false,
  };
}

/** Texts of the Draft-included docs (for the budget meter + grounding). */
export function draftDocTexts(docs: CreatorDoc[]): string[] {
  return docs.filter((d) => d.useDraft && d.text).map((d) => d.text);
}

/** Merge Triage results into the dropped docs by name. */
export function applyTriage(
  docs: CreatorDoc[],
  items: { name: string; category: DocCategory; includeDraft: boolean; includeRag: boolean }[],
): CreatorDoc[] {
  const byName = new Map(items.map((i) => [i.name, i]));
  return docs.map((d) => {
    const t = byName.get(d.name);
    if (!t) return d;
    return { ...d, category: t.category, useDraft: t.includeDraft, useRag: t.includeRag, triaged: true };
  });
}

// ---- proposed-world → CRUD payload mappers ---------------------------------

export function proposedStatToInput(s: StatDefinition): api.StatDefinitionInput {
  return {
    key: s.key,
    displayName: s.displayName,
    description: s.description,
    min: s.min,
    max: s.max,
    default: s.default,
    bands: s.bands,
    visibility: s.visibility,
    appliesTo: s.appliesTo,
  };
}

export function proposedToCharacterInput(c: ProposedCharacter): api.CharacterInput {
  return {
    name: c.name,
    role: c.role,
    color: c.color || "#8E2B1C",
    traits: c.traits,
    speech: c.speech,
    goal: c.goal,
    secret: c.secret,
    appearance: c.appearance,
    background: c.background,
    personality: c.personality,
  };
}

export function proposedToSettingInput(s: ProposedSetting): api.SettingInput {
  return {
    name: s.name,
    type: s.type,
    desc: s.desc,
    atmosphere: s.atmosphere,
    features: s.features,
    currentState: s.currentState,
  };
}

export function docToContextInput(d: CreatorDoc): ContextDocumentInput {
  return {
    name: d.name,
    content: d.text,
    category: d.category,
    includeDraft: Boolean(d.useDraft),
    includeRag: d.useRag ?? true,
    source: "upload",
  };
}

/** Proposed starting stats → a {key: value} map, restricted to defined stats. */
export function startingStatsMap(
  starting: { key: string; value: number }[],
  defined: StatDefinition[],
): Record<string, number> {
  const keys = new Set(defined.map((s) => s.key));
  const out: Record<string, number> = {};
  for (const s of starting) if (keys.has(s.key)) out[s.key] = s.value;
  return out;
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
  /** The proposed cast + settings to create (creation mode only). */
  proposed: ProposedWorld | null;
  /** The triaged corpus to persist. */
  docs: CreatorDoc[];
  /** Already-persisted docs (edit mode) — skipped so we don't duplicate them. */
  existingDocs?: ContextDocument[];
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

/**
 * Persist an approved world. Returns the storyline id. In edit mode it updates the
 * core + stats (+ appends any newly-dropped docs). In create mode it creates the
 * storyline, its stats, the proposed cast (+ starting stats) and settings, then the
 * triaged corpus — reporting progress per step. Image rendering is layered on later.
 */
export async function commitWorld(
  args: CommitArgs,
  onProgress?: (msg: string) => void,
): Promise<string> {
  const { editId, fields, stats, statsOriginal, proposed, docs } = args;

  if (editId) {
    onProgress?.("Saving changes…");
    await api.updateStoryline(editId, coreInput(fields, true));
    await persistStatsDiff(editId, stats, statsOriginal);
    const existing = new Set((args.existingDocs ?? []).map((d) => d.name));
    const fresh = docs.filter((d) => d.text && !existing.has(d.name));
    if (fresh.length) await api.bulkCreateContextDocuments(editId, fresh.map(docToContextInput));
    return editId;
  }

  onProgress?.("Creating the world…");
  const created = await api.createStoryline(coreInput(fields, false));
  const id = created.id;

  if (stats.length) {
    onProgress?.("Adding statistics…");
    await persistStatsDiff(id, stats, []);
  }

  for (const c of proposed?.characters ?? []) {
    onProgress?.(`Adding ${c.name || "a character"}…`);
    const ch = await api.createCharacter(id, proposedToCharacterInput(c));
    const values = startingStatsMap(c.startingStats, stats);
    if (Object.keys(values).length) await api.setCharacterStats(ch.id, values);
  }

  for (const s of proposed?.settings ?? []) {
    onProgress?.(`Adding ${s.name || "a setting"}…`);
    await api.createSetting(id, proposedToSettingInput(s));
  }

  const corpus = docs.filter((d) => d.text);
  if (corpus.length) {
    onProgress?.("Saving context files…");
    await api.bulkCreateContextDocuments(id, corpus.map(docToContextInput));
  }
  return id;
}
