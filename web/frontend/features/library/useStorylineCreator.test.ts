import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { useStorylineCreator } from "./useStorylineCreator";
import * as api from "@/lib/api";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

// The mock is module-scoped, so call history accrues across tests — clear it each
// time so the "not called" assertions reflect just the test under run.
beforeEach(() => vi.clearAllMocks());

function file(name: string, text: string): File {
  return new File([text], name, { type: "text/plain" });
}

describe("useStorylineCreator", () => {
  it("triages dropped docs into categories + Draft/RAG flags", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await act(async () => {
      await result.current.addFiles([file("a.md", "A person."), file("b.md", "A place.")]);
    });
    expect(result.current.docs).toHaveLength(2);
    // Untriaged default: Draft on, RAG on, "select" (uncategorized).
    expect(result.current.docs[0].category).toBe("select");
    expect(result.current.docs[0].triaged).toBe(false);

    await act(async () => {
      await result.current.triage();
    });
    expect(vi.mocked(api.triageDocumentsStream)).toHaveBeenCalled();
    // The mock cycles character/setting/other across the docs.
    expect(result.current.docs[0].category).toBe("character");
    expect(result.current.docs[1].category).toBe("setting");
    expect(result.current.docs.every((d) => d.triaged)).toBe(true);
    // The per-file indicator clears once the stream completes.
    expect(result.current.triageActive).toBeNull();
  });

  it("drops dropped docs Draft-on and bulk-clears/restores them via setAllDocUse", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await act(async () => {
      await result.current.addFiles([file("a.md", "A person."), file("b.md", "A place.")]);
    });
    expect(result.current.docs.every((d) => d.useDraft)).toBe(true);

    act(() => result.current.setAllDocUse("useDraft", false));
    expect(result.current.docs.every((d) => d.useDraft === false)).toBe(true);
    // RAG is untouched by a Draft-only bulk change.
    expect(result.current.docs.every((d) => d.useRag)).toBe(true);

    act(() => result.current.setAllDocUse("useDraft", true));
    expect(result.current.docs.every((d) => d.useDraft)).toBe(true);
  });

  it("exposes only the Draft-selected docs as the assistant's grounding", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await act(async () => {
      await result.current.addFiles([
        file("keep.md", "The harbour drowns at every ninth bell."),
        file("drop.md", "An unrelated shopping list."),
      ]);
    });
    // Both are Draft-on by default, so both ground the assistant.
    expect(result.current.docsOverview()).toContain("ninth bell");
    expect(result.current.docsOverview()).toContain("shopping list");

    act(() => result.current.toggleDocUse("drop.md", "useDraft"));
    const grounding = result.current.docsOverview();
    expect(grounding).toContain("ninth bell");
    expect(grounding).not.toContain("shopping list");

    // Clearing every selection drops the field entirely rather than sending "".
    act(() => result.current.setAllDocUse("useDraft", false));
    expect(result.current.docsOverview()).toBeUndefined();
  });

  it("adds a whole batch pre-categorized when an upload target is chosen", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await act(async () => {
      await result.current.addFiles(
        [file("a.md", "One hero."), file("b.md", "Another hero.")],
        { category: "character", useDraft: true, useRag: false },
      );
    });
    expect(result.current.docs).toHaveLength(2);
    expect(result.current.docs.every((d) => d.category === "character")).toBe(true);
    expect(result.current.docs.every((d) => d.triaged)).toBe(true);
    expect(result.current.docs[0].useDraft).toBe(true);
    expect(result.current.docs[0].useRag).toBe(false);
  });

  it("Triage only sweeps the Uncategorized docs, leaving pre-categorized ones alone", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    // One pre-categorized as a setting, one left Uncategorized.
    await act(async () => {
      await result.current.addFiles([file("place.md", "A place.")], { category: "setting" });
      await result.current.addFiles([file("mystery.md", "Unknown.")]);
    });
    await act(async () => {
      await result.current.triage();
    });
    // Only the Uncategorized doc was sent to the stream.
    const sent = vi.mocked(api.triageDocumentsStream).mock.calls[0][0];
    expect(sent).toEqual([{ name: "mystery.md", text: "Unknown." }]);
    // The pre-categorized setting keeps its category; the leftover got classified.
    const byName = Object.fromEntries(result.current.docs.map((d) => [d.name, d]));
    expect(byName["place.md"].category).toBe("setting");
    expect(byName["mystery.md"].category).not.toBe("select");
  });

  it("commits by hand: creates the storyline, its stats, and the triaged corpus", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    act(() => result.current.setField("title", "A World"));
    await act(async () => {
      await result.current.addFiles([file("lore.md", "World lore.")]);
    });
    await act(async () => {
      await result.current.triage();
    });

    let newId: string | null = null;
    await act(async () => {
      newId = await result.current.commit();
    });

    expect(newId).toBeTruthy();
    expect(vi.mocked(api.createStoryline)).toHaveBeenCalledWith(
      expect.objectContaining({ title: "A World" }),
    );
    expect(vi.mocked(api.bulkCreateContextDocuments)).toHaveBeenCalled();
  });

  it("commit forwards the author's Build-world choices to the population step", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    act(() => result.current.setField("title", "A World"));

    let newId: string | null = null;
    await act(async () => {
      newId = await result.current.commit({ enabled: true, withArtwork: true });
    });

    expect(newId).toBeTruthy();
    expect(vi.mocked(api.populateWorldStream)).toHaveBeenCalledWith(
      newId,
      expect.objectContaining({ withArtwork: true }),
    );
  });

  it("surfaces a population problem as an error without losing the world", async () => {
    vi.mocked(api.populateWorldStream).mockImplementationOnce(async function* () {
      yield { type: "error" as const, message: "Could not write Maerin.", fatal: false };
      yield { type: "done" as const, characters: 0, settings: 0 };
    } as never);
    const { result } = renderHook(() => useStorylineCreator());
    act(() => result.current.setField("title", "A World"));

    let newId: string | null = null;
    await act(async () => {
      newId = await result.current.commit({ enabled: true, withArtwork: false });
    });

    expect(newId).toBeTruthy();
    await waitFor(() => expect(result.current.error).toBe("Could not write Maerin."));
  });

  it("skips population entirely when the author declines it", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    act(() => result.current.setField("title", "A World"));
    await act(async () => {
      await result.current.commit({ enabled: false, withArtwork: false });
    });
    expect(vi.mocked(api.populateWorldStream)).not.toHaveBeenCalled();
  });

  it("loads an existing storyline + stats + corpus in edit mode", async () => {
    vi.mocked(api.getStoryline).mockResolvedValueOnce({
      id: "embergate",
      title: "Embergate",
      genre: "Maritime",
      tagline: "t",
      premise: "p",
      worldPrimer: "wp",
      symbol: "◆",
      symbolColor: "#C8862A",
    });
    const { result } = renderHook(() => useStorylineCreator("embergate"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.fields.title).toBe("Embergate");
    expect(result.current.fields.worldPrimer).toBe("wp");
    expect(vi.mocked(api.listContextDocuments)).toHaveBeenCalledWith("embergate");
  });

  it("re-hydrates the context panel with the saved corpus on edit (lost-track fix)", async () => {
    vi.mocked(api.getStoryline).mockResolvedValueOnce({
      id: "embergate",
      title: "Embergate",
      genre: "Maritime",
      symbol: "◆",
      symbolColor: "#C8862A",
    });
    vi.mocked(api.listContextDocuments).mockResolvedValueOnce([
      {
        id: "cd1", storylineId: "embergate", name: "lore.md", content: "old lore",
        category: "other", includeDraft: true, includeRag: true, includeExtract: false,
        source: "upload", charCount: 8,
      },
      {
        id: "cd2", storylineId: "embergate", name: "maerin-notes.md", content: "x",
        category: "character", includeDraft: false, includeRag: true, includeExtract: false,
        source: "upload", charCount: 1, entityType: "character", entityId: "c1",
      },
    ]);
    const { result } = renderHook(() => useStorylineCreator("embergate"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    // The storyline-level doc reappears in the panel (was previously lost); the
    // entity-scoped doc belongs to a character editor, so it is NOT shown here.
    expect(result.current.docs.map((d) => d.name)).toEqual(["lore.md"]);
    expect(result.current.docs[0].triaged).toBe(true);
    expect(result.current.docs[0].useDraft).toBe(true);
  });

  it("re-embeds the corpus, streaming progress and refreshing the indexed count", async () => {
    vi.mocked(api.getStoryline).mockResolvedValueOnce({
      id: "embergate", title: "Embergate", genre: "Maritime", symbol: "◆", symbolColor: "#C8862A",
    });
    vi.mocked(api.reindexCorpusStream).mockImplementationOnce(async function* () {
      yield { stage: "embedding", index: 1, total: 2, name: "Maerin", type: "character" };
      yield { stage: "done", indexed: 2, skipped: 0, total: 2, available: true };
    });
    vi.mocked(api.getRagStatus).mockResolvedValue({ available: true, indexed: 2 });

    const { result } = renderHook(() => useStorylineCreator("embergate"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.reembed();
    });
    expect(vi.mocked(api.reindexCorpusStream)).toHaveBeenCalledWith("embergate");
    expect(result.current.ragStatus).toEqual({ available: true, indexed: 2 });
    expect(result.current.reembedProgress).toContain("2");
  });

  it("commit in edit mode updates the storyline (no new entities)", async () => {
    vi.mocked(api.getStoryline).mockResolvedValueOnce({
      id: "embergate",
      title: "Embergate",
      genre: "Maritime",
      symbol: "◆",
      symbolColor: "#C8862A",
    });
    const { result } = renderHook(() => useStorylineCreator("embergate"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setField("tagline", "A new tagline."));
    await act(async () => {
      await result.current.commit();
    });
    expect(vi.mocked(api.updateStoryline)).toHaveBeenCalledWith(
      "embergate",
      expect.objectContaining({ tagline: "A new tagline." }),
    );
    expect(vi.mocked(api.createStoryline)).not.toHaveBeenCalled();
  });
});
