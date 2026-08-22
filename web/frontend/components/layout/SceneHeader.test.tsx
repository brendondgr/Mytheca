import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, it, expect, vi } from "vitest";
import { SceneHeader } from "./SceneHeader";

/**
 * Make `useMediaQuery` answer for a given viewport width.
 *
 * jsdom does not implement `matchMedia`, and the shared setup stubs it to `matches: false` —
 * which is the NARROW form. That is the right default (the server renders narrow too), but it
 * means the wide form is only ever exercised by a test that asks for it.
 */
function atWidth(width: number) {
  window.matchMedia = ((query: string) =>
    ({
      matches: (() => {
        const min = Number(/min-width:\s*(\d+)px/.exec(query)?.[1] ?? NaN);
        return Number.isNaN(min) ? false : width >= min;
      })(),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList) as typeof window.matchMedia;
}

const WIDE = 1024;
const NARROW = 320;
const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

describe("SceneHeader export control", () => {
  // Export is no longer an inline header control: it folded into the scene menu along with
  // the Inspector toggle and the new Writing item, so the header can gain capability while
  // losing width. The behaviour it had is unchanged — it is one click further in.
  it("exports as Markdown from the scene menu", async () => {
    const onExport = vi.fn();
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={onExport} canExport />);

    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /export as markdown/i }));
    expect(onExport).toHaveBeenCalledWith("md");
  });

  it("exports as JSON from the scene menu", async () => {
    const onExport = vi.fn();
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={onExport} canExport />);

    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /export as json/i }));
    expect(onExport).toHaveBeenCalledWith("json");
  });

  it("disables the export items until a session exists, and says why", async () => {
    // A disabled control with no explanation reads as a bug.
    render(
      <SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport={false} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    const md = screen.getByRole("menuitem", { name: /export as markdown/i });
    expect(md).toBeDisabled();
    expect(md).toHaveTextContent(/nothing to export until the scene has a turn/i);
  });

  it("omits the export items when no export handler is given", async () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" onToggleInspector={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.queryByRole("menuitem", { name: /export as/i })).not.toBeInTheDocument();
  });

  it("shows no scene menu at all when it would be empty — at a width where it can be", () => {
    // Only the wide form can have an empty menu. Below `sm` the theme switcher lives in
    // there, so there is always at least one row.
    atWidth(WIDE);
    render(<SceneHeader title="Standoff" settingName="Hearth" />);
    expect(screen.queryByRole("button", { name: /scene menu/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader scene menu", () => {
  it("carries the Inspector as a toggle that announces its state", async () => {
    const onToggleInspector = vi.fn();
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        onToggleInspector={onToggleInspector}
        inspectorOpen
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    const item = screen.getByRole("menuitemcheckbox", { name: /turn inspector/i });
    expect(item).toHaveAttribute("aria-checked", "true");

    await userEvent.click(item);
    expect(onToggleInspector).toHaveBeenCalled();
    // A toggle keeps the panel open — closing it would hide the state change just made.
    expect(screen.getByRole("menu", { name: /scene menu/i })).toBeInTheDocument();
  });

  it("opens the writing prompts", async () => {
    const onOpenWriting = vi.fn();
    render(
      <SceneHeader title="Standoff" settingName="Hearth" onOpenWriting={onOpenWriting} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /writing/i }));
    expect(onOpenWriting).toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.getByRole("menu", { name: /scene menu/i })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu", { name: /scene menu/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader view switch (chat ⇄ graph)", () => {
  it("renders the Chat/Graph switch to the left of Export and fires the handler", async () => {
    const onViewModeChange = vi.fn();
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        viewMode="chat"
        onViewModeChange={onViewModeChange}
        onExport={vi.fn()}
        canExport
      />,
    );
    const group = screen.getByRole("group", { name: /scene view/i });
    const menuBtn = screen.getByRole("button", { name: /scene menu/i });
    // The switch precedes the scene menu in the DOM (to its left).
    expect(group.compareDocumentPosition(menuBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Active state reflects the current mode.
    expect(screen.getByRole("button", { name: /chat/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /graph/i })).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(screen.getByRole("button", { name: /graph/i }));
    expect(onViewModeChange).toHaveBeenCalledWith("graph");
  });

  it("omits the switch when no handler is given", () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport />);
    expect(screen.queryByRole("group", { name: /scene view/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader config control (relocated to the composer)", () => {
  it("no longer renders the Config control in the header", () => {
    // Scene Config now lives in the composer's bottom-left controls row, not the header.
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport />);
    expect(screen.queryByRole("button", { name: /scene configuration/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader model status", () => {
  const health = (over: Partial<import("@/lib/types").LlmHealth> = {}) => ({
    state: "reachable" as const,
    backend: "llamacpp",
    model: "test-model",
    checkedAt: "2026-08-22T00:00:00Z",
    detail: "test-model is served by this endpoint.",
    ...over,
  });

  it("shows nothing until the first check has answered", () => {
    // A light that guesses is worse than one that waits.
    render(<SceneHeader title="Salt" settingName="Hearth" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reports readiness in words, not only by colour", () => {
    atWidth(WIDE);
    render(<SceneHeader title="Salt" settingName="Hearth" health={health()} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/model ready/i);
    expect(status).toHaveAccessibleName(/model ready/i);
  });

  it("keeps the words in its NAME when it shrinks to a glyph below sm", () => {
    // It used to be `hidden sm:flex` — absent at exactly the width where a broken endpoint
    // is hardest to diagnose. It is now always rendered; only the drawing shrinks.
    atWidth(NARROW);
    const { rerender } = render(
      <SceneHeader title="Salt" settingName="Hearth" health={health()} />,
    );
    const status = screen.getByRole("status");
    expect(status).toBeVisible();
    expect(status).toHaveAccessibleName(/model ready/i);

    // The glyph is the second channel: a bare coloured dot at 320px would be colour alone.
    const ready = status.textContent;
    rerender(<SceneHeader title="Salt" settingName="Hearth" health={health({ state: "unreachable" })} />);
    expect(screen.getByRole("status").textContent).not.toBe(ready);
    expect(screen.getByRole("status")).toHaveAccessibleName(/model unreachable/i);
  });

  it("distinguishes a missing model from a dead endpoint", () => {
    // They are different problems with different fixes — a typo in Options versus a dead
    // process — and a single "something is wrong" would send the player to the wrong one.
    atWidth(WIDE);
    const { rerender } = render(
      <SceneHeader title="Salt" settingName="Hearth" health={health({ state: "model_missing" })} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/model not found/i);

    rerender(<SceneHeader title="Salt" settingName="Hearth" health={health({ state: "unreachable" })} />);
    expect(screen.getByRole("status")).toHaveTextContent(/model unreachable/i);
  });

  it("says nothing is set up rather than raising an alarm", () => {
    atWidth(WIDE);
    render(<SceneHeader title="Salt" settingName="Hearth" health={health({ state: "unconfigured" })} />);
    expect(screen.getByRole("status")).toHaveTextContent(/no model set/i);
  });

  it("carries the endpoint's own explanation in the accessible name", () => {
    render(
      <SceneHeader
        title="Salt"
        settingName="Hearth"
        health={health({ state: "unreachable", detail: "The endpoint answered 503." })}
      />,
    );
    expect(screen.getByRole("status")).toHaveAccessibleName(/the endpoint answered 503/i);
  });
});


describe("SceneHeader below sm — the overflow menu", () => {
  /** Everything a scene player can do from the header. */
  function full(over: Record<string, unknown> = {}) {
    return (
      <SceneHeader
        title="Salt"
        settingName="Hearth"
        viewMode="chat"
        onViewModeChange={vi.fn()}
        onExport={vi.fn()}
        canExport
        onToggleInspector={vi.fn()}
        onOpenWriting={vi.fn()}
        onToggleMemory={vi.fn()}
        onOpenShortcuts={vi.fn()}
        health={{
          state: "reachable",
          backend: "llamacpp",
          model: "m",
          checkedAt: "2026-08-22T00:00:00Z",
          detail: "served",
        }}
        tray={<button type="button">Play-throughs</button>}
        trayPanel={<button type="button">A saved story</button>}
        {...over}
      />
    );
  }

  it("keeps only the mode switch and the health light inline", () => {
    atWidth(NARROW);
    render(full());
    expect(screen.getByRole("group", { name: /scene view/i })).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    // Everything else is one tap further in — and, crucially, rendered ONCE. A duplicated
    // cluster would produce two "What the scene knows" and a tab order visiting invisible
    // buttons.
    expect(screen.queryByRole("button", { name: "What the scene knows" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: /theme/i })).not.toBeInTheDocument();
  });

  it("reaches every remaining control through the ⋯ menu", async () => {
    atWidth(NARROW);
    render(full());
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    const menu = within(screen.getByRole("menu", { name: /scene menu/i }));

    expect(menu.getByRole("menuitem", { name: "Play-throughs" })).toBeInTheDocument();
    expect(menu.getByRole("menuitemcheckbox", { name: "What the scene knows" })).toBeInTheDocument();
    expect(menu.getByRole("menuitem", { name: "Writing…" })).toBeInTheDocument();
    expect(menu.getByRole("menuitemcheckbox", { name: "Turn Inspector" })).toBeInTheDocument();
    expect(menu.getByRole("menuitem", { name: "Export as Markdown" })).toBeInTheDocument();
    expect(menu.getByRole("menuitem", { name: "Export as JSON" })).toBeInTheDocument();
    expect(menu.getByRole("menuitem", { name: "Keyboard shortcuts" })).toBeInTheDocument();
    // The theme switcher rides in as a labelled row rather than three flattened commands.
    expect(menu.getByText("Theme")).toBeInTheDocument();
  });

  it("drills a panel-owning item down in place, and ‹ Back returns", async () => {
    // Never a popover inside a popover: two Escape targets and two outside-click handlers
    // racing each other is not operable by keyboard or screen reader.
    atWidth(NARROW);
    render(full());
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Play-throughs" }));

    expect(screen.getByRole("button", { name: "A saved story" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Writing…" })).not.toBeInTheDocument();
    // Still exactly one menu — the panel replaced the rows rather than stacking on them.
    expect(screen.getAllByRole("menu")).toHaveLength(1);

    await userEvent.click(screen.getByRole("menuitem", { name: /back/i }));
    expect(screen.getByRole("menuitem", { name: "Writing…" })).toBeInTheDocument();
  });

  it("Escape steps back out of a panel before it closes the menu", async () => {
    atWidth(NARROW);
    render(full());
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Play-throughs" }));

    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("menuitem", { name: "Writing…" })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("carries anything another plan adds, at one array entry", async () => {
    atWidth(NARROW);
    const onSelect = vi.fn();
    render(full({ extraControls: [{ key: "x", label: "Something new", onSelect }] }));
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Something new" }));
    expect(onSelect).toHaveBeenCalled();
  });

  it("leaves the wide form inline and unchanged", () => {
    atWidth(WIDE);
    render(full());
    expect(screen.getByRole("button", { name: "What the scene knows" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play-throughs" })).toBeInTheDocument();
    // Theme is inline, not a menu row.
    expect(screen.queryByText("Theme")).not.toBeInTheDocument();
  });
});
