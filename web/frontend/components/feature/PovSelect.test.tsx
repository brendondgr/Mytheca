import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PovSelect } from "./PovSelect";

const OPTIONS = [
  { id: "mei", name: "Mei", mono: "M", color: "#8E2B1C", portrait: null },
  { id: "kira", name: "Kira", mono: "K", color: "#5A7CA0", portrait: null },
];

function open() {
  fireEvent.click(screen.getByRole("button", { name: /speaking as/i }));
}

describe("PovSelect", () => {
  it("renders a 'Speaking as' trigger button (a custom dropdown, not a native select)", () => {
    render(<PovSelect pov={null} onPovChange={() => {}} options={OPTIONS} />);
    expect(screen.getByRole("button", { name: /speaking as/i })).toBeInTheDocument();
    // No native select is used.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    // The menu is closed until opened.
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens a menu of Narrator + each present cast member on click", () => {
    render(<PovSelect pov={null} onPovChange={() => {}} options={OPTIONS} />);
    open();
    const menu = screen.getByRole("menu", { name: /speaking as/i });
    expect(within(menu).getByRole("menuitemradio", { name: "Narrator" })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitemradio", { name: "Mei" })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitemradio", { name: "Kira" })).toBeInTheDocument();
  });

  it("shows the current POV name on the trigger and marks that option checked", () => {
    render(<PovSelect pov="kira" onPovChange={() => {}} options={OPTIONS} />);
    // Closed: the trigger displays the active character's name.
    expect(screen.getByRole("button", { name: /speaking as/i }).textContent).toContain("Kira");
    open();
    expect(screen.getByRole("menuitemradio", { name: "Kira" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitemradio", { name: "Mei" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("menuitemradio", { name: "Narrator" })).toHaveAttribute("aria-checked", "false");
  });

  it("defaults to Narrator checked when pov is null", () => {
    render(<PovSelect pov={null} onPovChange={() => {}} options={OPTIONS} />);
    expect(screen.getByRole("button", { name: /speaking as/i }).textContent).toContain("Narrator");
    open();
    expect(screen.getByRole("menuitemradio", { name: "Narrator" })).toHaveAttribute("aria-checked", "true");
  });

  it("calls onPovChange with the character id when a member is chosen", () => {
    const onPovChange = vi.fn();
    render(<PovSelect pov={null} onPovChange={onPovChange} options={OPTIONS} />);
    open();
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Mei" }));
    expect(onPovChange).toHaveBeenCalledWith("mei");
  });

  it("calls onPovChange with null when Narrator is chosen", () => {
    const onPovChange = vi.fn();
    render(<PovSelect pov="mei" onPovChange={onPovChange} options={OPTIONS} />);
    open();
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Narrator" }));
    expect(onPovChange).toHaveBeenCalledWith(null);
  });

  it("renders nothing when there are no present cast members to speak as", () => {
    const { container } = render(<PovSelect pov={null} onPovChange={() => {}} options={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
