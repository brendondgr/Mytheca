import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DocumentsView } from "./DocumentsView";
import * as api from "@/lib/api";
import type { ContextDocument } from "@/lib/types";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

function doc(over: Partial<ContextDocument>): ContextDocument {
  return {
    id: "cd1",
    storylineId: "embergate",
    name: "doc.md",
    content: "",
    category: "other",
    includeDraft: false,
    includeRag: true,
    includeExtract: false,
    source: "upload",
    charCount: 0,
    entityType: null,
    entityId: null,
    links: [],
    ...over,
  };
}

const DOCS: ContextDocument[] = [
  doc({ id: "cd1", name: "maerin.md", category: "character", content: "smuggler" }),
  doc({ id: "cd2", name: "chapel.md", category: "setting", content: "sunken shrine" }),
  doc({ id: "cd3", name: "lore.md", category: "other", content: "founding wars" }),
];

beforeEach(() => {
  vi.mocked(api.listContextDocuments).mockResolvedValue(DOCS);
});

describe("DocumentsView", () => {
  it("lists every uploaded document grouped by category", async () => {
    render(<DocumentsView storylineId="embergate" />);
    expect(await screen.findByText("maerin.md")).toBeInTheDocument();
    expect(screen.getByText("chapel.md")).toBeInTheDocument();
    expect(screen.getByText("lore.md")).toBeInTheDocument();
    expect(screen.getByText(/3 of 3 documents/i)).toBeInTheDocument();
  });

  it("filters by search query", async () => {
    const user = userEvent.setup();
    render(<DocumentsView storylineId="embergate" />);
    await screen.findByText("maerin.md");
    await user.type(screen.getByLabelText(/search documents/i), "chapel");
    await waitFor(() => expect(screen.queryByText("maerin.md")).not.toBeInTheDocument());
    expect(screen.getByText("chapel.md")).toBeInTheDocument();
  });

  it("filters by category", async () => {
    const user = userEvent.setup();
    render(<DocumentsView storylineId="embergate" />);
    await screen.findByText("maerin.md");
    await user.click(screen.getByRole("button", { name: /^settings$/i }));
    await waitFor(() => expect(screen.queryByText("maerin.md")).not.toBeInTheDocument());
    expect(screen.getByText("chapel.md")).toBeInTheDocument();
  });

  it("persists a usage-flag toggle via updateContextDocument", async () => {
    const user = userEvent.setup();
    render(<DocumentsView storylineId="embergate" />);
    await screen.findByText("maerin.md");
    await user.click(screen.getByRole("button", { name: /extract for maerin\.md/i }));
    expect(api.updateContextDocument).toHaveBeenCalledWith("cd1", { includeExtract: true });
  });

  it("deletes a document via deleteContextDocument", async () => {
    const user = userEvent.setup();
    render(<DocumentsView storylineId="embergate" />);
    await screen.findByText("lore.md");
    await user.click(screen.getByRole("button", { name: /delete lore\.md/i }));
    expect(api.deleteContextDocument).toHaveBeenCalledWith("cd3");
    await waitFor(() => expect(screen.queryByText("lore.md")).not.toBeInTheDocument());
  });

  it("shows the empty state when no documents exist", async () => {
    vi.mocked(api.listContextDocuments).mockResolvedValueOnce([]);
    render(<DocumentsView storylineId="embergate" />);
    expect(await screen.findByText(/no documents uploaded to this world yet/i)).toBeInTheDocument();
  });
});
