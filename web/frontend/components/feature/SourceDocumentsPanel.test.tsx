import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SourceDocumentsPanel } from "./SourceDocumentsPanel";
import * as api from "@/lib/api";
import type { ContextDocument } from "@/lib/types";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

function doc(over: Partial<ContextDocument>): ContextDocument {
  return {
    id: "cd", storylineId: "embergate", name: "doc.md", content: "", category: "other",
    includeDraft: false, includeRag: true, includeExtract: false, source: "upload",
    charCount: 0, entityType: null, entityId: null, links: [], ...over,
  };
}

const LINKED = [doc({ id: "cd1", name: "maerin.md", category: "character" })];
const CORPUS = [
  doc({ id: "cd1", name: "maerin.md", category: "character" }),
  doc({ id: "cd2", name: "lore.md", category: "other" }),
];

beforeEach(() => {
  vi.mocked(api.listContextDocuments).mockImplementation(async (_sl, scope) =>
    scope?.linkedEntityType ? LINKED : CORPUS,
  );
});

describe("SourceDocumentsPanel", () => {
  it("lists the documents linked to the entity", async () => {
    render(<SourceDocumentsPanel storylineId="embergate" entityType="character" entityId="maerin" />);
    expect(await screen.findByText(/maerin\.md/)).toBeInTheDocument();
  });

  it("unlinks a linked document", async () => {
    const user = userEvent.setup();
    render(<SourceDocumentsPanel storylineId="embergate" entityType="character" entityId="maerin" />);
    await screen.findByText(/maerin\.md/);
    await user.click(screen.getByRole("button", { name: /unlink maerin\.md/i }));
    expect(api.removeDocumentLink).toHaveBeenCalledWith("cd1", {
      entityType: "character",
      entityId: "maerin",
    });
  });

  it("links an unlinked corpus document via the picker", async () => {
    const user = userEvent.setup();
    render(<SourceDocumentsPanel storylineId="embergate" entityType="character" entityId="maerin" />);
    await screen.findByText(/maerin\.md/);
    // Only lore.md (not already linked) is offered as an option.
    await user.selectOptions(screen.getByLabelText(/link a document to this character/i), "cd2");
    await user.click(screen.getByRole("button", { name: /^link$/i }));
    await waitFor(() =>
      expect(api.addDocumentLink).toHaveBeenCalledWith("cd2", {
        entityType: "character",
        entityId: "maerin",
      }),
    );
  });

  it("shows an empty state when nothing is linked", async () => {
    vi.mocked(api.listContextDocuments).mockResolvedValue([]);
    render(<SourceDocumentsPanel storylineId="embergate" entityType="setting" entityId="chapel" />);
    expect(await screen.findByText(/no documents linked yet/i)).toBeInTheDocument();
  });
});
