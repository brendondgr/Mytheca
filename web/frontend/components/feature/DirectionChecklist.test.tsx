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
            { text: "Beth confronts Mei", state: "delivered" as const, by: "beth" },
            { text: "Mei admits the letter", state: "outstanding" as const },
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
          items: [{ text: "Kira storms out", state: "outstanding" as const }],
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
            { text: "A", state: "delivered" as const },
            { text: "B", state: "outstanding" as const },
          ],
          undelivered: [],
        }}
      />,
    );
    const live = screen.getByText("1 of 2 delivered");
    expect(live).toHaveAttribute("aria-live", "polite");
  });
});

describe("DirectionChecklist attempted state", () => {
  it("draws an attempted requirement as neither done nor untouched", () => {
    // A beat was spent on this and the engine could not confirm the prose reached it.
    // Showing it as a tick is the lie the old code told; showing it as untouched would
    // hide that the turn already tried.
    render(
      <DirectionChecklist
        progress={{
          items: [
            { text: "the lamp goes over", state: "attempted" as const },
            { text: "Mei storms out", state: "outstanding" as const },
          ],
          undelivered: [],
        }}
      />,
    );
    // The distinction is carried in words, not colour alone.
    expect(screen.getByText(/the scene may not have reached this/i)).toBeInTheDocument();
    expect(screen.getByText("0/2 delivered")).toBeInTheDocument();
  });

  it("counts attempted separately in the live announcement", () => {
    render(
      <DirectionChecklist
        progress={{
          items: [
            { text: "A", state: "delivered" as const },
            { text: "B", state: "attempted" as const },
          ],
          undelivered: [],
        }}
      />,
    );
    expect(
      screen.getByText(/1 of 2 delivered, 1 attempted but not confirmed/i),
    ).toBeInTheDocument();
  });

  it("does not label an attempted requirement as one that did not fit", () => {
    // `undelivered` now includes everything unconfirmed, so a requirement that WAS tried
    // must not also be blamed on the beat budget — two different failures, two messages.
    render(
      <DirectionChecklist
        progress={{
          items: [{ text: "A", state: "attempted" as const }],
          undelivered: ["A"],
        }}
      />,
    );
    expect(screen.queryByText(/did not fit this scene/i)).not.toBeInTheDocument();
    expect(screen.getByText(/the scene may not have reached this/i)).toBeInTheDocument();
  });
});

