import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneConfigMenu } from "./SceneConfigMenu";

function setup(overrides: Record<string, unknown> = {}) {
  const props = {
    suggestionsCount: 4,
    onSuggestionsCountChange: vi.fn(),
    onPinnedChange: vi.fn(),
    onPlannerModeChange: vi.fn(),
    onRegisterChange: vi.fn(),
    onTieScopeChange: vi.fn(),
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
    expect(screen.queryByRole("combobox", { name: /follow-up ideas/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("dialog", { name: /scene configuration/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /follow-up ideas/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /turn planning/i })).toBeInTheDocument();
  });

  it("fires the change handlers for turns and suggestions", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));

    await user.selectOptions(screen.getByRole("combobox", { name: /follow-up ideas/i }), "0");
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

  it("keeps the controls that are genuinely the player's to choose", async () => {
    // Pacing is no longer among them. How many beats a message makes and how long a beat is
    // are the scene's judgement, so what is left here is what a player can answer better
    // than the app can: how many follow-ups they want, whether a director reads each moment,
    // and how much history a character carries.
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("combobox", { name: /follow-up ideas/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /turn planning/i })).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: /how much history a character carries/i }),
    ).toBeInTheDocument();
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

describe("SceneConfigMenu says what each control does", () => {
  it("gives every control an accessible description of its effect", async () => {
    // The review's finding was that nothing tells a new player what any of this is. The
    // cheapest 80% of that fix is copy attached to the controls they can already see.
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    for (const name of [
      /follow-up ideas offered after each turn/i,
      /how much history a character carries/i,
    ]) {
      expect(screen.getByRole("combobox", { name })).toHaveAccessibleDescription(/\w/);
    }
  });

  it("names each control by its consequence, not by its implementation", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    // The old names described the machine ("Max turns", "Beat length"); these describe what
    // the player gets. Both of those controls have since been removed outright — pacing is
    // the scene's judgement now — so this also pins that they did not come back.
    expect(screen.queryByRole("combobox", { name: "Max turns" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Beat length" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: /how many beats one message produces/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: /how much a character says at once/i }),
    ).not.toBeInTheDocument();
  });

  it("reports what the scene remembers instead of asking for it", async () => {
    const user = userEvent.setup();
    render(
      <SceneConfigMenu
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
      screen.getByRole("combobox", { name: /follow-up ideas/i }),
    ).not.toHaveAccessibleDescription(/per extra beat/i);
  });

  describe("pins — per-turn versus permanent", () => {
    const ALL_PINNED = { suggestionsCount: true, planner: true, ties: true };

    async function open(overrides = {}) {
      const user = userEvent.setup();
      const props = setup(overrides);
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      return { user, props };
    }

    it("gives every control a pin whose accessible name states the scope", async () => {
      await open({ pinned: ALL_PINNED });
      for (const name of ["Suggestions", "Turn planning", "Ties"]) {
        const pin = screen.getByRole("button", { name: `${name} — pinned to this scene` });
        expect(pin).toHaveAttribute("aria-pressed", "true");
      }
    });

    it("says 'this turn only' on an unpinned control, in the name and on the row", async () => {
      // Scope is never colour alone: the pin's accessible name carries it for a screen
      // reader, and the caption carries it visibly.
      await open({ pinned: { ...ALL_PINNED, suggestionsCount: false } });
      const pin = screen.getByRole("button", { name: "Suggestions — this turn only" });
      expect(pin).toHaveAttribute("aria-pressed", "false");
      // Scoped to this row: the register row carries a PERMANENT "· this turn" tag, so a
      // bare text query would match two and prove nothing about the pin.
      const row = screen
        .getByRole("combobox", { name: /follow-up ideas/i })
        .closest("div");
      expect(row).toHaveTextContent(/· this turn/i);
    });

    it("reports the flip rather than changing the setting", async () => {
      const { user, props } = await open({ pinned: ALL_PINNED });
      await user.click(
        screen.getByRole("button", { name: "Suggestions — pinned to this scene" }),
      );
      expect(props.onPinnedChange).toHaveBeenCalledWith("suggestionsCount", false);
      // A pin says where a change goes; it is not itself a change.
      expect(props.onSuggestionsCountChange).not.toHaveBeenCalled();
    });

    it("hides the spring-back footer while everything is pinned", async () => {
      await open({ pinned: ALL_PINNED });
      expect(screen.queryByText(/spring back/i)).not.toBeInTheDocument();
    });

    it("counts the unpinned settings in the footer", async () => {
      await open({ pinned: { ...ALL_PINNED, maxTurns: false, suggestionsCount: false } });
      expect(
        screen.getByText(/2 settings apply to your next message only/i),
      ).toBeInTheDocument();
    });

    it("counts one unpinned setting in the singular", async () => {
      await open({ pinned: { ...ALL_PINNED, maxTurns: false } });
      expect(screen.getByText(/1 setting applies to your next message only/i)).toBeInTheDocument();
    });

    it("marks the closed Config button when anything is unpinned", async () => {
      // The state has to be visible without opening the popover, and the dot alone is not
      // visible to a screen reader — hence the text beside it.
      setup({ pinned: { ...ALL_PINNED, suggestionsCount: false } });
      expect(
        screen.getByRole("button", { name: /settings apply to this turn only/i }),
      ).toBeInTheDocument();
    });

    it("leaves the Config button unmarked when every control is pinned", async () => {
      setup({ pinned: ALL_PINNED });
      expect(
        screen.queryByRole("button", { name: /settings apply to this turn only/i }),
      ).not.toBeInTheDocument();
    });

    it("reaches every pin by keyboard", async () => {
      const { user, props } = await open({ pinned: ALL_PINNED });
      const pin = screen.getByRole("button", { name: "Suggestions — pinned to this scene" });
      pin.focus();
      expect(pin).toHaveFocus();
      await user.keyboard("{Enter}");
      expect(props.onPinnedChange).toHaveBeenCalledWith("suggestionsCount", false);
    });

    it("is pinned by default, so a player who ignores pins sees no change", async () => {
      await open();
      expect(screen.queryByText(/spring back/i)).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Suggestions — pinned to this scene" }),
      ).toBeInTheDocument();
    });
  });
});


  