import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DirectionRow } from "./DirectionRow";

describe("DirectionRow", () => {
  it("is a labelled strip with no second textarea in narrator mode", () => {
    // Two empty boxes would make a new player guess which one is "the scene". The strip
    // answers that in words instead: there is still exactly one text input on screen.
    render(<DirectionRow mode="narrator" value="" onChange={() => {}} />);
    expect(screen.getByText(/direction/i)).toBeInTheDocument();
    expect(screen.getByText(/this message steers the scene/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("expands into a labelled direction box under POV, naming who speaks below", () => {
    render(<DirectionRow mode="pov" value="" onChange={() => {}} povName="Mei" />);
    const box = screen.getByRole("textbox", { name: /scene direction/i });
    expect(box).toBeInTheDocument();
    expect(screen.getByText(/Mei speaks below/)).toBeInTheDocument();
  });

  it("names the character generically when the POV name is unknown", () => {
    render(<DirectionRow mode="pov" value="" onChange={() => {}} />);
    expect(screen.getByText(/your character speaks below/i)).toBeInTheDocument();
  });

  it("writes the value exactly once and still runs the composer's side-effects", () => {
    // Two writers of one value is the bug this composition exists to avoid.
    const onChange = vi.fn();
    const sideEffect = vi.fn();
    render(
      <DirectionRow
        mode="pov"
        value=""
        onChange={onChange}
        textareaProps={{ onChange: sideEffect }}
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: /scene direction/i }), {
      target: { value: "make it worse" },
    });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("make it worse");
    expect(sideEffect).toHaveBeenCalledTimes(1);
  });

  it("renders the verb-bar slot in both modes", () => {
    const { rerender } = render(
      <DirectionRow mode="narrator" value="" onChange={() => {}}>
        <span>verbs</span>
      </DirectionRow>,
    );
    expect(screen.getByText("verbs")).toBeInTheDocument();
    rerender(
      <DirectionRow mode="pov" value="" onChange={() => {}}>
        <span>verbs</span>
      </DirectionRow>,
    );
    expect(screen.getByText("verbs")).toBeInTheDocument();
  });
});
