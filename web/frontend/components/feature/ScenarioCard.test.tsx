import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ScenarioCard } from "./ScenarioCard";
import type { Character, ResolvedScenario } from "@/lib/types";

const ravi: Character = {
  id: "c1",
  name: "Ravi",
  role: "Dockhand",
  color: "#2F7D6B",
  mono: "R",
  traits: "Wry",
  speech: "",
  goal: "",
  secret: "",
  portrait: null,
};

const base: ResolvedScenario = {
  id: "sc1",
  title: "The Salt Ledger",
  genre: "Intrigue",
  tone: "Tension · rising",
  goal: "Keep the ledger safe.",
  castIds: ["c1"],
  settingId: "s1",
  opening: "Lamplight gutters over the wet dock.",
  branches: [],
  image: null,
  cast: [ravi],
  setting: { id: "s1", name: "The Harbor", type: "Social Hub", desc: "Lamplit." },
};

describe("ScenarioCard", () => {
  it("renders without a scene-art banner when image is null", () => {
    render(<ScenarioCard scenario={base} featured={false} onSelect={vi.fn()} />);
    expect(screen.queryByAltText(/scene art for/i)).toBeNull();
  });

  it("renders a full-bleed scene-art image when image is set", () => {
    const scenario = { ...base, image: "/media/scenes/harbor.webp" };
    render(<ScenarioCard scenario={scenario} featured={false} onSelect={vi.fn()} />);
    const img = screen.getByAltText("Scene art for The Salt Ledger");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", expect.stringContaining("harbor.webp"));
    // Fills the card rather than sitting as a fixed-height banner.
    expect(img).toHaveClass("object-cover");
    expect(img.className).toMatch(/inset-0/);
  });

  it("renders title, genre · tone, goal, and setting name", () => {
    render(<ScenarioCard scenario={base} featured={false} onSelect={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "The Salt Ledger" })).toBeInTheDocument();
    expect(screen.getByText(/Intrigue · Tension · rising/)).toBeInTheDocument();
    expect(screen.getByText("Keep the ledger safe.")).toBeInTheDocument();
    expect(screen.getByText(/The Harbor/)).toBeInTheDocument();
  });

  it("says it is featured through aria-pressed rather than a Recent badge", () => {
    // The badge is gone. It measured 91px beside the edit pencil, which is why the title
    // needed a 92px reserve to clear it — a fifth of the card's width at 390px, spent
    // saying what the 2px accent border and accent shadow already say. `aria-pressed` is
    // where a screen reader looks for this anyway, and it was already there.
    const { rerender } = render(
      <ScenarioCard scenario={base} featured={false} onSelect={vi.fn()} />,
    );
    expect(screen.queryByText(/^recent$/i)).toBeNull();
    expect(
      screen.getByRole("button", { name: /feature scenario/i }),
    ).toHaveAttribute("aria-pressed", "false");

    rerender(<ScenarioCard scenario={base} featured onSelect={vi.fn()} />);
    expect(screen.queryByText(/^recent$/i)).toBeNull();
    expect(
      screen.getByRole("button", { name: /feature scenario/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("features the scenario when the card is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ScenarioCard scenario={base} featured={false} onSelect={onSelect} />);
    await user.click(screen.getByRole("button", { name: /feature scenario the salt ledger/i }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("opens a cast member's profile without triggering select", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onProfile = vi.fn();
    render(
      <ScenarioCard scenario={base} featured={false} onSelect={onSelect} onProfile={onProfile} />,
    );
    await user.click(screen.getByRole("button", { name: "View Ravi" }));
    expect(onProfile).toHaveBeenCalledWith("c1");
    expect(onSelect).not.toHaveBeenCalled();
  });
});
