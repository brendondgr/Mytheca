import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useSceneData } from "./useSceneData";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("useSceneData", () => {
  it("resolves a scenario's cast + setting from the backend", async () => {
    const { result } = renderHook(() => useSceneData("embergate", "embergate"));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    if (result.current.status !== "ready") throw new Error("not ready");
    expect(result.current.scenario.id).toBe("embergate");
    expect(result.current.scenario.title).toBe("The Embergate Conspiracy");
    // Cast resolved from castIds → real characters.
    expect(result.current.scenario.cast.length).toBeGreaterThan(0);
    expect(result.current.scenario.setting.name).toBe("The Saltworn Tavern");
    expect(result.current.storylineName).toBe("Embergate");
  });

  it("errors when the scenario is in neither the backend nor the seed", async () => {
    const { result } = renderHook(() => useSceneData("embergate", "nope-xyz"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    if (result.current.status !== "error") throw new Error("expected error");
    expect(result.current.message).toMatch(/not found/i);
  });
});
