import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useLibraryState } from "./useLibraryState";
import * as api from "@/lib/api";
import { SEED_SETTINGS } from "@/lib/seed-data";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

/** Drive the hook's setting-authoring handlers directly (no UI). */
describe("useLibraryState — setting authoring", () => {
  async function mountReady() {
    const hook = renderHook(() => useLibraryState());
    await waitFor(() => expect(hook.result.current.activeStorylineId).toBeTruthy());
    return hook;
  }

  it("lights the active field during a setting draft, then clears it", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("setting"));
    act(() => result.current.setDraft("_prompt", "A flooded smugglers' market."));

    let pending: Promise<void>;
    act(() => {
      pending = result.current.draftSetting();
    });
    await waitFor(() => expect(result.current.activeField).not.toBeNull());
    expect(result.current.draftStage).toBe("details");

    await act(async () => {
      await pending!;
    });
    expect(result.current.activeField).toBeNull();
    expect(result.current.draftStage).toBeNull();
    expect(result.current.draft.currentState).toBe("A drafted current state.");
  });

  it("generates scene-art prompts, then renders an image into the draft", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("setting"));
    act(() => result.current.setDraft("name", "The Drowned Market"));

    await act(async () => {
      await result.current.generateSceneArtPrompts();
    });
    expect(result.current.draft._sceneArtPositive).toContain("watercolor");

    await act(async () => {
      await result.current.generateSceneArt();
    });
    expect(vi.mocked(api.generateSceneArt)).toHaveBeenCalledWith(
      expect.objectContaining({ positive: expect.stringContaining("watercolor") }),
    );
    expect(result.current.draft.image).toBe("/media/scenes/test.webp");
  });

  it("persists the scene-art prompts with the setting on save", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("setting"));
    act(() => result.current.setDraft("name", "The Drowned Market"));
    await act(async () => {
      await result.current.generateSceneArtPrompts();
    });
    await act(async () => {
      await result.current.submit();
    });
    // The prompts that produced the image are sent in the create payload.
    expect(vi.mocked(api.createSetting)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        sceneArtPositive: expect.stringContaining("watercolor"),
        sceneArtNegative: expect.any(String),
      }),
    );
  });

  it("re-hydrates saved scene-art prompts when the setting editor opens", async () => {
    vi.mocked(api.listSettings).mockResolvedValueOnce([
      { ...SEED_SETTINGS[0], sceneArtPositive: "saved positive", sceneArtNegative: "saved negative" },
    ]);
    const { result } = await mountReady();
    const someId = result.current.settings[0].id;
    act(() => result.current.editSetting(someId));
    await waitFor(() => expect(result.current.draft._sceneArtPositive).toBe("saved positive"));
    expect(result.current.draft._sceneArtNegative).toBe("saved negative");
  });
});
