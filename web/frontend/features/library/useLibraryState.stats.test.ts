import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { useLibraryState } from "./useLibraryState";
import { blankStat } from "./editor";
import * as api from "@/lib/api";
import type { StatDefinition } from "@/lib/types";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

const HEALTH: StatDefinition = {
  key: "health",
  displayName: "Health",
  description: "Vitality.",
  min: 0,
  max: 100,
  default: 100,
  visibility: "public",
  guidance: null,
  appliesTo: ["character"],
  bands: [{ min: 0, max: 20, label: "Nearly dead" }],
};

describe("useLibraryState — universal stat persistence", () => {
  beforeEach(() => vi.clearAllMocks());

  async function mountReady() {
    const hook = renderHook(() => useLibraryState());
    await waitFor(() => expect(hook.result.current.activeStorylineId).toBeTruthy());
    return hook;
  }

  it("loads a world's stats into the draft when editing", async () => {
    vi.mocked(api.listStatDefinitions).mockResolvedValueOnce([HEALTH]);
    const { result } = await mountReady();
    const id = result.current.activeStorylineId;

    await act(async () => {
      result.current.editStoryline(id);
    });
    await waitFor(() =>
      expect(result.current.draft._stats?.map((s) => s.key)).toEqual(["health"]),
    );
  });

  it("diffs into create / update / delete on save", async () => {
    // Existing world has "health" + "trust"; we edit health, drop trust, add "morale".
    vi.mocked(api.listStatDefinitions).mockResolvedValueOnce([
      HEALTH,
      { ...blankStat(), key: "trust", displayName: "Trust" },
    ]);
    const { result } = await mountReady();
    const id = result.current.activeStorylineId;

    await act(async () => {
      result.current.editStoryline(id);
    });
    await waitFor(() => expect(result.current.draft._stats?.length).toBe(2));

    act(() => {
      const morale = { ...blankStat(), key: "morale", displayName: "Morale" };
      const editedHealth = { ...HEALTH, default: 80 };
      // Keep health (edited), drop trust, add morale.
      result.current.setDraft("_stats", [editedHealth, morale]);
    });

    await act(async () => {
      await result.current.submitStoryline();
    });

    expect(vi.mocked(api.deleteStatDefinition)).toHaveBeenCalledWith(id, "trust");
    expect(vi.mocked(api.updateStatDefinition)).toHaveBeenCalledWith(
      id,
      "health",
      expect.objectContaining({ default: 80 }),
    );
    expect(vi.mocked(api.createStatDefinition)).toHaveBeenCalledWith(
      id,
      expect.objectContaining({ key: "morale", displayName: "Morale" }),
    );
  });

  it("skips blank (unnamed) stat rows", async () => {
    const { result } = await mountReady();
    act(() => result.current.openCreateStoryline());
    act(() => result.current.setDraft("title", "New World"));
    act(() => result.current.setDraft("_stats", [blankStat()])); // empty key+name

    await act(async () => {
      await result.current.submitStoryline();
    });
    expect(vi.mocked(api.createStatDefinition)).not.toHaveBeenCalled();
  });
});
