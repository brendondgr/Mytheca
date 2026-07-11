import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PovSelect } from "./PovSelect";

const OPTIONS = [
  { id: "mei", name: "Mei" },
  { id: "kira", name: "Kira" },
];

describe("PovSelect", () => {
  it("renders an accessible 'Speaking as' select with Narrator + each present cast member", () => {
    render(<PovSelect pov={null} onPovChange={() => {}} options={OPTIONS} />);
    expect(screen.getByRole("combobox", { name: /speaking as/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Narrator" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Mei" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Kira" })).toBeInTheDocument();
  });

  it("defaults to Narrator (empty value) when pov is null", () => {
    render(<PovSelect pov={null} onPovChange={() => {}} options={OPTIONS} />);
    expect(screen.getByRole("combobox", { name: /speaking as/i })).toHaveValue("");
  });

  it("reflects the active POV as the selected value", () => {
    render(<PovSelect pov="kira" onPovChange={() => {}} options={OPTIONS} />);
    expect(screen.getByRole("combobox", { name: /speaking as/i })).toHaveValue("kira");
  });

  it("calls onPovChange with the character id when a member is chosen", () => {
    const onPovChange = vi.fn();
    render(<PovSelect pov={null} onPovChange={onPovChange} options={OPTIONS} />);
    fireEvent.change(screen.getByRole("combobox", { name: /speaking as/i }), { target: { value: "mei" } });
    expect(onPovChange).toHaveBeenCalledWith("mei");
  });

  it("calls onPovChange with null when Narrator is chosen", () => {
    const onPovChange = vi.fn();
    render(<PovSelect pov="mei" onPovChange={onPovChange} options={OPTIONS} />);
    fireEvent.change(screen.getByRole("combobox", { name: /speaking as/i }), { target: { value: "" } });
    expect(onPovChange).toHaveBeenCalledWith(null);
  });

  it("renders nothing when there are no present cast members to speak as", () => {
    const { container } = render(<PovSelect pov={null} onPovChange={() => {}} options={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
