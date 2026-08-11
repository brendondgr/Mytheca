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

  it("passes the chosen upload target (category + Draft/RAG/Extract) to onAddFiles via Browse", async () => {
    const user = userEvent.setup();
    const onAddFiles = vi.fn();
    render(<TriagePanel {...baseProps} docs={[]} triaging={false} onAddFiles={onAddFiles} />);
    // Pick "Character" as the upload target and flip the Extract default on (Draft and
    // RAG are already on by default).
    await user.selectOptions(screen.getByRole("combobox", { name: /add as/i }), "character");
    await user.click(screen.getByRole("button", { name: /default extract for uploads/i }));
    // Browse a file → it carries the chosen target.
    const input = document.getElementById("creator-docs-input") as HTMLInputElement;
    await user.upload(input, new File(["A hero."], "hero.md", { type: "text/plain" }));
    expect(onAddFiles).toHaveBeenCalledTimes(1);
    const opts = onAddFiles.mock.calls[0][1];
    // Extract defaults OFF (opt-in); flipping it on rides the upload target.
    expect(opts).toEqual({ category: "character", useDraft: true, useRag: true, useExtract: true });
  });

  it("renders a per-row Extract chip and toggles useExtract when clicked", async () => {
    const user = userEvent.setup();
    const onToggleUse = vi.fn();
    const docs = [toCreatorDoc({ name: "hero.md", text: "A hero." })];
    render(
      <TriagePanel {...baseProps} docs={docs} triaging={false} onToggleUse={onToggleUse} />,
    );
    await user.click(screen.getByRole("button", { name: /extract for hero\.md/i }));
    expect(onToggleUse).toHaveBeenCalledWith("hero.md", "useExtract");
  });

  it("offers De-select All while any doc grounds the draft, and clears them in one click", async () => {
    const user = userEvent.setup();
    const onSetAllUse = vi.fn();
    const docs = [
      toCreatorDoc({ name: "a.md", text: "x" }),
      toCreatorDoc({ name: "b.md", text: "y" }),
    ];
    render(
      <TriagePanel {...baseProps} docs={docs} triaging={false} onSetAllUse={onSetAllUse} />,
    );
    expect(screen.getByText("2/2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /de-select all/i }));
    expect(onSetAllUse).toHaveBeenCalledWith("useDraft", false);
  });

  it("offers Re-select All once nothing grounds the draft", async () => {
    const user = userEvent.setup();
    const onSetAllUse = vi.fn();
    const docs = [
      toCreatorDoc({ name: "a.md", text: "x" }, { useDraft: false }),
      toCreatorDoc({ name: "b.md", text: "y" }, { useDraft: false }),
    ];
    render(
      <TriagePanel {...baseProps} docs={docs} triaging={false} onSetAllUse={onSetAllUse} />,
    );
    expect(screen.getByText("0/2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /re-select all/i }));
    expect(onSetAllUse).toHaveBeenCalledWith("useDraft", true);
  });

  it("hides the bulk Draft control while there are no docs", () => {
    render(<TriagePanel {...baseProps} docs={[]} triaging={false} />);
    expect(screen.queryByRole("button", { name: /select all/i })).not.toBeInTheDocument();
  });

  it("keeps the doc list inside its own scroll container", () => {
    // Regression: every DocRow renders an `sr-only` label, and `sr-only` is
    // `position: absolute`. Without a positioned ancestor those labels resolve
    // against the initial containing block, escape the page shell's
    // `overflow-hidden`, and grow the ROOT scroller by the full list height —
    // measured at 6212px of blank page for 28 files in a 720px viewport. jsdom
    // has no layout, so the invariant is asserted structurally.
    const docs = [toCreatorDoc({ name: "hero.md", text: "A person." })];
    const { container } = render(<TriagePanel {...baseProps} docs={docs} triaging={false} />);
    const label = container.querySelector("label.sr-only");
    expect(label).not.toBeNull();
    const scroller = label!.closest(".overflow-y-auto");
    expect(scroller).not.toBeNull();
    expect(scroller).toHaveClass("relative");
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
