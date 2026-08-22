/**
 * `@` file tagging — caret detection, filtering, insertion, and strip-and-resolve.
 *
 * The composer lets the player type `@` to pull one of the storyline's context documents
 * into the next turn. All of the fiddly parts — where a mention starts relative to the
 * caret, how a filename containing spaces is matched back out of free prose, which ids are
 * still present after editing — live here as pure functions so they can be tested without
 * a DOM.
 *
 * The important invariant is in {@link stripMentions}: the ids sent with a turn are
 * **re-derived from the final text** rather than accumulated as the player clicks. Deleting
 * `@maerin.md` by hand therefore drops the tag with no stale state to reconcile.
 */

/** One taggable context document, as listed by `GET …/context-docs/index`. */
export interface MentionOption {
  id: string;
  name: string;
  category?: string;
  charCount?: number;
}

/** How many rows the menu shows at once. */
export const MENTION_LIMIT = 8;

/** Longest `@…` run still treated as an open mention query. */
const MAX_QUERY = 60;

/** An open mention: where the `@` sits and what has been typed after it. */
export interface MentionQuery {
  /** Index of the `@` itself. */
  start: number;
  /** The text between the `@` and the caret (may contain spaces, never a newline). */
  query: string;
}

/**
 * Find the mention the caret is currently inside, or `null`.
 *
 * A mention starts at an `@` that is at the start of the text or preceded by whitespace —
 * so `email@example.com` never opens the menu — and runs to the caret, stopping at a
 * newline or {@link MAX_QUERY} characters.
 */
export function findMentionQuery(text: string, caret: number): MentionQuery | null {
  const pos = Math.max(0, Math.min(caret, text.length));
  for (let i = pos - 1; i >= 0 && pos - i <= MAX_QUERY + 1; i -= 1) {
    const ch = text[i];
    if (ch === "\n") return null;
    if (ch !== "@") continue;
    const before = i === 0 ? "" : text[i - 1];
    if (before !== "" && !/\s/.test(before)) return null;
    return { start: i, query: text.slice(i + 1, pos) };
  }
  return null;
}

/**
 * The options matching `query`, prefix matches first, capped at {@link MENTION_LIMIT}.
 * An empty query lists everything (capped); no match yields `[]`, which hides the menu.
 */
export function filterMentions(
  options: MentionOption[],
  query: string,
): MentionOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return options.slice(0, MENTION_LIMIT);
  const prefix: MentionOption[] = [];
  const rest: MentionOption[] = [];
  for (const opt of options) {
    const name = opt.name.toLowerCase();
    if (name.startsWith(q)) prefix.push(opt);
    else if (name.includes(q)) rest.push(opt);
  }
  return [...prefix, ...rest].slice(0, MENTION_LIMIT);
}

/** The result of editing the text: the new value and where the caret should land. */
export interface MentionEdit {
  text: string;
  caret: number;
}

/**
 * Replace the open `@query` run with `@<name> `, leaving the caret after the trailing space
 * so the player can keep typing.
 */
export function applyMention(
  text: string,
  start: number,
  caret: number,
  name: string,
): MentionEdit {
  const token = `@${name} `;
  const next = text.slice(0, start) + token + text.slice(caret);
  return { text: next, caret: start + token.length };
}

/** The cleaned prose plus the document ids it referenced. */
export interface StrippedMentions {
  text: string;
  ids: string[];
}

/**
 * Drop the `@` sigil from every mention that resolves to a known option, **keeping the
 * name**, and return the ids.
 *
 * This used to delete the whole token: `"Hey @Mei"` was sent as `"Hey"`, and
 * `"read @maerin.md"` as `"read"`. That is wrong twice over — it reads as a visual glitch
 * as the chip appears, and it removes the one noun the sentence was about, so the intent
 * and direction agents never see who or what the player meant. Now only the sigil goes:
 * `"Hey @Mei"` → `"Hey Mei"`, `"read @maerin.md"` → `"read maerin.md"`. The name is
 * preserved **as the player typed it**, casing included; the id still resolves, so nothing
 * downstream changes.
 *
 * Names are matched **longest first** so a filename containing spaces or dots
 * (`old harbor notes.md`) wins over a shorter one that prefixes it.
 *
 * To *untag* — which is what the chip's "×" does — use {@link removeMention}: with the name
 * surviving, deleting the token is now a different operation from preparing the text to
 * send.
 */
export function stripMentions(
  text: string,
  options: MentionOption[],
): StrippedMentions {
  const byLength = [...options].sort((a, b) => b.name.length - a.name.length);
  const ids: string[] = [];
  let out = "";
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    const boundary = i === 0 || /\s/.test(text[i - 1]);
    if (ch !== "@" || !boundary) {
      out += ch;
      i += 1;
      continue;
    }
    const after = text.slice(i + 1);
    const hit = byLength.find((opt) =>
      after.toLowerCase().startsWith(opt.name.toLowerCase()),
    );
    if (!hit) {
      out += ch;
      i += 1;
      continue;
    }
    if (!ids.includes(hit.id)) ids.push(hit.id);
    // The matched run as the player typed it — not `hit.name`, so their casing survives.
    out += text.slice(i + 1, i + 1 + hit.name.length);
    i += 1 + hit.name.length;
    // The trailing space is NOT swallowed any more: the name stays, so the space between it
    // and the next word is part of the sentence.
  }
  return { text: out.replace(/[ \t]{2,}/g, " ").trim(), ids };
}

/**
 * Delete a mention's whole `@<name>` token — the chip's "×" behaviour.
 *
 * Separate from {@link stripMentions} because the two now want opposite things: stripping
 * prepares the text to send and keeps the name, while untagging removes the reference
 * entirely. One trailing space goes with the token so removing a mid-sentence tag does not
 * leave a gap. Every occurrence is removed, since one chip stands for every mention of that
 * option in either box.
 */
export function removeMention(text: string, option: MentionOption): string {
  const name = option.name.toLowerCase();
  let out = "";
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    const boundary = i === 0 || /\s/.test(text[i - 1]);
    if (ch === "@" && boundary && text.slice(i + 1).toLowerCase().startsWith(name)) {
      i += 1 + option.name.length;
      if (text[i] === " ") i += 1;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out.replace(/[ \t]{2,}/g, " ").trim();
}
