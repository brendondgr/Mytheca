/**
 * Derive a 1–2 letter monogram from a name (ported from the reference).
 * One word -> first two letters; multiple -> first letter of the first two words.
 * Curated characters carry an explicit `mono`; this is for newly-created ones.
 */
export function monoOf(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
