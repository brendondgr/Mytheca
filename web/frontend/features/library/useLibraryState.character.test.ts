import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useLibraryState } from "./useLibraryState";
import * as api from "@/lib/api";

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
        category: "character", includeDraft: false, includeRag: true, source: "upload",
        charCount: 13, entityType: "character", entityId: someId,
      },
    ]);
    act(() => result.current.editCharacter(someId));
    await waitFor(() => expect(result.current.draft._docFiles?.length).toBe(1));
    expect(result.current.draft._docFiles?.[0]).toMatchObject({
      id: "cd1", name: "notes.md", text: "secret tunnels",
    });
  });
});
