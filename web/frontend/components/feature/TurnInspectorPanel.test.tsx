import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { TurnInspectorPanel } from "./TurnInspectorPanel";
import type { TraceTurn } from "@/features/story-player/turn-stream";

function turn(): TraceTurn {
  return {
    id: "0",
    label: "I slide the coin pouch over.",
    steps: [
      { type: "trace", n: 1, step: "turn", title: "You submitted a message", detail: "I slide the coin pouch over.", data: {} },
      { type: "trace", n: 2, step: "director", title: "The Director chose 1 speaker(s)", detail: "You addressed Mei directly, so only they respond.", data: {} },
      { type: "trace", n: 3, step: "thinking", title: "Mei thinks (private)", detail: "Coin first, favor later.", data: {} },
      { type: "trace", n: 4, step: "dialogue", title: "Mei speaks", detail: '"Coin is easy."', data: {} },
    ],
  };
}

describe("TurnInspectorPanel", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <TurnInspectorPanel open={false} onClose={() => {}} turns={[turn()]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the empty-state hint when there are no turns yet", () => {
    render(<TurnInspectorPanel open onClose={() => {}} turns={[]} />);
    expect(screen.getByText(/Send a message in the scene/i)).toBeInTheDocument();
  });

  it("renders the turn's steps in order with the Director rationale and hidden thinking", () => {
    render(<TurnInspectorPanel open onClose={() => {}} turns={[turn()]} />);
    // Docked column (complementary landmark, not a modal dialog) so the chat stays visible.
    expect(screen.getByRole("complementary", { name: /turn inspector/i })).toBeInTheDocument();
    expect(screen.getByText(/You addressed Mei directly/)).toBeInTheDocument();
    expect(screen.getByText("Coin first, favor later.")).toBeInTheDocument(); // surfaced thinking
    expect(screen.getByText('"Coin is easy."')).toBeInTheDocument();
    // The opening "turn" step is not repeated as a row (it labels the group instead).
    expect(screen.queryByText("You submitted a message")).not.toBeInTheDocument();
  });

  it("closes via the close button", async () => {
    const onClose = vi.fn();
    render(<TurnInspectorPanel open onClose={onClose} turns={[turn()]} />);
    await userEvent.click(screen.getByRole("button", { name: /^close$/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
