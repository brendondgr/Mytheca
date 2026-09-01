import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { BeatControls } from "./BeatControls";

describe("BeatControls", () => {
  it("edits on one click — it removes nothing", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(<BeatControls onEdit={onEdit} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: /edit mei's beat/i }));
    expect(onEdit).toHaveBeenCalled();
  });

  it("re-rolls just the beat", async () => {
    const user = userEvent.setup();
    const onReroll = vi.fn();
    render(<BeatControls onReroll={onReroll} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: /^re-roll mei's beat/i }));
    expect(onReroll).toHaveBeenCalledWith("beat");
  });

  it("offers re-running the whole turn as a separate action", async () => {
    const user = userEvent.setup();
    const onReroll = vi.fn();
    render(<BeatControls onReroll={onReroll} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: /re-run the whole turn/i }));
    expect(onReroll).toHaveBeenCalledWith("turn");
  });

  it("renders nothing when no action is available", () => {
    const { container } = render(<BeatControls />);
    expect(container).toBeEmptyDOMElement();
  });

  it("branches immediately — it removes nothing, so it costs one click", async () => {
    const user = userEvent.setup();
    const onBranch = vi.fn();
    render(<BeatControls onBranch={onBranch} label="Mei's beat" />);

    await user.click(screen.getByRole("button", { name: /branch from mei's beat/i }));
    expect(onBranch).toHaveBeenCalled();
  });

  it("confirms before rewinding, because it removes content", async () => {
    const user = userEvent.setup();
    const onRewind = vi.fn();
    render(<BeatControls onRewind={onRewind} rewindBeatCount={4} label="Mei's beat" />);

    await user.click(screen.getByRole("button", { name: /rewind to mei's beat/i }));
    expect(onRewind).not.toHaveBeenCalled();
    expect(screen.getByText(/remove 4 beats\?/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rewind" }));
    expect(onRewind).toHaveBeenCalled();
  });

  it("names how many beats go, rather than asking the player to guess", async () => {
    const user = userEvent.setup();
    render(<BeatControls onRewind={vi.fn()} rewindBeatCount={1} />);
    await user.click(screen.getByRole("button", { name: /rewind to/i }));
    expect(screen.getByText(/remove 1 beat\?/i)).toBeInTheDocument();
  });

  it("keeps the beat when the confirmation is declined", async () => {
    const user = userEvent.setup();
    const onRewind = vi.fn();
    render(<BeatControls onRewind={onRewind} rewindBeatCount={2} />);

    await user.click(screen.getByRole("button", { name: /rewind to/i }));
    await user.click(screen.getByRole("button", { name: "Keep" }));

    expect(onRewind).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /rewind to/i })).toBeInTheDocument();
  });

  it("stays in the tab order while quiet, so it is not mouse-only", () => {
    render(<BeatControls onBranch={vi.fn()} onRewind={vi.fn()} />);
    const buttons = screen.getAllByRole("button");
    // Present and visible even though the cluster is at opacity 0 until hover…
    for (const b of buttons) expect(b).toBeVisible();
    // …and reachable: exactly ONE tab stop, the rest on arrow keys. Five stops per beat put
    // 57 controls in the tab order of a twelve-beat transcript.
    expect(buttons.filter((b) => b.tabIndex === 0)).toHaveLength(1);
  });

  it("is one tab stop with arrow-key navigation inside", async () => {
    const user = userEvent.setup();
    render(<BeatControls onEdit={vi.fn()} onBranch={vi.fn()} onRewind={vi.fn()} label="Mei's beat" />);
    const bar = screen.getByRole("toolbar", { name: "Actions for Mei's beat" });
    const buttons = within(bar).getAllByRole("button");

    await user.tab();
    expect(buttons[0]).toHaveFocus();

    await user.keyboard("{ArrowRight}");
    expect(buttons[1]).toHaveFocus();

    await user.keyboard("{End}");
    expect(buttons.at(-1)).toHaveFocus();

    await user.keyboard("{ArrowRight}"); // wraps
    expect(buttons[0]).toHaveFocus();

    await user.keyboard("{ArrowLeft}"); // wraps the other way
    expect(buttons.at(-1)).toHaveFocus();
  });

  it("Tab leaves the cluster rather than cycling inside it", async () => {
    const user = userEvent.setup();
    render(
      <>
        <BeatControls onEdit={vi.fn()} onBranch={vi.fn()} />
        <button type="button">after</button>
      </>,
    );
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "after" })).toHaveFocus();
  });

  it("keeps its single tab stop when a beat offers fewer controls", () => {
    // The hazard of a hardcoded roving index: a beat with no Edit would assign the stop to a
    // control that is never rendered, and the whole cluster would drop out of the tab order.
    render(<BeatControls onRewind={vi.fn()} label="a stat change" />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons.filter((b) => b.tabIndex === 0)).toHaveLength(1);
  });

  it("is reachable by keyboard alone", async () => {
    const user = userEvent.setup();
    const onBranch = vi.fn();
    render(<BeatControls onBranch={onBranch} />);

    await user.tab();
    expect(screen.getByRole("button", { name: /branch from/i })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onBranch).toHaveBeenCalled();
  });

  it("disables its actions while a turn is streaming", () => {
    render(<BeatControls onBranch={vi.fn()} onRewind={vi.fn()} disabled />);
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});

describe("BeatControls — a rewind that empties the scene says so", () => {
  // Reported from a live scene as "Rewind to Here deletes the whole thread". It does not
  // delete anything permanently (the pre-cut history forks to a tray row and the notice
  // offers Undo) — but a rewind takes the containing turn AND everything after it, so from
  // the first turn that is the whole transcript, and the confirmation said "Remove 5 beats?"
  // in exactly the same words it uses to trim one exchange off the end.
  it("names the consequence when the cut takes the whole play-through", async () => {
    const user = userEvent.setup();
    render(<BeatControls onRewind={vi.fn()} rewindBeatCount={5} rewindEmptiesScene label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: "Rewind to Mei's beat" }));
    expect(screen.getByText(/Empty the scene — all 5 beats\?/i)).toBeInTheDocument();
  });

  it("still counts beats normally when the scene survives the cut", async () => {
    const user = userEvent.setup();
    render(<BeatControls onRewind={vi.fn()} rewindBeatCount={5} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: "Rewind to Mei's beat" }));
    expect(screen.getByText(/Remove 5 beats\?/i)).toBeInTheDocument();
    expect(screen.queryByText(/Empty the scene/i)).not.toBeInTheDocument();
  });

  it("warns in the tooltip before the player even commits to confirming", () => {
    render(<BeatControls onRewind={vi.fn()} rewindBeatCount={5} rewindEmptiesScene label="Mei's beat" />);
    expect(screen.getByRole("button", { name: "Rewind to Mei's beat" })).toHaveAttribute(
      "title",
      expect.stringMatching(/empties the scene/i),
    );
  });
});

/**
 * Below `sm` the cluster collapses to one `⋯` button. `useMediaQuery` reads `matchMedia`,
 * which jsdom does not implement — the shared setup stubs it as "matches nothing", i.e. the
 * WIDE rendering, so a narrow case has to say so explicitly.
 */
function setNarrow(narrow: boolean) {
  const previous = window.matchMedia;
  window.matchMedia = ((query: string) =>
    ({
      matches: query.includes("max-width") ? narrow : !narrow,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList) as typeof window.matchMedia;
  return () => {
    window.matchMedia = previous;
  };
}

describe("BeatControls — on a phone the cluster is a menu, not five buttons", () => {
  let restore = () => {};
  beforeEach(() => {
    restore = setNarrow(true);
  });
  afterEach(() => restore());

  it("shows one trigger instead of the toolbar", () => {
    render(<BeatControls onEdit={vi.fn()} onReroll={vi.fn()} onBranch={vi.fn()} onRewind={vi.fn()} label="Mei's beat" />);
    // 220px of permanently-visible chrome per beat is what this replaces.
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Actions for Mei's beat" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("offers every action the wide cluster does, in words", async () => {
    const user = userEvent.setup();
    render(<BeatControls onEdit={vi.fn()} onReroll={vi.fn()} onBranch={vi.fn()} onRewind={vi.fn()} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: "Actions for Mei's beat" }));
    const menu = screen.getByRole("menu", { name: "Actions for Mei's beat" });
    expect(within(menu).getAllByRole("menuitem").map((el) => el.textContent)).toEqual([
      "Edit",
      "Re-roll this beat",
      "Re-run the whole turn",
      "Branch from here",
      "Rewind to here",
    ]);
  });

  it("only lists the actions this beat actually has", async () => {
    const user = userEvent.setup();
    render(<BeatControls onBranch={vi.fn()} label="a stat change" />);
    await user.click(screen.getByRole("button", { name: "Actions for a stat change" }));
    expect(screen.getAllByRole("menuitem")).toHaveLength(1);
  });

  it("runs the action and closes", async () => {
    const user = userEvent.setup();
    const onReroll = vi.fn();
    render(<BeatControls onReroll={onReroll} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: "Actions for Mei's beat" }));
    await user.click(screen.getByRole("menuitem", { name: "Re-run the whole turn" }));
    expect(onReroll).toHaveBeenCalledWith("turn");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("still confirms a rewind — and asks inside the menu, where the finger already is", async () => {
    const user = userEvent.setup();
    const onRewind = vi.fn();
    render(<BeatControls onRewind={onRewind} rewindBeatCount={4} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: "Actions for Mei's beat" }));
    await user.click(screen.getByRole("menuitem", { name: "Rewind to here" }));
    expect(onRewind).not.toHaveBeenCalled();
    expect(screen.getByText(/remove 4 beats\?/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rewind" }));
    expect(onRewind).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("names the consequence when the cut takes the whole play-through", async () => {
    const user = userEvent.setup();
    render(<BeatControls onRewind={vi.fn()} rewindBeatCount={5} rewindEmptiesScene label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: "Actions for Mei's beat" }));
    expect(screen.getByRole("menuitem", { name: /empties the scene/i })).toBeInTheDocument();
  });

  it("closes on Escape and hands focus back, rather than dropping it at the document", async () => {
    const user = userEvent.setup();
    render(<BeatControls onBranch={vi.fn()} label="Mei's beat" />);
    const trigger = screen.getByRole("button", { name: "Actions for Mei's beat" });
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("is disabled while a turn is streaming", () => {
    render(<BeatControls onBranch={vi.fn()} disabled label="Mei's beat" />);
    expect(screen.getByRole("button", { name: "Actions for Mei's beat" })).toBeDisabled();
  });
});
