import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneConfigMenu } from "./SceneConfigMenu";
import { beatsTokensFromTexts, estimateBeatsTokens } from "@/lib/contextBudget";

function setup(overrides = {}) {
  const props = {
    maxTurns: 5,
    onMaxTurnsChange: vi.fn(),
    suggestionsCount: 4,
    onSuggestionsCountChange: vi.fn(),
    contextBeats: 14,
    onContextBeatsChange: vi.fn(),
    beatLength: "medium" as const,
    onBeatLengthChange: vi.fn(),
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
    expect(screen.getByRole("combobox", { name: /beat length/i })).toBeInTheDocument();
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

  it("computes the beats readout from the real transcript when beatTexts is given", async () => {
    const user = userEvent.setup();
    // Long, real beats → far more tokens than the flat 180-char average would guess.
    const beatTexts = Array.from({ length: 6 }, (_, i) => `Beat ${i}: ` + "word ".repeat(60));
    render(
      <SceneConfigMenu contextBeats={4} onContextBeatsChange={() => {}} beatTexts={beatTexts} />,
    );
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    const expected = beatsTokensFromTexts(beatTexts, 4);
    expect(
      screen.getByText(new RegExp(`${expected.toLocaleString()} tokens \\(recent beats\\)`)),
    ).toBeInTheDocument();
    // The content-real count differs from the flat-average estimate for the same depth.
    expect(expected).not.toBe(estimateBeatsTokens(4));
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

describe("SceneConfigMenu / beat length", () => {
  it("offers the three tiers, showing the paragraph counts that are the contract", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));

    const select = screen.getByRole("combobox", { name: /beat length/i });
    expect(select).toHaveValue("medium");
    // The counts are shown because they ARE the setting — "Short" alone tells the reader
    // nothing about what they are choosing.
    expect(screen.getByRole("option", { name: /short/i })).toHaveTextContent("1–2");
    expect(screen.getByRole("option", { name: /medium/i })).toHaveTextContent("2–4");
    expect(screen.getByRole("option", { name: /long/i })).toHaveTextContent("5–6");
  });

  it("fires the change handler with the tier, not with NaN", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));

    await user.selectOptions(screen.getByRole("combobox", { name: /beat length/i }), "long");
    expect(props.onBeatLengthChange).toHaveBeenCalledWith("long");
  });

  it("defaults to medium when the scenario has never set one", async () => {
    const user = userEvent.setup();
    render(<SceneConfigMenu onBeatLengthChange={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("combobox", { name: /beat length/i })).toHaveValue("medium");
  });

  it("is disabled when no handler is supplied, like its neighbours", async () => {
    const user = userEvent.setup();
    render(<SceneConfigMenu />);
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("combobox", { name: /beat length/i })).toBeDisabled();
  });
});
