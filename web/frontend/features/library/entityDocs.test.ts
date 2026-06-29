import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "@/lib/api";
import { loadEntityDocs, syncEntityDocs } from "./entityDocs";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());
beforeEach(() => vi.clearAllMocks());

function doc(over: Record<string, unknown> = {}) {
  return {
    id: "cd1", storylineId: "w1", name: "a.md", content: "x", category: "character",
    includeDraft: false, includeRag: true, source: "upload", charCount: 1, ...over,
  };
}

describe("entityDocs", () => {
  it("loadEntityDocs maps persisted docs to ReadDoc carrying their ids", async () => {
    vi.mocked(api.listContextDocuments).mockResolvedValueOnce([
      doc({ id: "cd1", name: "a.md", content: "alpha", includeDraft: true }),
    ]);
    const res = await loadEntityDocs("w1", "character", "c1");
    expect(api.listContextDocuments).toHaveBeenCalledWith("w1", { entityType: "character", entityId: "c1" });
    expect(res).toEqual([{ id: "cd1", name: "a.md", text: "alpha", useDraft: true, useRag: true }]);
  });

  it("syncEntityDocs creates new drops scoped to the entity", async () => {
    vi.mocked(api.listContextDocuments).mockResolvedValueOnce([]);
    await syncEntityDocs("w1", "setting", "s1", [{ name: "new.md", text: "hi", useRag: true }]);
    expect(api.bulkCreateContextDocuments).toHaveBeenCalledWith("w1", [
      expect.objectContaining({ name: "new.md", entityType: "setting", entityId: "s1", category: "setting" }),
    ]);
    expect(api.deleteContextDocument).not.toHaveBeenCalled();
  });

  it("syncEntityDocs deletes docs the author removed (pruning embeddings)", async () => {
    vi.mocked(api.listContextDocuments).mockResolvedValueOnce([doc({ id: "cdX", name: "gone.md" })]);
    await syncEntityDocs("w1", "character", "c1", []);
    expect(api.deleteContextDocument).toHaveBeenCalledWith("cdX");
    expect(api.bulkCreateContextDocuments).not.toHaveBeenCalled();
  });

  it("syncEntityDocs is a no-op when the panel matches the stored set", async () => {
    vi.mocked(api.listContextDocuments).mockResolvedValueOnce([doc({ id: "cd1", name: "keep.md" })]);
    await syncEntityDocs("w1", "character", "c1", [{ id: "cd1", name: "keep.md", text: "x" }]);
    expect(api.bulkCreateContextDocuments).not.toHaveBeenCalled();
    expect(api.deleteContextDocument).not.toHaveBeenCalled();
  });
});
