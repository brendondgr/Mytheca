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

/**
 * The blueprint concepts (one vivid sentence each) the build emits before drafting
 * the full entities — they drive the "drafting…" skeleton cards in the right column
 * until each `character`/`setting` event fills its slot.
 */
export interface PlanConcepts {
  characters: string[];
  settings: string[];
}

/** The document currently being classified during a live (per-file) triage. */
export interface TriageActive {
  name: string;
  index: number;
  total: number;
}

/**
 * Set `arr[index] = value` immutably. The build streams characters/settings in
 * order (index === current length), so this is effectively an append; written
 * generically so an out-of-order event still lands in the right slot.
 */
export function upsertAt<T>(arr: T[], index: number, value: T): T[] {
  const out = arr.slice();
  out[index] = value;
  return out;
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
}

/**
 * A freshly-dropped doc. By default it is Uncategorized ("select"), RAG on, Draft off.
 * When the author picked an upload target (category / Draft / RAG), those are applied
 * so a whole batch lands pre-categorized — no Triage needed for it. A doc dropped into
 * a real category counts as already triaged (Triage then only sweeps the leftovers).
 */
export function toCreatorDoc(doc: ReadDoc, opts: UploadDefaults = {}): CreatorDoc {
  const category = opts.category ?? "select";
  return {
    ...doc,
    useDraft: opts.useDraft ?? doc.useDraft ?? false,
    useRag: opts.useRag ?? doc.useRag ?? true,
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
    category: doc.category,
    triaged: true,
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
    // "select" is a UI-only placeholder; fall back to "other" at the API boundary.
    category: d.category === "select" ? "other" : d.category,
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
  /** Opt-in: render portraits / scene-art via ComfyUI (best-effort per entity). */
  generateImages?: boolean;
}

/**
 * A live entity update emitted during the commit — lets the page patch the
 * displayed cast/settings as each portrait / scene-art finishes rendering, so the
 * previews pop into the right column in front of the author.
 */
export type CommitEntityPatch =
  | { type: "character"; index: number; patch: Partial<ProposedCharacter> }
  | { type: "setting"; index: number; patch: Partial<ProposedSetting> };

/** Generate a portrait image URL for a (possibly unsaved) character — no persist. */
async function proposePortraitUrl(
  c: ProposedCharacter,
  onProgress?: (msg: string) => void,
): Promise<string | null> {
  onProgress?.(`Rendering portrait for ${c.name || "a character"}…`);
  const prompts = await api.generatePortraitPrompts({
    name: c.name,
    role: c.role,
    appearance: c.appearance,
    traits: c.traits,
    personality: c.personality,
  });
  const { portrait } = await api.generatePortrait({
    positive: prompts.positive,
    negative: prompts.negative,
  });
  return portrait || null;
}

/** Generate a scene-art image URL for a (possibly unsaved) setting — no persist. */
async function proposeSceneArtUrl(
  s: ProposedSetting,
  onProgress?: (msg: string) => void,
): Promise<string | null> {
  onProgress?.(`Rendering scene art for ${s.name || "a setting"}…`);
  const prompts = await api.generateSceneArtPrompts({
    name: s.name,
    type: s.type,
    desc: s.desc,
    atmosphere: s.atmosphere,
    features: s.features,
    currentState: s.currentState,
  });
  const { image } = await api.generateSceneArt({
    positive: prompts.positive,
    negative: prompts.negative,
  });
  return image || null;
}

/**
 * Render portraits + scene art for a proposed (un-persisted) world, patching each
 * into the proposal as it lands — so **Build the whole world** shows images appear
 * live whenever ComfyUI is available. Best-effort per entity (a failed render is
 * skipped, never thrown), skips entities that already have an image, and bails
 * promptly when `signal` aborts (e.g. the author hits Create World, or navigates).
 */
export async function renderProposalImages(
  proposed: ProposedWorld,
  onEntity: (e: CommitEntityPatch) => void,
  onProgress?: (msg: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  // Circuit breaker: if a render call fails (e.g. ComfyUI stopped mid-build), bail
  // immediately rather than hammering a down server with one 502 per entity.
  for (let i = 0; i < proposed.characters.length; i++) {
    if (signal?.aborted) return;
    const c = proposed.characters[i];
    if (c.portrait) continue;
    try {
      const portrait = await proposePortraitUrl(c, onProgress);
      if (signal?.aborted) return;
      if (portrait) onEntity({ type: "character", index: i, patch: { portrait } });
    } catch {
      onProgress?.("Image generation stopped — is ComfyUI running? (check Options).");
      return;
    }
  }
  for (let i = 0; i < proposed.settings.length; i++) {
    if (signal?.aborted) return;
    const s = proposed.settings[i];
    if (s.image) continue;
    try {
      const image = await proposeSceneArtUrl(s, onProgress);
      if (signal?.aborted) return;
      if (image) onEntity({ type: "setting", index: i, patch: { image } });
    } catch {
      onProgress?.("Image generation stopped — is ComfyUI running? (check Options).");
      return;
    }
  }
}

/** Render + persist a portrait (never throws). Returns false if the render failed
 *  (the caller stops rendering further images — likely ComfyUI is down). */
async function renderPortrait(
  characterId: string,
  c: ProposedCharacter,
  index: number,
  onProgress?: (msg: string) => void,
  onEntity?: (e: CommitEntityPatch) => void,
): Promise<boolean> {
  try {
    const portrait = await proposePortraitUrl(c, onProgress);
    if (!portrait) return true;
    await api.updateCharacter(characterId, { portrait });
    onEntity?.({ type: "character", index, patch: { portrait } });
    return true;
  } catch {
    onProgress?.("Image generation stopped — is ComfyUI running? (check Options).");
    return false;
  }
}

/** Render + persist scene art (never throws). Returns false on a failed render. */
async function renderSceneArt(
  settingId: string,
  s: ProposedSetting,
  index: number,
  onProgress?: (msg: string) => void,
  onEntity?: (e: CommitEntityPatch) => void,
): Promise<boolean> {
  try {
    const image = await proposeSceneArtUrl(s, onProgress);
    if (!image) return true;
    await api.updateSetting(settingId, { image });
    onEntity?.({ type: "setting", index, patch: { image } });
    return true;
  } catch {
    onProgress?.("Image generation stopped — is ComfyUI running? (check Options).");
    return false;
  }
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
  onEntity?: (e: CommitEntityPatch) => void,
): Promise<string> {
  const { editId, fields, stats, statsOriginal, proposed, docs } = args;

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

  // Once a fresh render fails we stop attempting more (ComfyUI is likely down) —
  // entities are still created, just without an image.
  let imagesOk = true;

  const characters = proposed?.characters ?? [];
  for (let i = 0; i < characters.length; i++) {
    const c = characters[i];
    onProgress?.(`Adding ${c.name || "a character"}…`);
    const ch = await api.createCharacter(id, proposedToCharacterInput(c));
    const values = startingStatsMap(c.startingStats, stats);
    if (Object.keys(values).length) await api.setCharacterStats(ch.id, values);
    // Images are rendered during the build; persist what's there, and render fresh
    // only if one is still missing (and the author left image generation on).
    if (c.portrait) await api.updateCharacter(ch.id, { portrait: c.portrait });
    else if (args.generateImages && imagesOk) {
      imagesOk = await renderPortrait(ch.id, c, i, onProgress, onEntity);
    }
  }

  const settings = proposed?.settings ?? [];
  for (let i = 0; i < settings.length; i++) {
    const s = settings[i];
    onProgress?.(`Adding ${s.name || "a setting"}…`);
    const st = await api.createSetting(id, proposedToSettingInput(s));
    if (s.image) await api.updateSetting(st.id, { image: s.image });
    else if (args.generateImages && imagesOk) {
      imagesOk = await renderSceneArt(st.id, s, i, onProgress, onEntity);
    }
  }

  const corpus = docs.filter((d) => d.text);
  if (corpus.length) {
    onProgress?.("Saving context files…");
    await api.bulkCreateContextDocuments(id, corpus.map(docToContextInput));
  }
  return id;
}
