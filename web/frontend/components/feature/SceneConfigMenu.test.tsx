import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneConfigMenu } from "./SceneConfigMenu";

function setup(overrides = {}) {
  const props = {
    maxTurns: 5,
    onMaxTurnsChange: vi.fn(),
    suggestionsCount: 4,
    onSuggestionsCountChange: vi.fn(),
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
    expect(screen.queryByRole("combobox", { name: /how many beats one message produces/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("dialog", { name: /scene configuration/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /how many beats one message produces/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /follow-up ideas/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /how much a character says/i })).toBeInTheDocument();
  });

  it("fires the change handlers for turns and suggestions", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));

    await user.selectOptions(screen.getByRole("combobox", { name: /how many beats one message produces/i }), "3");
    await user.selectOptions(screen.getByRole("combobox", { name: /follow-up ideas/i }), "0");
    expect(props.onMaxTurnsChange).toHaveBeenCalledWith(3);
    expect(props.onSuggestionsCountChange).toHaveBeenCalledWith(0);
  });

  it("no longer offers a beats slider — the window fits itself", async () => {
    // "Number of beats" asked the player to pick a context-window depth, which is a question
    // only the app can answer: the right depth is whatever the model can hold, and the app
    // knows the model's window while the player does not. Deleted, not hidden — what the
    // scene actually reached is reported in the Inspector instead of configured here.
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.queryByRole("slider", { name: /number of beats/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/number of beats/i)).not.toBeInTheDocument();
  });

  it("keeps the three controls that are genuinely the player's to choose", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("combobox", { name: /how many beats one message produces/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /follow-up ideas/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /how much a character says/i })).toBeInTheDocument();
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

    const select = screen.getByRole("combobox", { name: /how much a character says/i });
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

    await user.selectOptions(screen.getByRole("combobox", { name: /how much a character says/i }), "long");
    expect(props.onBeatLengthChange).toHaveBeenCalledWith("long");
  });

  it("defaults to medium when the scenario has never set one", async () => {
    const user = userEvent.setup();
    render(<SceneConfigMenu onBeatLengthChange={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("combobox", { name: /how much a character says/i })).toHaveValue("medium");
  });

  it("is disabled when no handler is supplied, like its neighbours", async () => {
    const user = userEvent.setup();
    render(<SceneConfigMenu />);
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("combobox", { name: /how much a character says/i })).toBeDisabled();
  });
});

describe("SceneConfigMenu says what each control does", () => {
  it("gives every control an accessible description of its effect", async () => {
    // The review's finding was that nothing tells a new player what any of this is. The
    // cheapest 80% of that fix is copy attached to the controls they can already see.
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    for (const name of [
      /how many beats one message produces/i,
      /follow-up ideas offered after each turn/i,
      /how much a character says at once/i,
    ]) {
      expect(screen.getByRole("combobox", { name })).toHaveAccessibleDescription(/\w/);
    }
  });

  it("names each control by its consequence, not by its implementation", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    // The old names described the machine ("Max turns", "Beat length"); these describe what
    // the player gets.
    expect(screen.queryByRole("combobox", { name: "Max turns" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Beat length" })).not.toBeInTheDocument();
  });

  it("reports what the scene remembers instead of asking for it", async () => {
    const user = userEvent.setup();
    render(
      <SceneConfigMenu
        maxTurns={5}
        onMaxTurnsChange={() => {}}
        sceneMemory={{
          windowBeats: 40,
          windowSource: "detected",
          droppedBeats: 12,
          budgetTokens: 8000,
        }}
      />,
    );
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    const row = screen.getByRole("region", { name: /what the scene remembers/i });
    expect(row).toHaveTextContent(/last 40 beats, word for word/i);
    expect(row).toHaveTextContent(/8,000 tokens/);
    expect(row).toHaveTextContent(/12 older beats have dropped out/i);
  });

  it("says the older beats are kept when compaction is on", async () => {
    const user = userEvent.setup();
    render(
      <SceneConfigMenu
        maxTurns={5}
        onMaxTurnsChange={() => {}}
        summarised
        sceneMemory={{
          windowBeats: 40,
          windowSource: "detected",
          droppedBeats: 12,
          budgetTokens: 8000,
        }}
      />,
    );
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(
      screen.getByRole("region", { name: /what the scene remembers/i }),
    ).toHaveTextContent(/kept as a summary/i);
  });

  it("says so honestly before a turn has run", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(
      screen.getByRole("region", { name: /what the scene remembers/i }),
    ).toHaveTextContent(/once the scene starts/i);
  });

  it("omits the per-beat cost until a turn has actually been timed", async () => {
    // A number invented in the UI would be wrong for every operator's hardware.
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(
      screen.getByRole("combobox", { name: /how many beats one message produces/i }),
    ).not.toHaveAccessibleDescription(/per extra beat/i);
  });
});

