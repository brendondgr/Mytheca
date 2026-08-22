import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneConfigMenu } from "./SceneConfigMenu";

function setup(overrides: Record<string, unknown> = {}) {
  const props = {
    maxTurns: 5,
    onMaxTurnsChange: vi.fn(),
    suggestionsCount: 4,
    onSuggestionsCountChange: vi.fn(),
    onContextBeatsChange: vi.fn(),
    beatLength: "medium" as const,
    onBeatLengthChange: vi.fn(),
    onPinnedChange: vi.fn(),
    onPresetChange: vi.fn(),
    onPlannerModeChange: vi.fn(),
    onRegisterChange: vi.fn(),
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

  describe("pins — per-turn versus permanent", () => {
    const ALL_PINNED = {
      maxTurns: true,
      suggestionsCount: true,
      beatLength: true,
      planner: true,
    };

    async function open(overrides = {}) {
      const user = userEvent.setup();
      const props = setup(overrides);
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      return { user, props };
    }

    it("gives every control a pin whose accessible name states the scope", async () => {
      await open({ pinned: ALL_PINNED });
      for (const name of ["Max turns", "Suggestions", "Beat length"]) {
        const pin = screen.getByRole("button", { name: `${name} — pinned to this scene` });
        expect(pin).toHaveAttribute("aria-pressed", "true");
      }
    });

    it("says 'this turn only' on an unpinned control, in the name and on the row", async () => {
      // Scope is never colour alone: the pin's accessible name carries it for a screen
      // reader, and the caption carries it visibly.
      await open({ pinned: { ...ALL_PINNED, beatLength: false } });
      const pin = screen.getByRole("button", { name: "Beat length — this turn only" });
      expect(pin).toHaveAttribute("aria-pressed", "false");
      // Scoped to this row: the register row carries a PERMANENT "· this turn" tag, so a
      // bare text query would match two and prove nothing about the pin.
      const row = screen
        .getByRole("combobox", { name: /how much a character says at once/i })
        .closest("div");
      expect(row).toHaveTextContent(/· this turn/i);
    });

    it("reports the flip rather than changing the setting", async () => {
      const { user, props } = await open({ pinned: ALL_PINNED });
      await user.click(screen.getByRole("button", { name: "Max turns — pinned to this scene" }));
      expect(props.onPinnedChange).toHaveBeenCalledWith("maxTurns", false);
      // A pin says where a change goes; it is not itself a change.
      expect(props.onMaxTurnsChange).not.toHaveBeenCalled();
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
        screen.getByRole("button", { name: "Max turns — pinned to this scene" }),
      ).toBeInTheDocument();
    });
  });

  describe("scene presets", () => {
    const PRESETS = [
      {
        id: "fast_banter",
        label: "Fast banter",
        blurb: "Short beats, quick exchanges, plenty of follow-ups.",
        values: { maxTurns: 3, suggestionsCount: 4, beatLength: "short" as const },
      },
      {
        id: "slow_burn",
        label: "Slow burn",
        blurb: "Long beats, fewer of them.",
        values: { maxTurns: 6, suggestionsCount: 2, beatLength: "long" as const },
      },
    ];

    async function openWith(overrides = {}) {
      const user = userEvent.setup();
      const props = setup({ presets: PRESETS, ...overrides });
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      return { user, props };
    }

    it("offers Custom plus every preset, above the individual controls", async () => {
      await openWith();
      const picker = screen.getByRole("combobox", { name: /what kind of scene this is/i });
      expect([...picker.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
        "Custom",
        "Fast banter",
        "Slow burn",
      ]);
    });

    it("renders the named preset's blurb", async () => {
      await openWith({ scenePreset: "slow_burn", presetState: "clean" });
      expect(
        screen.getByRole("combobox", { name: /what kind of scene this is/i }),
      ).toHaveAccessibleDescription(/long beats, fewer of them/i);
    });

    it("reports the pick rather than setting the controls itself", async () => {
      const { user, props } = await openWith();
      await user.selectOptions(
        screen.getByRole("combobox", { name: /what kind of scene this is/i }),
        "fast_banter",
      );
      expect(props.onPresetChange).toHaveBeenCalledWith("fast_banter");
      expect(props.onMaxTurnsChange).not.toHaveBeenCalled();
    });

    it("clears the preset when Custom is chosen", async () => {
      const { user, props } = await openWith({ scenePreset: "fast_banter", presetState: "clean" });
      await user.selectOptions(
        screen.getByRole("combobox", { name: /what kind of scene this is/i }),
        "Custom",
      );
      expect(props.onPresetChange).toHaveBeenCalledWith(null);
    });

    it("marks a drifted scene and offers a reset", async () => {
      const { user, props } = await openWith({
        scenePreset: "slow_burn",
        presetState: "modified",
      });
      expect(screen.getByText(/· modified/i)).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /reset to slow burn/i }));
      expect(props.onPresetChange).toHaveBeenCalledWith("slow_burn");
    });

    it("offers no reset while the scene still matches its preset", async () => {
      await openWith({ scenePreset: "slow_burn", presetState: "clean" });
      expect(screen.queryByRole("button", { name: /reset to/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/· modified/i)).not.toBeInTheDocument();
    });

    it("hides the picker entirely when no catalogue arrived", async () => {
      // A failed fetch must leave every underlying control exactly where it was.
      const user = userEvent.setup();
      setup();
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      expect(
        screen.queryByRole("combobox", { name: /what kind of scene this is/i }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("combobox", { name: /how many beats one message produces/i }),
      ).toBeInTheDocument();
    });
  });

  describe("turn planning", () => {
    it("offers both modes with the director's job spelled out", async () => {
      const user = userEvent.setup();
      setup({ onPlannerModeChange: vi.fn() });
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      const control = screen.getByRole("combobox", { name: /turn planning/i });
      expect([...control.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
        "On · a director reads each moment",
        "Off · the cast answers in order",
      ]);
      expect(control).toHaveAccessibleDescription(/over half of a turn/i);
    });

    it("states the LOSS when planning is off, not only the speed", async () => {
      // A control that advertised the saving without the cost would be lying.
      const user = userEvent.setup();
      setup({ plannerMode: "off", onPlannerModeChange: vi.fn() });
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      const control = screen.getByRole("combobox", { name: /turn planning/i });
      expect(control).toHaveAccessibleDescription(/nothing judges the moment/i);
      expect(control).toHaveAccessibleDescription(/no scene-setting narration/i);
      expect(control).toHaveAccessibleDescription(/stays in the rotation/i);
    });

    it("reports the change", async () => {
      const user = userEvent.setup();
      const props = setup({ onPlannerModeChange: vi.fn() });
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      await user.selectOptions(screen.getByRole("combobox", { name: /turn planning/i }), "off");
      expect(props.onPlannerModeChange).toHaveBeenCalledWith("off");
    });

    it("is pinnable like the other controls", async () => {
      const user = userEvent.setup();
      const props = setup({ onPlannerModeChange: vi.fn() });
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      await user.click(
        screen.getByRole("button", { name: "Turn planning — pinned to this scene" }),
      );
      expect(props.onPinnedChange).toHaveBeenCalledWith("planner", false);
    });
  });

  describe("register", () => {
    async function open(overrides = {}) {
      const user = userEvent.setup();
      const props = setup({ onRegisterChange: vi.fn(), ...overrides });
      await user.click(screen.getByRole("button", { name: /scene configuration/i }));
      return { user, props };
    }

    it("offers Auto plus the four registers", async () => {
      await open();
      const control = screen.getByRole("combobox", { name: /how this moment is pitched/i });
      expect([...control.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
        "Auto · the scene decides",
        "Light",
        "Neutral",
        "Tense",
        "Grave",
      ]);
    });

    it("carries a permanent 'this turn' tag and no pin", async () => {
      // It is per-turn by construction: how tense a beat is belongs to a moment, so there
      // is nothing to pin it to.
      await open();
      expect(
        screen.queryByRole("button", { name: /^Register — /i }),
      ).not.toBeInTheDocument();
      const row = screen
        .getByRole("combobox", { name: /how this moment is pitched/i })
        .closest("div");
      expect(row).toHaveTextContent(/· this turn/i);
    });

    it("says what it does NOT do", async () => {
      // A control called "register" sitting under "who speaks" invites that misreading.
      await open();
      expect(
        screen.getByRole("combobox", { name: /how this moment is pitched/i }),
      ).toHaveAccessibleDescription(/does not decide who speaks/i);
    });

    it("reports a pick, and clears back to Auto", async () => {
      const { user, props } = await open({ register: "grave" });
      const control = screen.getByRole("combobox", { name: /how this moment is pitched/i });
      await user.selectOptions(control, "tense");
      expect(props.onRegisterChange).toHaveBeenCalledWith("tense");

      await user.selectOptions(control, "Auto · the scene decides");
      expect(props.onRegisterChange).toHaveBeenCalledWith(null);
    });
  });
});
