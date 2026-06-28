import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ScenarioCard } from "./ScenarioCard";
import type { ResolvedScenario } from "@/lib/types";

const base: ResolvedScenario = {
  id: "sc1",
  title: "The Salt Ledger",
  genre: "Intrigue",
  tone: "Tension · rising",
  goal: "Keep the ledger safe.",
  castIds: [],
  settingId: "s1",
  opening: "Lamplight gutters over the wet dock.",
  branches: [],
  image: null,
  cast: [],
  setting: { id: "s1", name: "The Harbor", type: "Social Hub", desc: "Lamplit." },
};

describe("ScenarioCard", () => {
  it("renders without a scene-art banner when image is null", () => {
    render(<ScenarioCard scenario={base} featured={false} onSelect={vi.fn()} />);
    expect(screen.queryByAltText(/scene art for/i)).toBeNull();
  });

  it("renders the scene-art banner when image is set", () => {
    const scenario = { ...base, image: "/media/scenes/harbor.webp" };
    render(<ScenarioCard scenario={scenario} featured={false} onSelect={vi.fn()} />);
    const img = screen.getByAltText("Scene art for The Salt Ledger");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", expect.stringContaining("harbor.webp"));
  });
});
