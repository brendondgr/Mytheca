import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Character } from "@/lib/types";
import type { SceneMessage } from "@/features/story-player/scene-data";
import { TranscriptBeat } from "./TranscriptBeat";

const MEI: Character = {
  id: "mei",
  name: "Mei",
  role: "Broker",
  color: "#8E2B1C",
  mono: "M",
  traits: "",
  speech: "",
} as Character;

function renderBeat(message: SceneMessage) {
  return render(
    <TranscriptBeat
      message={message}
      charById={(id) => (id === "mei" ? MEI : undefined)}
      onProfile={vi.fn()}
      choices={[]}
      onChoose={vi.fn()}
    />,
  );
}

describe("TranscriptBeat", () => {
  it("renders narrator prose upright (no italic — feedback #6)", () => {
    renderBeat({ kind: "narrator", text: "Rain ticks against the shutters." });
    const prose = screen.getByText("Rain ticks against the shutters.");
    expect(prose.className).not.toContain("italic");
  });

  it("renders a character's action label upright (no italic — feedback #6)", () => {
    renderBeat({ kind: "char", who: "mei", action: "leans in, low", text: "Careful." });
    const label = screen.getByText("leans in, low");
    expect(label.className).not.toContain("italic");
  });

  it("renders an internal thought as a distinct, keyboard-reachable thought bubble", () => {
    renderBeat({ kind: "thought", who: "mei", text: "Coin first, favor later." });
    // The private thought text and a "thinking" tag both show …
    expect(screen.getByText("Coin first, favor later.")).toBeTruthy();
    expect(screen.getByText("thinking")).toBeTruthy();
    // … attributed to a named, focusable character button (profile affordance).
    expect(screen.getByRole("button", { name: "Mei" })).toBeTruthy();
  });

  it("routes speech and thought to different renderers for the same speaker", () => {
    const { rerender } = renderBeat({ kind: "char", who: "mei", text: "Fine." });
    expect(screen.queryByText("thinking")).toBeNull(); // speech has no thinking tag
    rerender(
      <TranscriptBeat
        message={{ kind: "thought", who: "mei", text: "He'll fold." }}
        charById={(id) => (id === "mei" ? MEI : undefined)}
        onProfile={vi.fn()}
        choices={[]}
        onChoose={vi.fn()}
      />,
    );
    expect(screen.getByText("thinking")).toBeTruthy();
  });
});
