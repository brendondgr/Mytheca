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
    // Untriaged default: Draft off, RAG on, "other".
    expect(result.current.docs[0].category).toBe("other");
    expect(result.current.docs[0].triaged).toBe(false);

    await act(async () => {
      await result.current.triage();
    });
    expect(vi.mocked(api.triageDocuments)).toHaveBeenCalled();
    // The mock cycles character/setting/other across the docs.
    expect(result.current.docs[0].category).toBe("character");
    expect(result.current.docs[1].category).toBe("setting");
    expect(result.current.docs.every((d) => d.triaged)).toBe(true);
  });

  it("builds a proposed world and reflects it into the editable fields", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    act(() => result.current.setSeed("A drowned harbor town."));
    await act(async () => {
      await result.current.build();
    });
    expect(vi.mocked(api.buildWorld)).toHaveBeenCalled();
    expect(result.current.proposed?.characters[0].name).toBe("Built Hero");
    // The build reflects the storyline core into the left column + stats.
    expect(result.current.fields.title).toBe("Built World");
    expect(result.current.stats[0].key).toBe("health");
    expect(result.current.isValid).toBe(true);
  });

  it("refuses to build with neither a seed nor draft docs", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await act(async () => {
      await result.current.build();
    });
    expect(vi.mocked(api.buildWorld)).not.toHaveBeenCalled();
    expect(result.current.error).toMatch(/seed or drop context/i);
  });

  it("commits the built world: storyline → stats → cast → settings → corpus", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    act(() => result.current.setSeed("A world."));
    await act(async () => {
      await result.current.addFiles([file("lore.md", "World lore.")]);
    });
    await act(async () => {
      await result.current.triage();
    });
    await act(async () => {
      await result.current.build();
    });

    let newId: string | null = null;
    await act(async () => {
      newId = await result.current.commit();
    });

    expect(newId).toBeTruthy();
    expect(vi.mocked(api.createStoryline)).toHaveBeenCalled();
    expect(vi.mocked(api.createStatDefinition)).toHaveBeenCalled();
    expect(vi.mocked(api.createCharacter)).toHaveBeenCalled();
    expect(vi.mocked(api.setCharacterStats)).toHaveBeenCalledWith(expect.any(String), { health: 100 });
    expect(vi.mocked(api.createSetting)).toHaveBeenCalled();
    expect(vi.mocked(api.bulkCreateContextDocuments)).toHaveBeenCalled();
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
