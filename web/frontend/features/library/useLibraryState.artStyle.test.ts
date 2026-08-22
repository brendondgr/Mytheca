import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useLibraryState } from "./useLibraryState";
import * as api from "@/lib/api";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

/**
 * The art style reaches every authoring surface, not just characters.
 *
 * Six calls carry it — a prompt-write and a render for each of characters, places and
 * scenarios — and both halves must agree: prompts *written* for one look and *painted* in
 * another produce a muddle nobody asked for.
 */
describe("useLibraryState — art style", () => {
  async function mountReady() {
    const hook = renderHook(() => useLibraryState());
    await waitFor(() => expect(hook.result.current.activeStorylineId).toBeTruthy());
    return hook;
  }

  it("defaults to null, meaning the operator's Options default", async () => {
    const { result } = await mountReady();
    expect(result.current.artStyle).toBeNull();
  });

  it("omits the style entirely when the author has not chosen one", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("appearance", "a wiry smuggler"));
    await act(async () => {
      await result.current.generatePortraitPrompts();
    });
    expect(vi.mocked(api.generatePortraitPrompts)).toHaveBeenCalledWith(
      expect.objectContaining({ artStyle: undefined }),
    );
  });

  it("sends the chosen style on both the character prompt-write and the render", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setDraft("appearance", "a wiry smuggler"));
    act(() => result.current.setArtStyle("anime"));

    await act(async () => {
      await result.current.generatePortraitPrompts();
    });
    act(() => result.current.setDraft("_portraitPositive", "a wiry smuggler"));
    await act(async () => {
      await result.current.generatePortrait();
    });

    expect(vi.mocked(api.generatePortraitPrompts)).toHaveBeenCalledWith(
      expect.objectContaining({ artStyle: "anime" }),
    );
    expect(vi.mocked(api.generatePortrait)).toHaveBeenCalledWith(
      expect.objectContaining({ artStyle: "anime" }),
    );
  });

  it("sends the chosen style on both halves of a setting's scene art", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("setting"));
    act(() => result.current.setDraft("atmosphere", "fog and brine"));
    act(() => result.current.setArtStyle("photoreal"));

    await act(async () => {
      await result.current.generateSceneArtPrompts();
    });
    act(() => result.current.setDraft("_sceneArtPositive", "a fog-bound harbor"));
    await act(async () => {
      await result.current.generateSceneArt();
    });

    expect(vi.mocked(api.generateSceneArtPrompts)).toHaveBeenCalledWith(
      expect.objectContaining({ artStyle: "photoreal" }),
    );
    expect(vi.mocked(api.generateSceneArt)).toHaveBeenCalledWith(
      expect.objectContaining({ artStyle: "photoreal" }),
    );
  });

  it("sends the chosen style on both halves of a scenario's scene art", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("scenario"));
    act(() => result.current.setDraft("tone", "tense"));
    act(() => result.current.setArtStyle("anime"));

    await act(async () => {
      await result.current.generateScenarioSceneArtPrompts();
    });
    act(() => result.current.setDraft("_sceneArtPositive", "a candlelit hall"));
    await act(async () => {
      await result.current.generateScenarioSceneArt();
    });

    expect(vi.mocked(api.generateScenarioSceneArtPrompts)).toHaveBeenCalledWith(
      expect.objectContaining({ artStyle: "anime" }),
    );
    expect(vi.mocked(api.generateScenarioSceneArt)).toHaveBeenCalledWith(
      expect.objectContaining({ artStyle: "anime" }),
    );
  });

  it("forgets the choice when a new editor opens", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("character"));
    act(() => result.current.setArtStyle("anime"));
    act(() => result.current.openCreate("setting"));
    // A per-entity choice, not a sticky mode: the next thing you author starts from the
    // operator's default rather than inheriting whatever the last one happened to use.
    expect(result.current.artStyle).toBeNull();
  });
});
