import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useLibraryState } from "./useLibraryState";
import * as api from "@/lib/api";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

/** Drive the hook's scenario-authoring handler directly (no UI). */
describe("useLibraryState — scenario authoring", () => {
  beforeEach(() => vi.clearAllMocks());


  async function mountReady() {
    const hook = renderHook(() => useLibraryState());
    await waitFor(() => expect(hook.result.current.activeStorylineId).toBeTruthy());
    return hook;
  }

  it("drafts a scenario and merges the roster-resolved cast + setting into the draft", async () => {
    const { result } = await mountReady();

    act(() => result.current.openCreate("scenario"));
    act(() => result.current.setDraft("_prompt", "A tense midnight negotiation."));
    await act(async () => {
      await result.current.draftScenario();
    });

    expect(vi.mocked(api.draftScenario)).toHaveBeenCalled();
    expect(result.current.draft.title).toBe("Drafted Scene");
    expect(result.current.draft.genre).toBe("Intrigue");
    expect(result.current.draft.opening).toBe("A drafted opening beat.");
    // Cast + setting come straight from the backend (real world members).
    expect(result.current.draft.cast).toEqual(["c-maerin", "c-doran"]);
    expect(result.current.draft.settingId).toBe("s-harbor");
    expect(result.current.draft._ai).toBe(true);
  });

  it("does nothing without a seed prompt", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreate("scenario"));
    await act(async () => {
      await result.current.draftScenario();
    });
    expect(vi.mocked(api.draftScenario)).not.toHaveBeenCalled();
  });

  it("surfaces an error when the draft call fails", async () => {
    vi.mocked(api.draftScenario).mockRejectedValueOnce(new Error("LLM unavailable"));
    const { result } = await mountReady();

    act(() => result.current.openCreate("scenario"));
    act(() => result.current.setDraft("_prompt", "A heist gone wrong."));
    await act(async () => {
      await result.current.draftScenario();
    });

    expect(result.current.error).toBe("LLM unavailable");
    expect(result.current.generating).toBe(false);
  });

  // ---- delete, from the card's trash square (no editor open) ----

  it("asking to delete resolves the scenario but calls nothing until confirmed", async () => {
    const { result } = await mountReady();
    const id = result.current.resolvedScenarios[0].id;

    act(() => result.current.requestDeleteScenario(id));
    expect(result.current.scenarioToDelete?.id).toBe(id);
    expect(vi.mocked(api.deleteScenario)).not.toHaveBeenCalled();

    act(() => result.current.cancelDeleteScenario());
    expect(result.current.scenarioToDelete).toBeNull();
    expect(vi.mocked(api.deleteScenario)).not.toHaveBeenCalled();
  });

  it("confirming deletes it, drops it from the list, and refeatures another scene", async () => {
    const { result } = await mountReady();
    const before = result.current.scenarios.map((s) => s.id);
    const id = result.current.featuredId;

    act(() => result.current.requestDeleteScenario(id));
    await act(async () => {
      await result.current.confirmDeleteScenario();
    });

    expect(vi.mocked(api.deleteScenario)).toHaveBeenCalledWith(id);
    expect(result.current.scenarios.map((s) => s.id)).toEqual(before.filter((x) => x !== id));
    expect(result.current.scenarioToDelete).toBeNull();
    expect(result.current.featuredId).not.toBe(id);
  });

  it("keeps the confirm open on failure so the delete can be retried", async () => {
    vi.mocked(api.deleteScenario).mockRejectedValueOnce(new Error("Scene is locked"));
    const { result } = await mountReady();
    const id = result.current.resolvedScenarios[0].id;

    act(() => result.current.requestDeleteScenario(id));
    await act(async () => {
      await result.current.confirmDeleteScenario();
    });

    expect(result.current.error).toBe("Scene is locked");
    expect(result.current.scenarioToDelete?.id).toBe(id);
    expect(result.current.scenarios.some((s) => s.id === id)).toBe(true);
  });

});
