import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StatsEditor } from "./StatsEditor";
import { blankStat } from "@/features/library/editor";
import { PALETTE } from "@/lib/seed-data";
import type { StatDefinition } from "@/lib/types";

function renderEditor(stats: StatDefinition[], originalKeys: string[] = []) {
  const onChange = vi.fn();
  render(
    <StatsEditor stats={stats} originalKeys={new Set(originalKeys)} onChange={onChange} />,
  );
  return { onChange };
}

describe("StatsEditor", () => {
  it("adds a statistic", () => {
    const { onChange } = renderEditor([]);
    fireEvent.click(screen.getByRole("button", { name: "+ Add statistic" }));
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ key: "", displayName: "" })]);
  });

  it("derives the key from the name for a new stat", () => {
    const { onChange } = renderEditor([blankStat()]);
    fireEvent.change(screen.getByLabelText("Statistic 1 name"), {
      target: { value: "Hit Points" },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ displayName: "Hit Points", key: "hit_points" }),
    ]);
  });

  it("keeps a loaded stat's key immutable when renamed", () => {
    const loaded: StatDefinition = { ...blankStat(), key: "health", displayName: "Health" };
    const { onChange } = renderEditor([loaded], ["health"]);
    fireEvent.change(screen.getByLabelText("Statistic 1 name"), {
      target: { value: "Vitality" },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ displayName: "Vitality", key: "health" }),
    ]);
  });

  it("adds a band ('ticker') seeded to the stat's range with an empty description", () => {
    const stat: StatDefinition = { ...blankStat(), key: "health", displayName: "Health", min: 0, max: 100 };
    const { onChange } = renderEditor([stat]);
    fireEvent.click(screen.getByRole("button", { name: "+ Add band" }));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ bands: [{ min: 0, max: 100, label: "", description: "" }] }),
    ]);
  });

  it("edits a band description (the {Character} field)", () => {
    const stat: StatDefinition = {
      ...blankStat(),
      key: "stamina",
      displayName: "Stamina",
      bands: [{ min: 0, max: 20, label: "Exhausted", description: "" }],
    };
    const { onChange } = renderEditor([stat]);
    fireEvent.change(screen.getByLabelText("Band 1 description"), {
      target: { value: "{Character} is exhausted." },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        bands: [{ min: 0, max: 20, label: "Exhausted", description: "{Character} is exhausted." }],
      }),
    ]);
  });

  it("removes a statistic", () => {
    const stat: StatDefinition = { ...blankStat(), key: "health", displayName: "Health" };
    const { onChange } = renderEditor([stat]);
    fireEvent.click(screen.getByRole("button", { name: "Remove Health" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("offers 12 character accent colors", () => {
    expect(PALETTE).toHaveLength(12);
  });
});
