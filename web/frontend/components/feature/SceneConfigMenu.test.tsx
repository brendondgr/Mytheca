import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneConfigMenu } from "./SceneConfigMenu";
import { estimateBeatsTokens } from "@/lib/contextBudget";

function setup(overrides = {}) {
  const props = {
    maxTurns: 5,
    onMaxTurnsChange: vi.fn(),
    suggestionsCount: 4,
    onSuggestionsCountChange: vi.fn(),
    contextBeats: 14,
    onContextBeatsChange: vi.fn(),
    ...overrides,
  };
  render(<SceneConfigMenu {...props} />);
  return props;
}

describe("SceneConfigMenu", () => {
  it("keeps the controls in a popover, closed until the button is clicked", async () => {
    const user = userEvent.setup();
    setup();
    // Closed by default — no controls in the DOM.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /max turns/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("dialog", { name: /scene configuration/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /max turns/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /suggestions/i })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: /number of beats/i })).toBeInTheDocument();
  });

  it("fires the change handlers for turns, suggestions, and beats", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));

    await user.selectOptions(screen.getByRole("combobox", { name: /max turns/i }), "3");
    await user.selectOptions(screen.getByRole("combobox", { name: /suggestions/i }), "0");
    expect(props.onMaxTurnsChange).toHaveBeenCalledWith(3);
    expect(props.onSuggestionsCountChange).toHaveBeenCalledWith(0);

    // The beats slider ranges 5–100 and reports a numeric value.
    const slider = screen.getByRole("slider", { name: /number of beats/i });
    expect(slider).toHaveAttribute("min", "5");
    expect(slider).toHaveAttribute("max", "100");
    fireEvent.change(slider, { target: { value: "50" } });
    expect(props.onContextBeatsChange).toHaveBeenCalledWith(50);
  });

  it("shows a live token estimate for the selected beats", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <SceneConfigMenu contextBeats={14} onContextBeatsChange={() => {}} />,
    );
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(
      screen.getByText(new RegExp(`${estimateBeatsTokens(14).toLocaleString()} tokens`)),
    ).toBeInTheDocument();
    // The estimate tracks the selected depth (a higher beat count → more tokens).
    rerender(<SceneConfigMenu contextBeats={100} onContextBeatsChange={() => {}} />);
    expect(
      screen.getByText(new RegExp(`${estimateBeatsTokens(100).toLocaleString()} tokens`)),
    ).toBeInTheDocument();
    expect(estimateBeatsTokens(100)).toBeGreaterThan(estimateBeatsTokens(14));
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
