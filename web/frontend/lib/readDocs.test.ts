import { describe, it, expect } from "vitest";
import {
  concatDocs,
  docsForDraft,
  DOCS_CHAR_CAP,
  isAcceptedDoc,
  readDocFiles,
  type ReadDoc,
} from "./readDocs";

describe("readDocs", () => {
  it("accepts only plain-text doc extensions", () => {
    expect(isAcceptedDoc("bestiary.md")).toBe(true);
    expect(isAcceptedDoc("NOTES.TXT")).toBe(true);
    expect(isAcceptedDoc("lore.markdown")).toBe(true);
    expect(isAcceptedDoc("map.png")).toBe(false);
    expect(isAcceptedDoc("dossier.pdf")).toBe(false);
  });

  it("reads accepted files and skips unsupported / empty ones", async () => {
    const md = new File(["The Grull hunts by vibration."], "grull.md", {
      type: "text/markdown",
    });
    const png = new File(["binary"], "map.png", { type: "image/png" });
    const empty = new File(["   "], "blank.txt", { type: "text/plain" });

    const docs = await readDocFiles([md, png, empty]);
    expect(docs).toEqual([{ name: "grull.md", text: "The Grull hunts by vibration." }]);
  });

  it("concatenates docs under per-file headers", () => {
    const docs: ReadDoc[] = [
      { name: "a.md", text: "Alpha." },
      { name: "b.md", text: "Beta." },
    ];
    expect(concatDocs(docs)).toBe("### a.md\nAlpha.\n\n### b.md\nBeta.");
  });

  it("returns undefined when there is nothing to ground", () => {
    expect(concatDocs([])).toBeUndefined();
    expect(concatDocs([{ name: "x.md", text: "" }])).toBeUndefined();
  });

  it("caps the grounding block length", () => {
    const big: ReadDoc = { name: "huge.md", text: "x".repeat(DOCS_CHAR_CAP + 500) };
    expect((concatDocs([big]) ?? "").length).toBe(DOCS_CHAR_CAP);
  });

  it("keeps Draft-enabled (and unflagged) files for grounding, drops opted-out ones", () => {
    const docs: ReadDoc[] = [
      { name: "on.md", text: "On.", useDraft: true },
      { name: "legacy.md", text: "Legacy." }, // undefined = on (back-compat)
      { name: "off.md", text: "Off.", useDraft: false },
    ];
    expect(docsForDraft(docs).map((d) => d.name)).toEqual(["on.md", "legacy.md"]);
  });

  it("omits a Draft-disabled file's text from the grounding block", () => {
    const docs: ReadDoc[] = [
      { name: "keep.md", text: "KEEP_MARKER", useDraft: true },
      { name: "drop.md", text: "DROP_MARKER", useDraft: false },
    ];
    const grounding = concatDocs(docsForDraft(docs)) ?? "";
    expect(grounding).toContain("KEEP_MARKER");
    expect(grounding).not.toContain("DROP_MARKER");
  });
});
