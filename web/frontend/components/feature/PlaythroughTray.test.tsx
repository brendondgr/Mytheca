import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { PlaythroughTray, playthroughLabel, relativeTime } from "./PlaythroughTray";
import type { SessionSummary } from "@/lib/events";

function session(over: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: "ps_1",
    scenarioId: "sc_1",
    createdAt: "2026-08-21T10:00:00Z",
    updatedAt: "2026-08-21T10:00:00Z",
    closedAt: null,
    turnCount: 3,
    preview: "I hold my ground.",
    name: null,
    parentSessionId: null,
    forkSeq: null,
    ...over,
  };
}

function setup(over: Partial<React.ComponentProps<typeof PlaythroughTray>> = {}) {
  const props = {
    sessions: [session()],
    currentSessionId: "ps_1",
    onOpen: vi.fn(),
    onCreate: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
    ...over,
  };
  render(<PlaythroughTray {...props} />);
  return props;
}

const openTray = async (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: /play-throughs/i }));

describe("playthroughLabel", () => {
  it("prefers the name, falls back to the first line, then to a placeholder", () => {
    expect(playthroughLabel(session({ name: "The kind run" }))).toBe("The kind run");
    expect(playthroughLabel(session({ name: null }))).toBe("I hold my ground.");
    expect(playthroughLabel(session({ name: "  ", preview: "" }))).toBe(
      "Untitled play-through",
    );
  });
});

describe("relativeTime", () => {
  const now = Date.parse("2026-08-21T12:00:00Z");

  it("reads coarsely", () => {
    expect(relativeTime("2026-08-21T11:59:30Z", now)).toBe("just now");
    expect(relativeTime("2026-08-21T11:30:00Z", now)).toBe("30m ago");
    expect(relativeTime("2026-08-21T09:00:00Z", now)).toBe("3h ago");
    expect(relativeTime("2026-08-20T12:00:00Z", now)).toBe("yesterday");
    expect(relativeTime("2026-08-18T12:00:00Z", now)).toBe("3d ago");
  });

  it("survives an unparseable timestamp rather than rendering NaN", () => {
    expect(relativeTime("not-a-date", now)).toBe("");
  });
});

describe("PlaythroughTray", () => {
  it("lists each play-through with its turn count", async () => {
    const user = userEvent.setup();
    setup({
      sessions: [
        session({ id: "ps_1", name: "First run", turnCount: 3 }),
        session({ id: "ps_2", name: "Second run", turnCount: 1 }),
      ],
    });
    await openTray(user);

    expect(screen.getByText("First run")).toBeInTheDocument();
    expect(screen.getByText("Second run")).toBeInTheDocument();
    expect(screen.getByText(/3 turns/)).toBeInTheDocument();
    // Singular, not "1 turns".
    expect(screen.getByText(/1 turn ·/)).toBeInTheDocument();
  });

  it("marks the open play-through and does not re-open it", async () => {
    const user = userEvent.setup();
    const props = setup({
      sessions: [session({ id: "ps_1", name: "Open one" }), session({ id: "ps_2", name: "Other" })],
      currentSessionId: "ps_1",
    });
    await openTray(user);

    expect(screen.getByText(/· open/)).toBeInTheDocument();
    await user.click(screen.getByText("Open one"));
    expect(props.onOpen).not.toHaveBeenCalled();
  });

  it("switches to another play-through", async () => {
    const user = userEvent.setup();
    const props = setup({
      sessions: [session({ id: "ps_1", name: "Open one" }), session({ id: "ps_2", name: "Other" })],
      currentSessionId: "ps_1",
    });
    await openTray(user);
    await user.click(screen.getByText("Other"));

    expect(props.onOpen).toHaveBeenCalledWith("ps_2");
  });

  it("starts a new play-through", async () => {
    const user = userEvent.setup();
    const props = setup();
    await openTray(user);
    await user.click(screen.getByRole("menuitem", { name: /new play-through/i }));

    expect(props.onCreate).toHaveBeenCalled();
  });

  it("renames a play-through inline, seeded with its current name", async () => {
    const user = userEvent.setup();
    const props = setup({ sessions: [session({ id: "ps_1", name: "Old name" })] });
    await openTray(user);
    await user.click(screen.getByRole("button", { name: /rename old name/i }));

    const field = screen.getByRole("textbox", { name: /rename old name/i });
    expect(field).toHaveValue("Old name");
    await user.clear(field);
    await user.type(field, "New name");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(props.onRename).toHaveBeenCalledWith("ps_1", "New name");
  });

  it("abandons a rename on cancel", async () => {
    const user = userEvent.setup();
    const props = setup({ sessions: [session({ id: "ps_1", name: "Old name" })] });
    await openTray(user);
    await user.click(screen.getByRole("button", { name: /rename old name/i }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(props.onRename).not.toHaveBeenCalled();
    expect(screen.getByText("Old name")).toBeInTheDocument();
  });

  it("confirms in-row before deleting", async () => {
    const user = userEvent.setup();
    const props = setup({ sessions: [session({ id: "ps_1", name: "Doomed" })] });
    await openTray(user);
    await user.click(screen.getByRole("button", { name: /delete doomed/i }));

    // Nothing has happened yet — the row asked first.
    expect(props.onDelete).not.toHaveBeenCalled();
    expect(screen.getByText(/delete this play-through\?/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(props.onDelete).toHaveBeenCalledWith("ps_1");
  });

  it("keeps the play-through when the confirmation is declined", async () => {
    const user = userEvent.setup();
    const props = setup({ sessions: [session({ id: "ps_1", name: "Spared" })] });
    await openTray(user);
    await user.click(screen.getByRole("button", { name: /delete spared/i }));
    await user.click(screen.getByRole("button", { name: "Keep" }));

    expect(props.onDelete).not.toHaveBeenCalled();
    expect(screen.getByText("Spared")).toBeInTheDocument();
  });

  it("explains itself when the scene has never been played", async () => {
    const user = userEvent.setup();
    setup({ sessions: [], currentSessionId: null });
    await openTray(user);

    expect(screen.getByText(/has not been played yet/i)).toBeInTheDocument();
    // Starting one is still offered.
    expect(screen.getByRole("menuitem", { name: /new play-through/i })).toBeInTheDocument();
  });

  it("marks a branched play-through as such", async () => {
    const user = userEvent.setup();
    setup({ sessions: [session({ id: "ps_2", name: "Fork", parentSessionId: "ps_1", forkSeq: 4 })] });
    await openTray(user);

    expect(screen.getByText(/· branched/)).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    setup();
    await openTray(user);
    expect(screen.getByRole("menu", { name: /play-throughs/i })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu", { name: /play-throughs/i })).not.toBeInTheDocument();
  });

  it("abandons a half-finished rename when the tray is closed and reopened", async () => {
    const user = userEvent.setup();
    setup({ sessions: [session({ id: "ps_1", name: "Old name" })] });
    await openTray(user);
    await user.click(screen.getByRole("button", { name: /rename old name/i }));
    await user.keyboard("{Escape}");
    await openTray(user);

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText("Old name")).toBeInTheDocument();
  });

  it("is disabled while a turn is streaming", async () => {
    setup({ disabled: true });
    expect(screen.getByRole("button", { name: /play-throughs/i })).toBeDisabled();
  });

  it("keeps every row action reachable by keyboard", async () => {
    const user = userEvent.setup();
    setup({ sessions: [session({ id: "ps_1", name: "Only" })] });
    await openTray(user);

    const menu = screen.getByRole("menu", { name: /play-throughs/i });
    // The row's open action and the footer's New action are menuitems; rename and delete
    // are plain buttons with accessible names. All four must be focusable.
    const actions = [
      ...within(menu).getAllByRole("menuitem"),
      ...within(menu).getAllByRole("button"),
    ];
    expect(within(menu).getByRole("menuitem", { name: /only/i })).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: /rename only/i })).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: /delete only/i })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: /new play-through/i })).toBeInTheDocument();
    for (const el of actions) expect(el).not.toHaveAttribute("tabindex", "-1");
  });
});
