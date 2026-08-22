import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneMenu, type SceneMenuItem } from "./SceneMenu";

function items(overrides: Partial<SceneMenuItem>[] = []): SceneMenuItem[] {
  const base: SceneMenuItem[] = [
    { key: "writing", label: "Writing…", hint: "the instructions", onSelect: vi.fn() },
    { key: "inspector", label: "Turn Inspector", pressed: false, onSelect: vi.fn() },
    { key: "export-md", label: "Export as Markdown", onSelect: vi.fn() },
  ];
  return base.map((b, i) => ({ ...b, ...(overrides[i] ?? {}) }));
}

describe("SceneMenu", () => {
  it("is closed until the trigger is used", async () => {
    render(<SceneMenu items={items()} />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.getByRole("menu", { name: /scene menu/i })).toBeInTheDocument();
  });

  it("renders plain items as menuitems and toggles as menuitemcheckboxes", async () => {
    // `aria-pressed` on a `menuitem` is invalid ARIA; a menu toggle is a
    // `menuitemcheckbox`. Getting this wrong means the state is silently unannounced.
    render(<SceneMenu items={items()} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.getAllByRole("menuitem")).toHaveLength(2);
    expect(screen.getAllByRole("menuitemcheckbox")).toHaveLength(1);
  });

  it("fires an item and closes", async () => {
    const rows = items();
    render(<SceneMenu items={rows} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /export as markdown/i }));

    expect(rows[2].onSelect).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("keeps the panel open for a toggle, so the state change stays visible", async () => {
    const rows = items();
    render(<SceneMenu items={rows} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitemcheckbox", { name: /turn inspector/i }));

    expect(rows[1].onSelect).toHaveBeenCalled();
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("announces a toggle's state rather than leaving it to be inferred", async () => {
    render(<SceneMenu items={items([{}, { pressed: true }])} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.getByRole("menuitemcheckbox", { name: /turn inspector/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("does not mark a plain item as a toggle", async () => {
    render(<SceneMenu items={items()} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(
      screen.getByRole("menuitem", { name: /export as markdown/i }),
    ).not.toHaveAttribute("aria-checked");
  });

  it("disables an item and still shows its hint as the reason", async () => {
    const rows = items([{}, {}, { disabled: true, hint: "nothing to export yet" }]);
    render(<SceneMenu items={rows} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));

    const item = screen.getByRole("menuitem", { name: /export as markdown/i });
    expect(item).toBeDisabled();
    expect(item).toHaveTextContent(/nothing to export yet/i);

    await userEvent.click(item);
    expect(rows[2].onSelect).not.toHaveBeenCalled();
  });

  it("is reachable and operable by keyboard", async () => {
    const rows = items();
    render(<SceneMenu items={rows} />);
    await userEvent.tab();
    expect(screen.getByRole("button", { name: /scene menu/i })).toHaveFocus();

    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("menu")).toBeInTheDocument();

    // Focus lands in the panel on open, so Tab reaches the first item rather than leaving
    // a keyboard user stranded behind the trigger.
    await userEvent.tab();
    expect(screen.getByRole("menuitem", { name: /writing/i })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(rows[0].onSelect).toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    render(<SceneMenu items={items()} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("closes on an outside click", async () => {
    render(
      <div>
        <SceneMenu items={items()} />
        <button type="button">elsewhere</button>
      </div>,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("button", { name: /elsewhere/i }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("renders a non-button control as a labelled row", async () => {
    // The seam `docs/plans/reach.md` Phase 4 needs: a theme switcher (or any control that
    // is not a menuitem) sitting in the same list without a second popover.
    render(
      <SceneMenu
        items={[
          { key: "theme", label: "Theme", render: <button type="button">Slate</button> },
        ]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.getByText("Theme")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Slate" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
  });

  it("renders an extra slot at the foot", async () => {
    render(<SceneMenu items={items()} extraSlot={<p>footer</p>} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.getByText("footer")).toBeInTheDocument();
  });


  it("keeps the hint out of the accessible NAME and in the description", async () => {
    // Left to the default computation the label and hint concatenate — "Turn Inspectorwhat
    // the scene read…" — which is what a screen reader announces as the item's name.
    render(<SceneMenu items={items()} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    const item = screen.getByRole("menuitem", { name: "Writing…" });
    expect(item).toHaveAccessibleDescription("the instructions");
  });
});
