// Read dropped reference files into a single grounding string for the storyline
// authoring agent. The text grounds ONE generation call only — files are never
// uploaded, persisted, or indexed here (the corpus / RAG layer is a later plan).

export const ACCEPTED_DOC_EXTENSIONS = [".txt", ".md", ".markdown"] as const;

/** Upper bound on the grounding text sent for a single generation. */
export const DOCS_CHAR_CAP = 8000;

export interface ReadDoc {
  name: string;
  text: string;
}

/** True for the plain-text formats we can read in the browser today. */
export function isAcceptedDoc(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED_DOC_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Read accepted text files; unsupported types and empty files are skipped. */
export async function readDocFiles(files: File[]): Promise<ReadDoc[]> {
  const accepted = files.filter((f) => isAcceptedDoc(f.name));
  const read = await Promise.all(
    accepted.map(async (f) => ({ name: f.name, text: (await f.text()).trim() })),
  );
  return read.filter((d) => d.text.length > 0);
}

/**
 * Concatenate docs into one grounding block (each under a `### name` header),
 * capped to {@link DOCS_CHAR_CAP} characters. Returns `undefined` when empty so
 * callers can omit the field entirely.
 */
export function concatDocs(docs: ReadDoc[]): string | undefined {
  const joined = docs
    .filter((d) => d.text)
    .map((d) => `### ${d.name}\n${d.text}`)
    .join("\n\n");
  if (!joined) return undefined;
  return joined.length > DOCS_CHAR_CAP ? joined.slice(0, DOCS_CHAR_CAP) : joined;
}
