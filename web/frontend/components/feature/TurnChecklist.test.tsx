import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TurnChecklist } from "./TurnChecklist";
import type { TurnTask } from "@/lib/events";

const task = (over: Partial<TurnTask> = {}): TurnTask => ({
  n: 1,
  must: "Valdar refuses to name the buyer",
  who: [],
  state: "",
  note: "",
  ...over,
});

describe("TurnChecklist", () => {
  it("renders nothing outside free-text mode, which is most scenes", () => {
    const { container } = render(<TurnChecklist tasks={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows what the turn owes before any of it has been graded", () => {
    render(<TurnChecklist tasks={[task()]} />);
    expect(screen.getByText(/Valdar refuses to name the buyer/)).toBeInTheDocument();
    expect(screen.getByText(/1 thing to do, not yet checked/)).toBeInTheDocument();
  });

  it("distinguishes all four states in words, never by colour alone", () => {
    render(
      <TurnChecklist
        tasks={[
          task({ n: 1, must: "landed", state: "yes" }),
          task({ n: 2, must: "half done", state: "partial" }),
          task({ n: 3, must: "missing", state: "no" }),
          task({ n: 4, must: "not yet graded", state: "" }),
        ]}
      />,
    );
    expect(screen.getByText("started, not finished")).toBeInTheDocument();
    expect(screen.getByText("not on the page")).toBeInTheDocument();
    // "yes" and "" carry no note — the glyph and the ungraded/graded count say it.
    expect(screen.getByText(/1 of 4 delivered/)).toBeInTheDocument();
  });

  it("names who is involved without implying an order of speaking", () => {
    render(<TurnChecklist tasks={[task({ who: ["Mei", "Valdar"] })]} />);
    expect(screen.getByText("Mei · Valdar")).toBeInTheDocument();
  });

  it("keys rows on the task number so a second frame updates in place", () => {
    const { rerender } = render(<TurnChecklist tasks={[task()]} />);
    rerender(<TurnChecklist tasks={[task({ state: "yes" })]} />);
    // One row, not two: the review frame replaces the checklist frame rather than stacking.
    expect(screen.getAllByText(/Valdar refuses to name the buyer/)).toHaveLength(1);
  });

  it("can be told not to announce, for a sheet that mounts on open", () => {
    const { container } = render(<TurnChecklist tasks={[task()]} live={false} />);
    expect(container.querySelector('[aria-live="off"]')).toBeInTheDocument();
  });
});
