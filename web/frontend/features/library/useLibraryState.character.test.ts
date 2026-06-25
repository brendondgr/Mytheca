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

  it("drafts a full character into the draft and flags it AI-drafted", async () => {
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
});
