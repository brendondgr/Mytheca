import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SceneVerbBar } from "./SceneVerbBar";
import type { SceneVerb } from "@/lib/sceneVerbs";

const VERBS: SceneVerb[] = [
  { id: "push", group: "pace", label: "Push it forward", text: "Move this along." },
  { id: "slow", group: "pace", label: "Slow down", text: "Stay in this moment." },
  { id: "escalate", group: "tone", label: "Escalate", text: "Something makes this worse." },
  { id: "arrives", group: "event", label: "Someone arrives", text: "", expands: "cast" },
];

describe("SceneVerbBar", () => {
  it("is a toolbar of labelled groups, not a flat row", () => {
    render(<SceneVerbBar verbs={VERBS} onVerb={() => {}} />);
    expect(screen.getByRole("toolbar", { name: "Direction" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Pace" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Tone" })).toBeInTheDocument();
  });

  it("omits a group with nothing in it", () => {
    render(<SceneVerbBar verbs={[VERBS[0]]} onVerb={() => {}} />);
    expect(screen.queryByRole("group", { name: "Tone" })).not.toBeInTheDocument();
  });

  it("takes exactly one tab stop, however many verbs there are", () => {
    // Fifteen chips at one tab stop each would put fifteen presses between the composer and
    // the Send button — worse for a keyboard user than not having the bar at all.
    render(<SceneVerbBar verbs={VERBS} onVerb={() => {}} />);
    const tabbable = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("tabindex") === "0");
    expect(tabbable).toHaveLength(1);
    expect(tabbable[0]).toHaveTextContent("Push it forward");
  });

  it("moves between verbs with the arrow keys, wrapping, and across group boundaries", () => {
    render(<SceneVerbBar verbs={VERBS} onVerb={() => {}} />);
    const first = screen.getByRole("button", { name: "Push it forward" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("button", { name: "Slow down" })).toHaveFocus();
    // The next Right crosses from Pace into Tone — the roving index is flat.
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(screen.getByRole("button", { name: "Escalate" })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(screen.getByRole("button", { name: "Slow down" })).toHaveFocus();
  });

  it("jumps to the ends with Home and End", () => {
    render(<SceneVerbBar verbs={VERBS} onVerb={() => {}} />);
    const first = screen.getByRole("button", { name: "Push it forward" });
    first.focus();
    fireEvent.keyDown(first, { key: "End" });
    expect(screen.getByRole("button", { name: "Someone arrives" })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(first).toHaveFocus();
  });

  it("wraps from the last verb back to the first", () => {
    render(<SceneVerbBar verbs={VERBS} onVerb={() => {}} />);
    const last = screen.getByRole("button", { name: "Someone arrives" });
    last.focus();
    fireEvent.keyDown(last, { key: "ArrowRight" });
    expect(screen.getByRole("button", { name: "Push it forward" })).toHaveFocus();
  });

  it("inserts the phrasing, not the label", () => {
    const onVerb = vi.fn();
    render(<SceneVerbBar verbs={VERBS} onVerb={onVerb} />);
    fireEvent.click(screen.getByRole("button", { name: "Escalate" }));
    expect(onVerb).toHaveBeenCalledWith("Something makes this worse.");
  });

  it("expands rather than inserting for a verb that names people", () => {
    const onVerb = vi.fn();
    const onExpandCast = vi.fn();
    render(<SceneVerbBar verbs={VERBS} onVerb={onVerb} onExpandCast={onExpandCast} />);
    fireEvent.click(screen.getByRole("button", { name: "Someone arrives" }));
    expect(onExpandCast).toHaveBeenCalledTimes(1);
    expect(onVerb).not.toHaveBeenCalled();
  });

  it("renders nothing when every verb is gated out", () => {
    const { container } = render(<SceneVerbBar verbs={[]} onVerb={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("disables the verbs while a turn is in flight", () => {
    render(<SceneVerbBar verbs={VERBS} onVerb={() => {}} disabled />);
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});
