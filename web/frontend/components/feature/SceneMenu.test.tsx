import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneMenu, type SceneMenuItem } from "./SceneMenu";

function open(items: SceneMenuItem[], extraSlot?: React.ReactNode) {
  render(<SceneMenu items={items} extraSlot={extraSlot} />);
  return userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
}

describe("SceneMenu", () => {
  it("declares itself as a menu trigger and reflects its state", async () => {
    render(<SceneMenu items={[{ key: "a", label: "Alpha", onSelect: vi.fn() }]} />);
    const trigger = screen.getByRole("button", { name: /scene menu/i });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menu", { name: /scene menu/i })).toBeInTheDocument();
  });

  it("runs a plain item and closes", async () => {
    const onSelect = vi.fn();
    await open([{ key: "a", label: "Alpha", onSelect }]);
    await userEvent.click(screen.getByRole("menuitem", { name: "Alpha" }));
    expect(onSelect).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("renders a toggle as a menuitemcheckbox and keeps the panel open", async () => {
    // `menuitem` + `aria-pressed` is invalid ARIA; closing would hide the state change the
    // player just made.
    const onSelect = vi.fn();
    await open([{ key: "t", label: "Inspector", pressed: true, onSelect }]);
    const item = screen.getByRole("menuitemcheckbox", { name: "Inspector" });
    expect(item).toHaveAttribute("aria-checked", "true");

    await userEvent.click(item);
    expect(onSelect).toHaveBeenCalled();
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("keeps a hint out of the accessible name and in the description", async () => {
    await open([{ key: "a", label: "Alpha", hint: "does a thing", onSelect: vi.fn() }]);
    const item = screen.getByRole("menuitem", { name: "Alpha" });
    expect(item).toHaveAccessibleName("Alpha");
    expect(item).toHaveAccessibleDescription("does a thing");
  });

  it("lets a non-button control sit as a labelled row", async () => {
    await open([{ key: "th", label: "Theme", render: <button type="button">Ember</button> }]);
    const menu = within(screen.getByRole("menu"));
    expect(menu.getByText("Theme")).toBeInTheDocument();
    expect(menu.getByRole("button", { name: "Ember" })).toBeInTheDocument();
  });

  it("disables an item and still explains why", async () => {
    await open([{ key: "x", label: "Export", hint: "nothing to export yet", disabled: true, onSelect: vi.fn() }]);
    const item = screen.getByRole("menuitem", { name: "Export" });
    expect(item).toBeDisabled();
    expect(item).toHaveAccessibleDescription("nothing to export yet");
  });

  it("closes on Escape and on an outside click", async () => {
    await open([{ key: "a", label: "Alpha", onSelect: vi.fn() }]);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("renders the extra slot at the foot", async () => {
    await open([{ key: "a", label: "Alpha", onSelect: vi.fn() }], <p>foot</p>);
    expect(within(screen.getByRole("menu")).getByText("foot")).toBeInTheDocument();
  });
});

describe("SceneMenu drill-down", () => {
  const items: SceneMenuItem[] = [
    { key: "tray", label: "Play-throughs", panel: <button type="button">A saved story</button> },
    { key: "a", label: "Alpha", onSelect: vi.fn() },
  ];

  it("advertises a panel-owning row and replaces the rows in place", async () => {
    // Never a popover inside a popover: two Escape targets and two outside-click handlers
    // racing each other is not operable by keyboard or screen reader.
    await open(items);
    const row = screen.getByRole("menuitem", { name: "Play-throughs" });
    expect(row).toHaveAttribute("aria-haspopup", "menu");

    await userEvent.click(row);
    expect(screen.getByRole("button", { name: "A saved story" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Alpha" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("menu")).toHaveLength(1);
  });

  it("‹ Back returns to the rows", async () => {
    await open(items);
    await userEvent.click(screen.getByRole("menuitem", { name: "Play-throughs" }));
    await userEvent.click(screen.getByRole("menuitem", { name: /back/i }));
    expect(screen.getByRole("menuitem", { name: "Alpha" })).toBeInTheDocument();
  });

  it("Escape steps back one level before it closes the menu", async () => {
    await open(items);
    await userEvent.click(screen.getByRole("menuitem", { name: "Play-throughs" }));

    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("menuitem", { name: "Alpha" })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("reopens at the top level, never where it was left", async () => {
    await open(items);
    await userEvent.click(screen.getByRole("menuitem", { name: "Play-throughs" }));
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i })); // close
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i })); // reopen
    expect(screen.getByRole("menuitem", { name: "Alpha" })).toBeInTheDocument();
  });

  it("hides the extra slot while a panel is showing", async () => {
    await open(items, <p>foot</p>);
    await userEvent.click(screen.getByRole("menuitem", { name: "Play-throughs" }));
    expect(screen.queryByText("foot")).not.toBeInTheDocument();
  });
});
