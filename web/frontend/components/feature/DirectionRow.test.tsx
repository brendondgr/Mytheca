import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DirectionRow } from "./DirectionRow";

describe("DirectionRow", () => {
  it("is a labelled strip with no second textarea in Playwright mode", () => {
    // Two empty boxes would make a new player guess which one is "the scene". The strip
    // answers that in words instead: there is still exactly one text input on screen.
    render(<DirectionRow mode="playwright" value="" onChange={() => {}} />);
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

  it("renders the verb-bar slot in both modes, once opened", () => {
    const { rerender } = render(
      <DirectionRow mode="playwright" value="" onChange={() => {}}>
        <span>verbs</span>
      </DirectionRow>,
    );
    // The slot is behind the disclosure now; the property under test is that the ROW carries
    // it in both modes, not that it is open.
    fireEvent.click(screen.getByRole("button", { name: /verbs/i }));
    expect(screen.getByText("verbs")).toBeInTheDocument();
    rerender(
      <DirectionRow mode="pov" value="" onChange={() => {}}>
        <span>verbs</span>
      </DirectionRow>,
    );
    expect(screen.getByText("verbs")).toBeInTheDocument();
  });
});

describe("the verb disclosure", () => {
  beforeEach(() => window.localStorage.clear());

  it("is closed by default — the verbs do not sit in every scene", () => {
    render(
      <DirectionRow mode="playwright" value="" onChange={() => {}}>
        <button type="button">Push it forward</button>
      </DirectionRow>,
    );
    expect(screen.getByRole("button", { name: /verbs/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByRole("button", { name: "Push it forward" })).toBeNull();
  });

  it("unmounts the bar when closed, so its chips leave the tab order", async () => {
    const user = userEvent.setup();
    render(
      <DirectionRow mode="playwright" value="" onChange={() => {}}>
        <button type="button">Push it forward</button>
      </DirectionRow>,
    );
    const toggle = screen.getByRole("button", { name: /verbs/i });
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Push it forward" })).toBeInTheDocument();
    await user.click(toggle);
    // Not merely hidden: a collapsed toolbar that still takes focus is worse than none.
    expect(screen.queryByRole("button", { name: "Push it forward" })).toBeNull();
  });

  it("remembers being opened, so a player who wants the verbs keeps them", async () => {
    const user = userEvent.setup();
    const { unmount } = render(
      <DirectionRow mode="playwright" value="" onChange={() => {}}>
        <button type="button">Push it forward</button>
      </DirectionRow>,
    );
    await user.click(screen.getByRole("button", { name: /verbs/i }));
    unmount();

    render(
      <DirectionRow mode="playwright" value="" onChange={() => {}}>
        <button type="button">Push it forward</button>
      </DirectionRow>,
    );
    expect(
      await screen.findByRole("button", { name: "Push it forward" }),
    ).toBeInTheDocument();
  });

  it("shows no disclosure at all when there are no verbs to offer", () => {
    render(<DirectionRow mode="playwright" value="" onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: /verbs/i })).toBeNull();
  });
});
