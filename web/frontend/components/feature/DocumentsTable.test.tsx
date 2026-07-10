import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { DocumentsTable } from "./DocumentsTable";
import type { ContextDocument } from "@/lib/types";

const DOC: ContextDocument = {
  id: "cd1",
  storylineId: "embergate",
  name: "maerin.md",
  content: "A wary harbor smuggler.",
  category: "character",
  includeDraft: false,
  includeRag: true,
  includeExtract: false,
  source: "upload",
  charCount: 23,
  entityType: null,
  entityId: null,
  links: [{ id: "l1", entityType: "character", entityId: "maerin" }],
};

function setup(doc: ContextDocument = DOC) {
  const onUpdate = vi.fn();
  const onRemove = vi.fn();
  const entityLabel = (t: string, id: string) => (id === "maerin" ? "Maerin Voss" : id);
  render(
    <DocumentsTable docs={[doc]} entityLabel={entityLabel} onUpdate={onUpdate} onRemove={onRemove} />,
  );
  return { onUpdate, onRemove };
}

describe("DocumentsTable", () => {
  it("toggling a usage flag patches the doc", async () => {
    const user = userEvent.setup();
    const { onUpdate } = setup();
    await user.click(screen.getByRole("button", { name: /draft for maerin\.md/i }));
    expect(onUpdate).toHaveBeenCalledWith("cd1", { includeDraft: true });
  });

  it("changing the category patches the doc", async () => {
    const user = userEvent.setup();
    const { onUpdate } = setup();
    await user.selectOptions(screen.getByLabelText(/category for maerin\.md/i), "setting");
    expect(onUpdate).toHaveBeenCalledWith("cd1", { category: "setting" });
  });

  it("shows the entities a doc is provenance for", () => {
    setup();
    // The link renders the entity's resolved name (context for: Maerin Voss).
    expect(screen.getByText("Maerin Voss")).toBeInTheDocument();
  });

  it("labels an entity-owned doc's scope", () => {
    setup({ ...DOC, links: [], entityType: "character", entityId: "maerin" });
    expect(screen.getByText(/owned by maerin voss/i)).toBeInTheDocument();
  });

  it("deletes a document", async () => {
    const user = userEvent.setup();
    const { onRemove } = setup();
    await user.click(screen.getByRole("button", { name: /delete maerin\.md/i }));
    expect(onRemove).toHaveBeenCalledWith("cd1");
  });

  it("expands to view the document contents", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /view contents of maerin\.md/i }));
    expect(screen.getByText("A wary harbor smuggler.")).toBeInTheDocument();
  });
});
