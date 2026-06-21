import { describe, it, expect } from "vitest";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";

describe("resolveScenario", () => {
  it("resolves cast + setting from id references", () => {
    const resolved = resolveScenario(
      SEED_SCENARIOS[0],
      SEED_CHARACTERS,
      SEED_SETTINGS,
    );
    expect(resolved.cast.map((c) => c.id)).toEqual([
      "maerin",
      "aldous",
      "wren",
      "doran",
    ]);
    expect(resolved.setting.name).toBe("The Saltworn Tavern");
  });

  it("drops unknown cast ids and falls back for a missing setting", () => {
    const resolved = resolveScenario(
      { ...SEED_SCENARIOS[0], castIds: ["ghost"], settingId: "nowhere" },
      SEED_CHARACTERS,
      SEED_SETTINGS,
    );
    expect(resolved.cast).toHaveLength(0);
    expect(resolved.setting.name).toBe("—");
  });
});
