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
    expect(vi.mocked(api.triageDocumentsStream)).toHaveBeenCalled();
    // The mock cycles character/setting/other across the docs.
    expect(result.current.docs[0].category).toBe("character");
    expect(result.current.docs[1].category).toBe("setting");
    expect(result.current.docs.every((d) => d.triaged)).toBe(true);
    // The per-file indicator clears once the stream completes.
    expect(result.current.triageActive).toBeNull();
  });

  it("builds a proposed world and reflects it into the editable fields", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    act(() => result.current.setSeed("A drowned harbor town."));
    await act(async () => {
      await result.current.build();
    });
    expect(vi.mocked(api.buildWorldStream)).toHaveBeenCalled();
    expect(result.current.proposed?.characters[0].name).toBe("Built Hero");
    // The build reflects the storyline core into the left column + stats.
    expect(result.current.fields.title).toBe("Built World");
    expect(result.current.stats[0].key).toBe("health");
    expect(result.current.isValid).toBe(true);
    // The blueprint concepts seeded the live skeleton (one cast + one setting).
    expect(result.current.planConcepts?.characters).toHaveLength(1);
  });

  it("refuses to build with neither a seed nor draft docs", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await act(async () => {
      await result.current.build();
    });
    expect(vi.mocked(api.buildWorldStream)).not.toHaveBeenCalled();
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

  it("renders portraits + scene art on commit when ComfyUI is configured", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await waitFor(() => expect(result.current.imagesAvailable).toBe(true));
    act(() => result.current.setSeed("A world."));
    await act(async () => {
      await result.current.build();
    });
    await act(async () => {
      await result.current.commit();
    });
    expect(vi.mocked(api.generatePortraitPrompts)).toHaveBeenCalled();
    expect(vi.mocked(api.generatePortrait)).toHaveBeenCalled();
    expect(vi.mocked(api.generateSceneArtPrompts)).toHaveBeenCalled();
    expect(vi.mocked(api.generateSceneArt)).toHaveBeenCalled();
    expect(vi.mocked(api.updateCharacter)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ portrait: expect.any(String) }),
    );
    // The rendered images are patched back onto the displayed proposal (live preview).
    expect(result.current.proposed?.characters[0].portrait).toBe("/media/portraits/test.webp");
    expect(result.current.proposed?.settings[0].image).toBe("/media/scenes/test.webp");
  });

  it("skips images when ComfyUI is not configured", async () => {
    vi.mocked(api.getSettings).mockResolvedValueOnce({
      llm: {
        baseUrl: "",
        model: "",
        provider: "openai-compatible",
        params: { temperature: 0.7, maxTokens: 512, topP: 1, frequencyPenalty: 0, presencePenalty: 0 },
        hasApiKey: false,
        apiKeyHint: null,
      },
      library: { defaultStorylineId: null, openLastStoryline: true },
      comfy: {
        baseUrl: "",
        workflow: "",
        params: { steps: 4, cfg: 1, width: 1024, height: 1024, batchSize: 1, negativePrompt: "" },
      },
    });
    const { result } = renderHook(() => useStorylineCreator());
    await waitFor(() => expect(result.current.imagesAvailable).toBe(false));
    act(() => result.current.setSeed("A world."));
    await act(async () => {
      await result.current.build();
    });
    await act(async () => {
      await result.current.commit();
    });
    expect(vi.mocked(api.generatePortrait)).not.toHaveBeenCalled();
    expect(vi.mocked(api.generateSceneArt)).not.toHaveBeenCalled();
  });

  it("a failed image render does not abort the commit", async () => {
    const { result } = renderHook(() => useStorylineCreator());
    await waitFor(() => expect(result.current.imagesAvailable).toBe(true));
    vi.mocked(api.generatePortrait).mockRejectedValueOnce(new Error("comfy down"));
    act(() => result.current.setSeed("A world."));
    await act(async () => {
      await result.current.build();
    });
    let id: string | null = null;
    await act(async () => {
      id = await result.current.commit();
    });
    expect(id).toBeTruthy(); // commit still succeeds…
    expect(vi.mocked(api.createSetting)).toHaveBeenCalled(); // …and continues past the failure
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
