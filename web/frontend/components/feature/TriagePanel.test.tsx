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

  it("shows the idle Triage action (scoped to Uncategorized) when not triaging", () => {
    render(<TriagePanel {...baseProps} docs={docs} triaging={false} />);
    // Both docs are Uncategorized → the button offers to triage just those.
    expect(
      screen.getByRole("button", { name: /triage uncategorized \(2\)/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/classifying/i)).not.toBeInTheDocument();
  });

  it("disables Triage when every doc is already categorized", () => {
    const categorized = [
      { ...toCreatorDoc({ name: "a.md", text: "x" }, { category: "character" }) },
      { ...toCreatorDoc({ name: "b.md", text: "y" }, { category: "setting" }) },
    ];
    render(<TriagePanel {...baseProps} docs={categorized} triaging={false} />);
    expect(screen.getByRole("button", { name: /triage context/i })).toBeDisabled();
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

  it("passes the chosen upload target (category + Draft/RAG) to onAddFiles via Browse", async () => {
    const user = userEvent.setup();
    const onAddFiles = vi.fn();
    render(<TriagePanel {...baseProps} docs={[]} triaging={false} onAddFiles={onAddFiles} />);
    // Pick "Character" as the upload target and flip the Draft default on.
    await user.selectOptions(screen.getByRole("combobox", { name: /add as/i }), "character");
    await user.click(screen.getByRole("button", { name: /default draft for uploads/i }));
    // Browse a file → it carries the chosen target.
    const input = document.getElementById("creator-docs-input") as HTMLInputElement;
    await user.upload(input, new File(["A hero."], "hero.md", { type: "text/plain" }));
    expect(onAddFiles).toHaveBeenCalledTimes(1);
    const opts = onAddFiles.mock.calls[0][1];
    expect(opts).toEqual({ category: "character", useDraft: true, useRag: true });
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
