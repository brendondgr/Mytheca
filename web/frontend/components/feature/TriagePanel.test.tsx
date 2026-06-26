import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
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

describe("TriagePanel self-triage", () => {
  it("fresh docs show 'Select' as the default category option", () => {
    const docs = [toCreatorDoc({ name: "hero.md", text: "A person." })];
    render(<TriagePanel {...baseProps} docs={docs} triaging={false} />);
    const select = screen.getByRole("combobox", { name: /category for hero\.md/i });
    expect(select).toHaveValue("select");
    // All four options are present in the right order.
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual(["select", "character", "other", "setting"]);
  });

  it("calls onSetCategory when the user picks a category manually", async () => {
    const user = userEvent.setup();
    const onSetCategory = vi.fn();
    const docs = [toCreatorDoc({ name: "hero.md", text: "A person." })];
    render(
      <TriagePanel {...baseProps} docs={docs} triaging={false} onSetCategory={onSetCategory} />,
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: /category for hero\.md/i }),
      "character",
    );
    expect(onSetCategory).toHaveBeenCalledWith("hero.md", "character");
  });

  it("switches to grouped view once a doc is manually categorized", () => {
    const categorized = { ...toCreatorDoc({ name: "hero.md", text: "A person." }), category: "character" as const };
    const uncategorized = toCreatorDoc({ name: "place.md", text: "A place." });
    render(<TriagePanel {...baseProps} docs={[categorized, uncategorized]} triaging={false} />);
    // The categorized doc appears under "Characters".
    expect(screen.getByText(/character details/i)).toBeInTheDocument();
    // The still-uncategorized doc appears under "Uncategorized".
    expect(screen.getByText(/not yet categorized/i)).toBeInTheDocument();
  });
});
