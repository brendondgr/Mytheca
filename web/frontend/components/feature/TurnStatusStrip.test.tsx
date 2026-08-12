import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TurnStatusStrip } from "./TurnStatusStrip";
import type { TurnStatus } from "@/features/story-player/turn-stream";
import type { Character } from "@/lib/types";

const mei: Character = {
  id: "mei", name: "Mei", role: "Smuggler", color: "#8E2B1C", mono: "ME",
  traits: "", speech: "", goal: "", secret: "",
};
const charById = (id: string) => (id === mei.id ? mei : undefined);

function renderStrip(status: TurnStatus, streaming = true) {
  return render(
    <TurnStatusStrip status={status} streaming={streaming} charById={charById} />,
  );
}

describe("TurnStatusStrip", () => {
  it("renders nothing when no turn is in flight", () => {
    const { container } = renderStrip({ phase: "thinking", characterId: "mei" }, false);
    expect(container).toBeEmptyDOMElement();
  });

  it("names who is about to speak, with dots", () => {
    renderStrip({ phase: "thinking", characterId: "mei" });
    expect(screen.getByText("Mei is about to speak")).toBeInTheDocument();
    expect(screen.getByTestId("typing-dots")).toBeInTheDocument();
  });

  it("says who is speaking and who is acting", () => {
    const { rerender } = renderStrip({ phase: "speaking", characterId: "mei" });
    expect(screen.getByText("Mei is speaking")).toBeInTheDocument();
    rerender(
      <TurnStatusStrip
        status={{ phase: "acting", characterId: "mei" }}
        streaming
        charById={charById}
      />,
    );
    expect(screen.getByText("Mei is acting")).toBeInTheDocument();
  });

  it("falls back to the name the speaker trace carried when the cast lookup misses", () => {
    renderStrip({ phase: "thinking", characterId: "ghost", name: "Kira" });
    expect(screen.getByText("Kira is about to speak")).toBeInTheDocument();
  });

  it("falls back to a neutral stand-in when neither is available", () => {
    renderStrip({ phase: "speaking", characterId: "ghost" });
    expect(screen.getByText("Someone is speaking")).toBeInTheDocument();
  });

  it("names the narrator without attaching a character avatar", () => {
    const { container } = renderStrip({ phase: "narrating" });
    expect(screen.getByText("The narrator is setting the scene")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("drops the dots once the turn is ending — nothing more is coming", () => {
    renderStrip({ phase: "ending" });
    expect(screen.getByText("The turn is ending")).toBeInTheDocument();
    expect(screen.queryByTestId("typing-dots")).toBeNull();
  });

  it("shows a neutral line between beats rather than blinking out", () => {
    // `idle` can occur mid-turn (a line finished, the next speaker is not chosen yet).
    // A strip that disappears on every beat boundary reads as a glitch.
    renderStrip({ phase: "idle" });
    expect(screen.getByText("The scene is unfolding")).toBeInTheDocument();
  });

  it("announces politely, and keeps the decorative parts out of the announcement", () => {
    renderStrip({ phase: "thinking", characterId: "mei" });
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent("Mei is about to speak");
    expect(screen.getByTestId("typing-dots")).toHaveAttribute("aria-hidden", "true");
  });
});
