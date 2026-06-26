import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TriagePanel } from "./TriagePanel";
import { toCreatorDoc } from "@/features/library/storylineCreator";
import { budgetFor } from "@/lib/contextBudget";

const noop = () => {};
const baseProps = {
  onAddFiles: noop,
  onRemove: noop,
  onToggleUse: noop,
  onSetCategory: noop,
  onTriage: noop,
  budget: budgetFor({}),
};

describe("TriagePanel live triage", () => {
  const docs = [toCreatorDoc({ name: "a.md", text: "x" }), toCreatorDoc({ name: "b.md", text: "y" })];

  it("marks the in-flight file and shows per-file progress while triaging", () => {
    render(
      <TriagePanel
        {...baseProps}
        docs={docs}
        triaging
        triageActive={{ name: "a.md", index: 0, total: 2 }}
      />,
    );
    // The Triage button reflects the per-file progress…
    expect(screen.getByRole("button", { name: /triaging 1\/2…/i })).toBeInTheDocument();
    // …a live status names the in-flight file…
    expect(screen.getByText(/classifying a\.md…/i)).toBeInTheDocument();
    // …and the active row shows the "classifying…" badge.
    expect(screen.getByText(/^classifying…$/i)).toBeInTheDocument();
  });

  it("shows the idle Triage action when not triaging", () => {
    render(<TriagePanel {...baseProps} docs={docs} triaging={false} />);
    expect(screen.getByRole("button", { name: /triage context/i })).toBeInTheDocument();
    expect(screen.queryByText(/classifying/i)).not.toBeInTheDocument();
  });
});
