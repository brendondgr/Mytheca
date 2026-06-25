import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  buildWorld,
  bulkCreateContextDocuments,
  createCharacter,
  createGraphType,
  deleteCharacter,
  getScenarioGraph,
  listStorylines,
  triageDocuments,
} from "@/lib/api";

function mockFetch(impl: (url: string, init?: RequestInit) => Response) {
  const spy = vi.fn((url: string, init?: RequestInit) => Promise.resolve(impl(url, init)));
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("parses a successful JSON response", async () => {
    mockFetch(() => new Response(JSON.stringify([{ id: "embergate", title: "Embergate" }]), { status: 200 }));
    const storylines = await listStorylines();
    expect(storylines[0].id).toBe("embergate");
  });

  it("sends create payloads as JSON to the scoped endpoint", async () => {
    const spy = mockFetch(() => new Response(JSON.stringify({ id: "c1", name: "Maerin", mono: "MV" }), { status: 201 }));
    const created = await createCharacter("embergate", { name: "Maerin", role: "Antagonist", color: "#000", traits: "", speech: "", goal: "", secret: "" });
    expect(created.id).toBe("c1");
    const [url, init] = spy.mock.calls[0];
    expect(url).toContain("/storylines/embergate/characters");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string).name).toBe("Maerin");
  });

  it("maps the error envelope to ApiError", async () => {
    mockFetch(() => new Response(JSON.stringify({ error: { code: "not_found", message: "nope" } }), { status: 404 }));
    await expect(listStorylines()).rejects.toMatchObject({ code: "not_found", status: 404 });
    await expect(listStorylines()).rejects.toBeInstanceOf(ApiError);
  });

  it("returns undefined for 204 responses", async () => {
    mockFetch(() => new Response(null, { status: 204 }));
    await expect(deleteCharacter("c1")).resolves.toBeUndefined();
  });

  it("reads a scenario's Story-Graph subgraph", async () => {
    const spy = mockFetch(
      () => new Response(JSON.stringify({ available: true, scenarioId: "sc1", nodes: [], edges: [] }), { status: 200 }),
    );
    const graph = await getScenarioGraph("sc1");
    expect(graph.available).toBe(true);
    expect(spy.mock.calls[0][0]).toContain("/scenarios/sc1/graph");
  });

  it("posts dropped docs to the triage endpoint", async () => {
    const spy = mockFetch(
      () => new Response(JSON.stringify({ items: [{ name: "a.md", category: "character" }] }), { status: 200 }),
    );
    const res = await triageDocuments([{ name: "a.md", text: "A person." }]);
    expect(res.items[0].category).toBe("character");
    const [url, init] = spy.mock.calls[0];
    expect(url).toContain("/storylines/triage");
    expect(JSON.parse(init?.body as string).docs[0].name).toBe("a.md");
  });

  it("requests a world build", async () => {
    const spy = mockFetch(
      () =>
        new Response(
          JSON.stringify({ storyline: { title: "Built" }, stats: [], characters: [], settings: [] }),
          { status: 200 },
        ),
    );
    const world = await buildWorld({ seed: "A world." });
    expect(world.storyline.title).toBe("Built");
    expect(spy.mock.calls[0][0]).toContain("/storylines/build");
  });

  it("bulk-creates the triaged context corpus", async () => {
    const spy = mockFetch(() => new Response(JSON.stringify([{ id: "cd1", name: "a.md" }]), { status: 201 }));
    const docs = await bulkCreateContextDocuments("embergate", [
      { name: "a.md", content: "x", category: "other", includeRag: true },
    ]);
    expect(docs[0].id).toBe("cd1");
    const [url, init] = spy.mock.calls[0];
    expect(url).toContain("/storylines/embergate/context-docs/bulk");
    expect(JSON.parse(init?.body as string).docs[0].name).toBe("a.md");
  });

  it("registers a user-defined graph type at the storyline-scoped endpoint", async () => {
    const spy = mockFetch(
      () => new Response(JSON.stringify({ id: "gt1", typeName: "sworn_to", status: "experimental" }), { status: 201 }),
    );
    const created = await createGraphType("embergate", {
      kind: "edge",
      typeName: "sworn_to",
      fieldSchema: [],
      description: "",
      valence: "positive",
      decay: null,
    });
    expect(created.id).toBe("gt1");
    const [url, init] = spy.mock.calls[0];
    expect(url).toContain("/storylines/embergate/graph/types");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string).valence).toBe("positive");
  });
});
