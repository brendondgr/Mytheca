import { describe, it, expect, vi } from "vitest";

const { redirect } = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`REDIRECT:${url}`);
  }),
}));
vi.mock("next/navigation", () => ({ redirect }));

import LegacyPlayRedirect from "./page";

describe("legacy /play/{scenarioId} redirect", () => {
  it("redirects to /{storylineId}/{scenarioId} for a known scenario", async () => {
    await expect(
      LegacyPlayRedirect({ params: Promise.resolve({ scenarioId: "embergate" }) }),
    ).rejects.toThrow("REDIRECT:/embergate/embergate");
  });

  it("falls back to the first storyline + scenario for an unknown id", async () => {
    await expect(
      LegacyPlayRedirect({ params: Promise.resolve({ scenarioId: "ghost" }) }),
    ).rejects.toThrow("REDIRECT:/embergate/embergate");
  });
});
