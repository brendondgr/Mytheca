import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DirectionChecklist } from "./DirectionChecklist";
import { NO_DIRECTION } from "@/features/story-player/turn-stream";

describe("DirectionChecklist", () => {
  it("renders nothing when the player is not directing the scene", () => {
    const { container } = render(<DirectionChecklist progress={NO_DIRECTION} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows each outcome the turn owes, and which have landed", () => {
    render(
      <DirectionChecklist
        progress={{
          items: [
            { text: "Beth confronts Mei", delivered: true, by: "beth" },
            { text: "Mei admits the letter", delivered: false },
          ],
          undelivered: [],
        }}
      />,
    );
    expect(screen.getByText("Beth confronts Mei")).toBeInTheDocument();
    expect(screen.getByText("Mei admits the letter")).toBeInTheDocument();
    expect(screen.getByText("1/2 delivered")).toBeInTheDocument();
  });

  it("names what the scene's beat budget could not fit", () => {
    // Previously discoverable only by noticing something never happened.
    render(
      <DirectionChecklist
        progress={{
          items: [{ text: "Kira storms out", delivered: false }],
          undelivered: ["Kira storms out"],
        }}
      />,
    );
    expect(screen.getByText(/did not fit this scene/i)).toBeInTheDocument();
    expect(screen.getByText(/raise the scene's turn limit/i)).toBeInTheDocument();
  });

  it("announces overall progress once, not item by item", () => {
    // Announcing each item as it lands would talk over the prose the transcript reads.
    render(
      <DirectionChecklist
        progress={{
          items: [
            { text: "A", delivered: true },
            { text: "B", delivered: false },
          ],
          undelivered: [],
        }}
      />,
    );
    const live = screen.getByText("1 of 2 delivered");
    expect(live).toHaveAttribute("aria-live", "polite");
  });
});
