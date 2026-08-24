import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanApproval } from "./PlanApproval";
import type { PlannedBeat } from "@/lib/events";

const BEATS: PlannedBeat[] = [
  {
    action: "speak",
    actorId: "c_lily",
    actorName: "Lily",
    addressingId: null,
    reason: "she is not going to let that stand",
    register: "tense",
    stakes: "the debt",
    status: null,
  },
  {
    action: "narrate",
    actorId: null,
    actorName: "",
    addressingId: null,
    reason: "the door opens",
    register: null,
    stakes: "",
    status: null,
  },
];

describe("PlanApproval", () => {
  it("names who acts, using the name the server resolved", () => {
    // The panel must not have to join against the cast to draw a row — it would render
    // "unknown" the first time presence changed.
    render(<PlanApproval beats={BEATS} onApprove={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText("Lily")).toBeInTheDocument();
    expect(screen.getByText(/she is not going to let that stand/i)).toBeInTheDocument();
  });

  it("falls back to Narrator for a beat with no actor", () => {
    render(<PlanApproval beats={BEATS} onApprove={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText("Narrator")).toBeInTheDocument();
  });

  it("shows the register, which is the thing most worth arguing with", () => {
    render(<PlanApproval beats={BEATS} onApprove={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText(/tense/i)).toBeInTheDocument();
  });

  it("says plainly that nothing has been written yet", () => {
    // The whole promise of the panel. A player who thinks the scene has already committed
    // will approve rather than edit, which defeats the feature.
    render(<PlanApproval beats={BEATS} onApprove={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText(/nothing written yet/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing has been written either way/i)).toBeInTheDocument();
  });

  it("announces itself, because it arrives after the player has looked away", () => {
    render(<PlanApproval beats={BEATS} onApprove={vi.fn()} onDismiss={vi.fn()} />);
    const panel = screen.getByRole("region", { name: /the plan for this turn/i });
    expect(panel).toHaveAttribute("aria-live", "polite");
  });

  it("offers approving and changing, and reports each", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onDismiss = vi.fn();
    render(<PlanApproval beats={BEATS} onApprove={onApprove} onDismiss={onDismiss} />);

    await user.click(screen.getByRole("button", { name: /play it out/i }));
    expect(onApprove).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: /change it/i }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("renders nothing for an empty plan", () => {
    // A plan with no beats is nothing to approve, and an empty panel over the composer is
    // worse than none.
    const { container } = render(
      <PlanApproval beats={[]} onApprove={vi.fn()} onDismiss={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("disables both actions while the approved turn is running", async () => {
    render(<PlanApproval beats={BEATS} onApprove={vi.fn()} onDismiss={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: /play it out/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /change it/i })).toBeDisabled();
  });

  it("shows intent, never prose", () => {
    // Approving a plan approves who acts and what they are trying to do; the writing still
    // happens fresh. A drafted line here would quietly turn approval into dictation.
    render(<PlanApproval beats={BEATS} onApprove={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.queryByText(/"/)).toBeNull();
  });
});
