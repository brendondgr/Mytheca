import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProcessProgress, type ProcessStep } from "./ProcessProgress";

const STEPS: ProcessStep[] = [
  { key: "identity", label: "Identity" },
  { key: "voice", label: "Voice" },
  { key: "stats", label: "Stats" },
];

describe("ProcessProgress", () => {
  it("marks earlier steps done, the active step active, later pending", () => {
    render(<ProcessProgress steps={STEPS} activeKey="voice" />);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveAttribute("data-state", "done");
    expect(items[1]).toHaveAttribute("data-state", "active");
    expect(items[2]).toHaveAttribute("data-state", "pending");
  });

  it("shows the current and next step in the status line", () => {
    render(<ProcessProgress steps={STEPS} activeKey="identity" />);
    const status = screen.getByText(/Now:/);
    expect(status).toHaveTextContent("Now: Identity");
    expect(status).toHaveTextContent("Next: Voice");
  });

  it("omits Next on the last step", () => {
    render(<ProcessProgress steps={STEPS} activeKey="stats" />);
    expect(screen.getByText(/Now:/)).toHaveTextContent("Now: Stats");
    expect(screen.queryByText(/Next:/)).not.toBeInTheDocument();
  });

  it("renders the completed state when done", () => {
    render(<ProcessProgress steps={STEPS} activeKey={null} done />);
    expect(screen.getByText("Complete")).toBeInTheDocument();
    for (const item of screen.getAllByRole("listitem")) {
      expect(item).toHaveAttribute("data-state", "done");
    }
  });

  it("exposes an accessible group label", () => {
    render(<ProcessProgress steps={STEPS} activeKey="voice" label="Build" />);
    expect(screen.getByRole("group", { name: "Build" })).toBeInTheDocument();
  });
});
