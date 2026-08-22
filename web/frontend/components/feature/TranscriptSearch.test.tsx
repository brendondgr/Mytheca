import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TranscriptSearch } from "./TranscriptSearch";

function setup(over: Partial<React.ComponentProps<typeof TranscriptSearch>> = {}) {
  const props = {
    query: "",
    onQueryChange: vi.fn(),
    current: 0,
    total: 0,
    onStep: vi.fn(),
    onClose: vi.fn(),
    ...over,
  };
  render(<TranscriptSearch {...props} />);
  return props;
}

describe("TranscriptSearch", () => {
  it("is a labelled search region with a focused field", () => {
    setup();
    expect(screen.getByRole("search", { name: /search this scene/i })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: /find in this scene/i })).toHaveFocus();
  });

  it("announces the match count in a live region", () => {
    // Without it a screen-reader user pressing next has no way to know anything moved — the
    // count IS the feedback loop of a search.
    setup({ query: "lamp", current: 2, total: 17 });
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("3 of 17");
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("says so plainly when nothing matched", () => {
    setup({ query: "zzz", total: 0 });
    expect(screen.getByRole("status")).toHaveTextContent(/no matches/i);
  });

  it("invites a query before one is typed", () => {
    setup();
    expect(screen.getByRole("status")).toHaveTextContent(/type to search/i);
  });

  it("steps forward and back", () => {
    const props = setup({ query: "lamp", total: 3 });
    fireEvent.click(screen.getByRole("button", { name: "Next match" }));
    expect(props.onStep).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "Previous match" }));
    expect(props.onStep).toHaveBeenCalledWith(-1);
  });

  it("steps with Enter and Shift+Enter", () => {
    const props = setup({ query: "lamp", total: 3 });
    const box = screen.getByRole("searchbox");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(props.onStep).toHaveBeenCalledWith(1);
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(props.onStep).toHaveBeenCalledWith(-1);
  });

  it("disables the steppers when there is nothing to step through", () => {
    setup({ query: "zzz", total: 0 });
    expect(screen.getByRole("button", { name: "Next match" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous match" })).toBeDisabled();
  });

  it("closes on Escape and by button", () => {
    const props = setup();
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Escape" });
    expect(props.onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(props.onClose).toHaveBeenCalledTimes(2);
  });
});
