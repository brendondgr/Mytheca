import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useLibraryState } from "./useLibraryState";
import * as api from "@/lib/api";
import { SEED_CHARACTERS } from "@/lib/seed-data";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

/** Drive the hook's character-authoring handlers directly (no UI). */
describe("useLibraryState — character authoring", () => {
  async function mountReady() {
    const hook = renderHook(() => useLibraryState());
    await waitFor(() => expect(hook.result.current.activeStorylineId).toBeTruthy());
    return hook;
  }

  it("drafts a full character and auto-proposes starting stats", async () => {
    const { result } = await mountReady();

    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("_prompt", "A by-the-book harbor captain."));
    await act(async () => {
      await result.current.draftCharacter();
    });

    expect(vi.mocked(api.draftCharacter)).toHaveBeenCalled();
    expect(result.current.draft.name).toBe("Drafted Hero");
    expect(result.current.draft.appearance).toBe("A drafted appearance.");
    expect(result.current.draft.background).toBe("A drafted background.");
    expect(result.current.draft.personality).toBe("A drafted personality.");
    expect(result.current.draft._ai).toBe(true);
    // Starting stats should be auto-proposed using the drafted fields.
    expect(vi.mocked(api.proposeStartingStats)).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Drafted Hero", role: "Drafted Role" }),
    );
    expect(result.current.draft._startingStats?.map((p) => p.key)).toEqual(["health", "trust"]);
  });

  it("lights the active field during the draft, then clears it when done", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("_prompt", "A by-the-book harbor captain."));

    let pending: Promise<void>;
    act(() => {
      pending = result.current.draftCharacter();
    });
    // Mid-reveal, some field is the active (being-written) one, on the identity stage.
    await waitFor(() => expect(result.current.activeField).not.toBeNull());
    expect(result.current.draftStage).toBe("identity");

    await act(async () => {
      await pending!;
    });
    // Fully drafted → highlights cleared.
    expect(result.current.activeField).toBeNull();
    expect(result.current.draftStage).toBeNull();
    expect(result.current.draft.personality).toBe("A drafted personality.");
  });

  it("still succeeds when auto-stat proposal fails during draft", async () => {
    vi.mocked(api.proposeStartingStats).mockRejectedValueOnce(new Error("LLM unavailable"));
    const { result } = await mountReady();

    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("_prompt", "A rogue cartographer."));
    await act(async () => {
      await result.current.draftCharacter();
    });

    // Draft fields must be populated even if stat proposal failed.
    expect(result.current.draft.name).toBe("Drafted Hero");
    expect(result.current.draft._ai).toBe(true);
    // No stats proposed — graceful degradation.
    expect(result.current.draft._startingStats).toBeUndefined();
    // No error surfaced to the user.
    expect(result.current.error).toBeNull();
  });

  it("generates portrait prompts, then renders a portrait into the draft", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("appearance", "A young orc warrior."));

    await act(async () => {
      await result.current.generatePortraitPrompts();
    });
    expect(result.current.draft._portraitPositive).toContain("watercolor portrait");

    await act(async () => {
      await result.current.generatePortrait();
    });
    expect(vi.mocked(api.generatePortrait)).toHaveBeenCalledWith(
      expect.objectContaining({ positive: expect.stringContaining("watercolor portrait") }),
    );
    expect(result.current.draft.portrait).toBe("/media/portraits/test.webp");
  });

  it("persists the portrait prompts with the character on save", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("name", "Gorrok"));
    act(() => result.current.setDraft("appearance", "A young orc warrior."));
    await act(async () => {
      await result.current.generatePortraitPrompts();
    });
    await act(async () => {
      await result.current.submit();
    });
    // The prompts that produced the portrait are sent in the create payload.
    expect(vi.mocked(api.createCharacter)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        portraitPositive: expect.stringContaining("watercolor portrait"),
        portraitNegative: expect.any(String),
      }),
    );
  });

  it("re-hydrates saved portrait prompts when the character editor opens", async () => {
    vi.mocked(api.listCharacters).mockResolvedValueOnce([
      { ...SEED_CHARACTERS[0], portraitPositive: "saved positive", portraitNegative: "saved negative" },
    ]);
    const { result } = await mountReady();
    const someId = result.current.characters[0].id;
    act(() => result.current.editCharacter(someId));
    await waitFor(() => expect(result.current.draft._portraitPositive).toBe("saved positive"));
    expect(result.current.draft._portraitNegative).toBe("saved negative");
  });

  it("proposes starting stats keyed to the world's schema", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));

    await act(async () => {
      await result.current.proposeStartingStats();
    });
    expect(result.current.draft._startingStats?.map((p) => p.key)).toEqual(["health", "trust"]);
  });

  it("applies proposed starting stats with the character on save", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("name", "Grimm"));
    await act(async () => {
      await result.current.proposeStartingStats();
    });
    await act(async () => {
      await result.current.submit();
    });

    expect(vi.mocked(api.createCharacter)).toHaveBeenCalled();
    expect(vi.mocked(api.setCharacterStats)).toHaveBeenCalledWith(
      expect.any(String),
      { health: 90, trust: 1 },
    );
  });

  it("auto-generates voice samples during draft (before stats)", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("_prompt", "A wary harbor smuggler."));
    await act(async () => {
      await result.current.draftCharacter();
    });
    // Voice samples derived from the drafted prose land on the draft.
    expect(vi.mocked(api.proposeVoiceSamples)).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Drafted Hero" }),
    );
    expect(result.current.draft._voiceSamples?.map((s) => s.situation)).toEqual([
      "greeted warmly",
      "offered a bribe",
    ]);
  });

  it("still drafts when voice-sample proposal fails", async () => {
    vi.mocked(api.proposeVoiceSamples).mockRejectedValueOnce(new Error("LLM unavailable"));
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("_prompt", "A rogue cartographer."));
    await act(async () => {
      await result.current.draftCharacter();
    });
    expect(result.current.draft.name).toBe("Drafted Hero");
    // Silent degradation: the samples stay at the seeded empty default.
    expect(result.current.draft._voiceSamples).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it("proposes voice samples on demand (the editor's Redo action)", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    await act(async () => {
      await result.current.proposeVoiceSamples();
    });
    expect(result.current.draft._voiceSamples?.[0].sample).toBe("State your business.");
  });

  it("persists voice samples with the character on save (trimming blank rows)", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("name", "Fenwick"));
    act(() =>
      result.current.setDraft("_voiceSamples", [
        { situation: " cornered ", sample: " Back off. Now. " },
        { situation: "empty row", sample: "   " }, // dropped: no response text
      ]),
    );
    await act(async () => {
      await result.current.submit();
    });
    expect(vi.mocked(api.createCharacter)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        voiceSamples: [{ situation: "cornered", sample: "Back off. Now." }],
      }),
    );
  });

  it("re-hydrates saved voice samples when the character editor opens", async () => {
    vi.mocked(api.listCharacters).mockResolvedValueOnce([
      { ...SEED_CHARACTERS[0], voiceSamples: [{ situation: "questioned", sample: "Ask again." }] },
    ]);
    const { result } = await mountReady();
    const someId = result.current.characters[0].id;
    act(() => result.current.editCharacter(someId));
    await waitFor(() => expect(result.current.draft._voiceSamples?.length).toBe(1));
    expect(result.current.draft._voiceSamples?.[0]).toMatchObject({
      situation: "questioned",
      sample: "Ask again.",
    });
  });

  it("persists attached context files scoped to the character on save", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("name", "Maerin"));
    act(() =>
      result.current.setDraft("_docFiles", [{ name: "notes.md", text: "secret tunnels", useRag: true }]),
    );
    await act(async () => {
      await result.current.submit();
    });
    expect(vi.mocked(api.bulkCreateContextDocuments)).toHaveBeenCalledWith(
      result.current.activeStorylineId,
      [expect.objectContaining({ name: "notes.md", entityType: "character", category: "character" })],
    );
  });

  it("re-hydrates a character's saved context files when its editor opens", async () => {
    const { result } = await mountReady();
    const someId = result.current.characters[0].id;
    vi.mocked(api.listContextDocuments).mockResolvedValueOnce([
      {
        id: "cd1", storylineId: "x", name: "notes.md", content: "secret tunnels",
        category: "character", includeDraft: false, includeRag: true, includeExtract: false,
        source: "upload", charCount: 13, entityType: "character", entityId: someId,
      },
    ]);
    act(() => result.current.editCharacter(someId));
    await waitFor(() => expect(result.current.draft._docFiles?.length).toBe(1));
    expect(result.current.draft._docFiles?.[0]).toMatchObject({
      id: "cd1", name: "notes.md", text: "secret tunnels",
    });
  });
});

describe("useLibraryState — per-character stat values", () => {
  async function mountReady() {
    const hook = renderHook(() => useLibraryState());
    await waitFor(() => expect(hook.result.current.activeStorylineId).toBeTruthy());
    return hook;
  }

  it("loads each character's persisted stat values keyed by id", async () => {
    vi.mocked(api.getCharacterStats).mockReset();
    vi.mocked(api.getCharacterStats).mockImplementation(async (id: string): Promise<Record<string, number>> =>
      id === SEED_CHARACTERS[0].id ? { health: 80, trust: 3 } : {},
    );
    const { result } = await mountReady();
    await waitFor(() =>
      expect(result.current.statsByCharId[SEED_CHARACTERS[0].id]).toEqual({ health: 80, trust: 3 }),
    );
  });

  it("degrades to an empty entry for a character whose stats fetch fails", async () => {
    vi.mocked(api.getCharacterStats).mockReset();
    vi.mocked(api.getCharacterStats).mockRejectedValue(new Error("network"));
    const { result } = await mountReady();
    await waitFor(() => expect(result.current.characters.length).toBeGreaterThan(0));
    await waitFor(() =>
      expect(result.current.statsByCharId[result.current.characters[0].id]).toEqual({}),
    );
  });

  it("refreshes statsByCharId after a new character is saved with starting stats", async () => {
    vi.mocked(api.getCharacterStats).mockReset();
    vi.mocked(api.getCharacterStats).mockResolvedValue({});
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("name", "Grimm"));
    await act(async () => {
      await result.current.proposeStartingStats();
    });
    vi.mocked(api.getCharacterStats).mockResolvedValue({ health: 90, trust: 1 });
    await act(async () => {
      await result.current.submit();
    });
    const newId = result.current.characters[result.current.characters.length - 1].id;
    await waitFor(() =>
      expect(result.current.statsByCharId[newId]).toEqual({ health: 90, trust: 1 }),
    );
  });
});
