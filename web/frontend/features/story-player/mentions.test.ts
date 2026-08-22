import { describe, expect, it } from "vitest";
import {
  applyMention,
  filterMentions,
  findMentionQuery,
  MENTION_LIMIT,
  removeMention,
  splitDirectives,
  stripMentions,
  type MentionOption,
} from "./mentions";

const OPTS: MentionOption[] = [
  { id: "cd_m", name: "maerin.md" },
  { id: "cd_h", name: "harbor.md" },
  { id: "cd_o", name: "old harbor notes.md" },
];

describe("findMentionQuery", () => {
  it("opens on an @ at the start of the text", () => {
    expect(findMentionQuery("@mae", 4)).toEqual({ start: 0, query: "mae" });
  });

  it("opens on an @ after whitespace", () => {
    expect(findMentionQuery("look at @har", 12)).toEqual({ start: 8, query: "har" });
  });

  it("opens on a bare @ with no query yet", () => {
    expect(findMentionQuery("tell me @", 9)).toEqual({ start: 8, query: "" });
  });

  it("does not open mid-word", () => {
    expect(findMentionQuery("email@example.com", 17)).toBeNull();
  });

  it("does not reach across a newline", () => {
    expect(findMentionQuery("@mae\nand then", 13)).toBeNull();
  });

  it("reads only up to the caret, not the whole string", () => {
    expect(findMentionQuery("@maerin.md trailing", 4)).toEqual({ start: 0, query: "mae" });
  });

  it("allows spaces so a filename with spaces can be typed", () => {
    expect(findMentionQuery("see @old harbor", 15)).toEqual({ start: 4, query: "old harbor" });
  });

  it("returns null when there is no @ at all", () => {
    expect(findMentionQuery("just talking", 12)).toBeNull();
  });

  it("clamps an out-of-range caret", () => {
    expect(findMentionQuery("@mae", 999)).toEqual({ start: 0, query: "mae" });
  });
});

describe("filterMentions", () => {
  it("lists everything for an empty query", () => {
    expect(filterMentions(OPTS, "")).toHaveLength(3);
  });

  it("matches case-insensitively", () => {
    expect(filterMentions(OPTS, "MAE").map((o) => o.id)).toEqual(["cd_m"]);
  });

  it("ranks prefix matches ahead of substring matches", () => {
    expect(filterMentions(OPTS, "harbor").map((o) => o.id)).toEqual(["cd_h", "cd_o"]);
  });

  it("returns nothing when no name matches", () => {
    expect(filterMentions(OPTS, "zzz")).toEqual([]);
  });

  it("caps the list", () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ id: `cd_${i}`, name: `doc${i}.md` }));
    expect(filterMentions(many, "")).toHaveLength(MENTION_LIMIT);
  });
});

describe("applyMention", () => {
  it("replaces the query run with the full name plus a space", () => {
    expect(applyMention("@mae", 0, 4, "maerin.md")).toEqual({
      text: "@maerin.md ",
      caret: 11,
    });
  });

  it("preserves text on both sides", () => {
    const { text, caret } = applyMention("look at @har and go", 8, 12, "harbor.md");
    expect(text).toBe("look at @harbor.md  and go");
    expect(text.slice(0, caret)).toBe("look at @harbor.md ");
  });
});

describe("stripMentions", () => {
  // The sigil goes; the NAME stays. Deleting the whole token used to send "Hey @Mei" as
  // "Hey" — a visual glitch as the chip appears, and the removal of the one noun the
  // sentence was about, so the intent and direction agents never saw who was meant.
  it("drops the sigil and keeps the name, returning its id", () => {
    expect(stripMentions("@maerin.md what is she holding?", OPTS)).toMatchObject({
      text: "maerin.md what is she holding?",
      ids: ["cd_m"],
    });
  });

  it("keeps a mid-sentence name in place, with its spacing intact", () => {
    expect(stripMentions("check @harbor.md for the tide", OPTS)).toMatchObject({
      text: "check harbor.md for the tide",
      ids: ["cd_h"],
    });
  });

  it("prefers the longest matching filename", () => {
    expect(stripMentions("@old harbor notes.md please", OPTS)).toMatchObject({
      text: "old harbor notes.md please",
      ids: ["cd_o"],
    });
  });

  it("preserves the player's own casing rather than the option's", () => {
    // `hit.name` would normalise it; the text is the player's prose, not a lookup key.
    expect(stripMentions("@MAERIN.MD hello", OPTS).text).toBe("MAERIN.MD hello");
  });

  it("collects several tags in order, deduped", () => {
    const { ids } = stripMentions("@harbor.md and @maerin.md and @harbor.md", OPTS);
    expect(ids).toEqual(["cd_h", "cd_m"]);
  });

  it("leaves an unknown @token alone and reports no id", () => {
    expect(stripMentions("@nothere.md stays", OPTS)).toMatchObject({
      text: "@nothere.md stays",
      ids: [],
    });
  });

  it("leaves a mid-word @ alone", () => {
    expect(stripMentions("write to me@maerin.md now", OPTS)).toMatchObject({
      text: "write to me@maerin.md now",
      ids: [],
    });
  });

  it("matches a tag case-insensitively", () => {
    expect(stripMentions("@MAERIN.MD hello", OPTS).ids).toEqual(["cd_m"]);
  });

  it("returns untouched text when nothing is tagged", () => {
    expect(stripMentions("just talking", OPTS)).toMatchObject({ text: "just talking", ids: [] });
  });

  it("is the self-healing path: a deleted tag drops its id", () => {
    // What the player typed, then edited back down by hand. The bare name left behind by
    // stripping is NOT a tag — only the `@` makes one, so re-stripping sent text is a no-op.
    expect(stripMentions("what is she holding?", OPTS).ids).toEqual([]);
    expect(stripMentions("maerin.md what is she holding?", OPTS).ids).toEqual([]);
  });
});

describe("removeMention", () => {
  const maerin = OPTS.find((o) => o.id === "cd_m")!;
  const harbor = OPTS.find((o) => o.id === "cd_h")!;

  it("deletes the whole token, name and all — the chip's ×", () => {
    expect(removeMention("@maerin.md what is she holding?", maerin)).toBe(
      "what is she holding?",
    );
  });

  it("takes one trailing space with it, so a mid-sentence removal leaves no gap", () => {
    expect(removeMention("check @harbor.md for the tide", harbor)).toBe("check for the tide");
  });

  it("removes every occurrence — one chip stands for all of them", () => {
    expect(removeMention("@harbor.md then @harbor.md again", harbor)).toBe("then again");
  });

  it("leaves other options' tags alone", () => {
    expect(removeMention("@harbor.md and @maerin.md", harbor)).toBe("and @maerin.md");
  });

  it("matches case-insensitively but is not fooled by a mid-word @", () => {
    expect(removeMention("@MAERIN.MD gone", maerin)).toBe("gone");
    expect(removeMention("write to me@maerin.md now", maerin)).toBe("write to me@maerin.md now");
  });

  it("returns the text unchanged when the option is not tagged", () => {
    expect(removeMention("nothing tagged here", maerin)).toBe("nothing tagged here");
  });
});

describe("cast mentions", () => {
  const MIXED: MentionOption[] = [
    { id: "cd_m", name: "maerin.md", kind: "doc", charCount: 120 },
    { id: "ch_mei", name: "Mei", kind: "cast", mono: "M", color: "#8E2B1C" },
    { id: "cd_h", name: "harbor.md", kind: "doc", charCount: 80 },
    { id: "ch_ald", name: "Aldous", kind: "cast", mono: "A", color: "#2B5E8E" },
  ];

  it("splits the ids by what they do", () => {
    // A doc grounds the line; a character aims it. They cannot share one list.
    const out = stripMentions("@Mei, look at @harbor.md", MIXED);
    expect(out.castIds).toEqual(["ch_mei"]);
    expect(out.docIds).toEqual(["cd_h"]);
    expect(out.text).toBe("Mei, look at harbor.md");
  });

  it("keeps `ids` as an alias of the document ids", () => {
    // The name predates cast mentions and still means "the files this turn carries".
    const out = stripMentions("@Mei and @harbor.md", MIXED);
    expect(out.ids).toEqual(out.docIds);
    expect(out.ids).not.toContain("ch_mei");
  });

  it("offers a character before a document within the same match tier", () => {
    // A typed `@M` should reach Mei before maerin.md — the player is far more often
    // addressing someone than attaching a file.
    // `harbor.md` also contains an "m" (the extension), so it trails in the second tier.
    expect(filterMentions(MIXED, "m").map((o) => o.id)).toEqual(["ch_mei", "cd_m", "cd_h"]);
  });

  it("still lets a stronger match win over kind", () => {
    // `harbor.md` starts with the query; no character does. Tier beats kind.
    expect(filterMentions(MIXED, "harbor")[0].id).toBe("cd_h");
  });

  it("puts cast first in the unfiltered list too", () => {
    expect(filterMentions(MIXED, "").map((o) => o.id)).toEqual([
      "ch_mei",
      "ch_ald",
      "cd_m",
      "cd_h",
    ]);
  });

  it("treats an option with no kind as a document, so old call sites are unchanged", () => {
    const out = stripMentions("@maerin.md now", [{ id: "cd_m", name: "maerin.md" }]);
    expect(out.docIds).toEqual(["cd_m"]);
    expect(out.castIds).toEqual([]);
  });

  it("removes a cast tag by its whole token, like a doc tag", () => {
    expect(removeMention("@Mei, look here", MIXED[1])).toBe(", look here");
  });
});

describe("splitDirectives", () => {
  const MIXED: MentionOption[] = [
    { id: "ch_mei", name: "Mei", kind: "cast" },
    { id: "ch_ald", name: "Aldous", kind: "cast" },
    { id: "cd_h", name: "harbor.md", kind: "doc" },
  ];

  it("reads the box one line at a time, aiming each at its @mention", () => {
    expect(
      splitDirectives("@Mei backs down\n@Aldous grabs her wrist\nthe lamp goes over", MIXED),
    ).toEqual([
      { text: "Mei backs down", actorId: "ch_mei" },
      { text: "Aldous grabs her wrist", actorId: "ch_ald" },
      { text: "the lamp goes over", actorId: null },
    ]);
  });

  it("sends nothing at all when no line names a character", () => {
    // Free prose stays free prose: the backend's parse step is what splits "Mei storms out
    // and Aldous grabs her wrist" into two requirements, and sending it as one directive
    // would quietly disable that.
    expect(splitDirectives("Mei storms out and Aldous grabs her wrist", MIXED)).toEqual([]);
    expect(splitDirectives("", MIXED)).toEqual([]);
  });

  it("skips blank lines", () => {
    expect(splitDirectives("@Mei backs down\n\n   \nthe lamp goes over", MIXED)).toEqual([
      { text: "Mei backs down", actorId: "ch_mei" },
      { text: "the lamp goes over", actorId: null },
    ]);
  });

  it("takes the first character on a line when several are named", () => {
    expect(splitDirectives("@Mei apologises to @Aldous", MIXED)).toEqual([
      { text: "Mei apologises to Aldous", actorId: "ch_mei" },
    ]);
  });

  it("does not treat a document mention as a target", () => {
    // A doc grounds a line; it cannot perform one. Without a cast mention anywhere, the
    // whole box is still free prose.
    expect(splitDirectives("check @harbor.md first", MIXED)).toEqual([]);
  });

  it("keeps the name in the directive text, as the send path does", () => {
    expect(splitDirectives("@Mei backs down", MIXED)[0].text).toBe("Mei backs down");
  });
});

