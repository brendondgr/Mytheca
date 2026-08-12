import { describe, expect, it } from "vitest";
import {
  applyMention,
  filterMentions,
  findMentionQuery,
  MENTION_LIMIT,
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
  it("removes a tag and returns its id", () => {
    expect(stripMentions("@maerin.md what is she holding?", OPTS)).toEqual({
      text: "what is she holding?",
      ids: ["cd_m"],
    });
  });

  it("removes a mid-sentence tag without leaving a double space", () => {
    expect(stripMentions("check @harbor.md for the tide", OPTS)).toEqual({
      text: "check for the tide",
      ids: ["cd_h"],
    });
  });

  it("prefers the longest matching filename", () => {
    expect(stripMentions("@old harbor notes.md please", OPTS)).toEqual({
      text: "please",
      ids: ["cd_o"],
    });
  });

  it("collects several tags in order, deduped", () => {
    const { ids } = stripMentions("@harbor.md and @maerin.md and @harbor.md", OPTS);
    expect(ids).toEqual(["cd_h", "cd_m"]);
  });

  it("leaves an unknown @token alone and reports no id", () => {
    expect(stripMentions("@nothere.md stays", OPTS)).toEqual({
      text: "@nothere.md stays",
      ids: [],
    });
  });

  it("leaves a mid-word @ alone", () => {
    expect(stripMentions("write to me@maerin.md now", OPTS)).toEqual({
      text: "write to me@maerin.md now",
      ids: [],
    });
  });

  it("matches a tag case-insensitively", () => {
    expect(stripMentions("@MAERIN.MD hello", OPTS).ids).toEqual(["cd_m"]);
  });

  it("returns untouched text when nothing is tagged", () => {
    expect(stripMentions("just talking", OPTS)).toEqual({ text: "just talking", ids: [] });
  });

  it("is the self-healing path: a deleted tag drops its id", () => {
    // What the player typed, then edited back down by hand.
    expect(stripMentions("what is she holding?", OPTS).ids).toEqual([]);
  });
});
