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

describe("TriagePanel upload disclosure", () => {
  /** A panel with documents, so the Draft strip is on screen too. */
  function renderPanel() {
    return render(
      <TriagePanel
        {...baseProps}
        docs={[toCreatorDoc({ name: "a.md", text: "x" })]}
        triaging={false}
        onSetAllUse={noop}
      />,
    );
  }

  /**
   * The stacked layout gave the document list ~34px of scroll at 320×720, because the sticky
   * header was ~230px of a 42dvh strip. The setup half now collapses below `lg`; what a
   * player *scans* or reaches for stays put.
   */
  it("collapses the upload setup by default and says so", () => {
    renderPanel();
    const toggle = screen.getByRole("button", { name: /add files/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls");
  });

  it("keeps Browse files, Triage and the Draft strip reachable with nothing expanded", () => {
    // `Browse files` is the keyboard alternative to dragging. An alternative gated behind a
    // disclosure — and behind an animation — is not an alternative.
    renderPanel();
    expect(screen.getByText("Browse files")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /triage/i })).toBeInTheDocument();
    expect(screen.getByText(/de-select all|re-select all/i)).toBeInTheDocument();
  });

  it("keeps the file input associated with its label across the move", () => {
    // Both moved out of the drop zone together — splitting an `htmlFor` pair across a
    // collapsed region is how a label stops labelling anything.
    const { container } = renderPanel();
    const label = screen.getByText("Browse files") as HTMLLabelElement;
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    expect(label.htmlFor).toBe(input.id);
    expect(input.className).toContain("sr-only");
  });

  it("reveals the upload target when expanded, and updates aria-expanded", async () => {
    const user = userEvent.setup();
    renderPanel();
    const toggle = screen.getByRole("button", { name: /add files/i });

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Add as")).toBeInTheDocument();
    expect(screen.getByText(/drag/i)).toBeInTheDocument();
  });

  it("takes the collapsed controls out of the tab order, not just out of sight", async () => {
    // `overflow-hidden` at `0fr` clips them visually and leaves them focusable; a keyboard
    // user would land on a select that is not on screen.
    const user = userEvent.setup();
    renderPanel();
    const region = document.getElementById(
      screen.getByRole("button", { name: /add files/i }).getAttribute("aria-controls")!,
    )!;
    const inner = region.firstElementChild!;
    expect(inner.className).toContain("invisible");
    expect(inner.className).toContain("lg:visible");

    await user.click(screen.getByRole("button", { name: /add files/i }));
    expect(region.firstElementChild!.className).toContain("visible");
    expect(region.firstElementChild!.className).not.toContain("invisible");
  });

  it("is forced open at lg and up, in CSS — no media query, no hydration swap", () => {
    renderPanel();
    const region = document.getElementById(
      screen.getByRole("button", { name: /add files/i }).getAttribute("aria-controls")!,
    )!;
    expect(region.className).toContain("lg:grid-rows-[1fr]");
    expect(screen.getByRole("button", { name: /add files/i }).className).toContain("lg:hidden");
  });
});
