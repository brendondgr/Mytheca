import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  bulkCreateContextDocuments,
  createCharacter,
  createGraphType,
  deleteCharacter,
  generateScenarioSceneArt,
  generateScenarioSceneArtPrompts,
  getScenarioGraph,
  listStorylines,
  postNdjson,
  proposeVoiceSamples,
  triageDocuments,
} from "@/lib/api";

function mockFetch(impl: (url: string, init?: RequestInit) => Response) {
  const spy = vi.fn((url: string, init?: RequestInit) => Promise.resolve(impl(url, init)));
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** A streamed Response body from raw chunks (to exercise line buffering). */
function streamResponse(chunks: string[], init?: ResponseInit): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
  return new Response(body, { status: 200, ...init });
}

async function collect<T>(gen: AsyncGenerator<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const ev of gen) out.push(ev);
  return out;
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

  it("postNdjson parses streamed lines, including a chunk split mid-line", async () => {
    mockFetch(() =>
      streamResponse(['{"type":"a"}\n{"ty', 'pe":"b"}\n', '{"type":"c"}']),
    );
    const events = await collect(postNdjson<{ type: string }>("/x/stream", {}));
    expect(events.map((e) => e.type)).toEqual(["a", "b", "c"]);
  });

  it("postNdjson throws the error envelope before the stream opens", async () => {
    mockFetch(
      () =>
        new Response(JSON.stringify({ error: { code: "bad_request", message: "no" } }), {
          status: 400,
        }),
    );
    await expect(collect(postNdjson("/x/stream", {}))).rejects.toMatchObject({
      code: "bad_request",
      status: 400,
    });
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

  it("generateScenarioSceneArtPrompts POSTs to /scenarios/scene-art-prompts", async () => {
    const spy = mockFetch(() =>
      new Response(JSON.stringify({ positive: "foggy harbor, watercolor", negative: "people, text" }), { status: 200 }),
    );
    const result = await generateScenarioSceneArtPrompts({ title: "The Salt Ledger", tone: "Tension · rising" });
    expect(result.positive).toContain("watercolor");
    const [url, init] = spy.mock.calls[0];
    expect(url).toContain("/scenarios/scene-art-prompts");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string).title).toBe("The Salt Ledger");
  });

  it("generateScenarioSceneArt POSTs to /scenarios/scene-art and returns image", async () => {
    const spy = mockFetch(() =>
      new Response(JSON.stringify({ image: "/media/scenes/abc.webp" }), { status: 200 }),
    );
    const result = await generateScenarioSceneArt({ positive: "foggy harbor, watercolor" });
    expect(result.image).toBe("/media/scenes/abc.webp");
    const [url] = spy.mock.calls[0];
    expect(url).toContain("/scenarios/scene-art");
  });

  it("proposeVoiceSamples POSTs to /characters/voice-samples and returns samples", async () => {
    const spy = mockFetch(() =>
      new Response(
        JSON.stringify({ samples: [{ situation: "cornered", sample: "Back off." }] }),
        { status: 200 },
      ),
    );
    const result = await proposeVoiceSamples({ name: "Fenwick", personality: "guarded" });
    expect(result.samples[0].sample).toBe("Back off.");
    const [url, init] = spy.mock.calls[0];
    expect(url).toContain("/characters/voice-samples");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string).name).toBe("Fenwick");
  });
});

// ---- connect-time retry + failure taxonomy ---------------------------------
// "Could not reach the server." can only come from a rejected fetch(), i.e. no
// response headers ever arrived. A connection that dies *after* headers is a
// different failure with a different remedy, and used to surface as a bare
// "network error" from the stream reader.

describe("connect-time retry", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("retries a generation POST once on a fresh connection and succeeds", async () => {
    let calls = 0;
    const spy = vi.fn(() => {
      calls += 1;
      if (calls === 1) return Promise.reject(new TypeError("Failed to fetch"));
      return Promise.resolve(new Response(JSON.stringify({ worldPrimer: "ok" }), { status: 200 }));
    });
    vi.stubGlobal("fetch", spy);
    const { generateWorldPrimer } = await import("@/lib/api");
    await expect(generateWorldPrimer({ premise: "p" })).resolves.toEqual({ worldPrimer: "ok" });
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("gives up after one retry and reports the server as unreachable", async () => {
    const spy = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    vi.stubGlobal("fetch", spy);
    const { generateWorldPrimer } = await import("@/lib/api");
    await expect(generateWorldPrimer({ premise: "p" })).rejects.toMatchObject({
      code: "network_error",
      message: "Could not reach the server.",
    });
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("never retries a call that writes — a retried create is a duplicate row", async () => {
    const spy = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    vi.stubGlobal("fetch", spy);
    const { createStoryline } = await import("@/lib/api");
    await expect(createStoryline({ title: "W" })).rejects.toMatchObject({
      code: "network_error",
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("retries the storyline agent stream, which performs no writes", async () => {
    let calls = 0;
    const spy = vi.fn(() => {
      calls += 1;
      if (calls === 1) return Promise.reject(new TypeError("Failed to fetch"));
      return Promise.resolve(streamResponse(['{"type":"status","message":"hi"}\n']));
    });
    vi.stubGlobal("fetch", spy);
    const { storylineAgentCreateStream } = await import("@/lib/api");
    const frames = await collect(
      storylineAgentCreateStream({ scope: {}, messages: [], fields: {} }),
    );
    expect(frames).toEqual([{ type: "status", message: "hi" }]);
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("does not retry an aborted request", async () => {
    const spy = vi.fn(() =>
      Promise.reject(new DOMException("The user aborted a request.", "AbortError")),
    );
    vi.stubGlobal("fetch", spy);
    const { generateWorldPrimer } = await import("@/lib/api");
    await expect(generateWorldPrimer({ premise: "p" })).rejects.toBeTruthy();
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("a connection lost mid-stream is not reported as an unreachable server", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("names the failure and keeps the frames already delivered", async () => {
    const enc = new TextEncoder();
    let pulls = 0;
    const body = new ReadableStream<Uint8Array>({
      // Deliver one frame, then drop the connection — the shape of a keep-alive
      // arriving before an intermediary reaps the idle socket.
      pull(controller) {
        pulls += 1;
        if (pulls === 1) {
          controller.enqueue(enc.encode('{"type":"status","message":"working"}\n'));
          return;
        }
        controller.error(new TypeError("network error"));
      },
    });
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(body, { status: 200 }))));

    const seen: unknown[] = [];
    const gen = postNdjson("/x", {});
    await expect(
      (async () => {
        for await (const frame of gen) seen.push(frame);
      })(),
    ).rejects.toMatchObject({
      code: "connection_lost",
      message: "Lost the connection while the server was still working.",
    });
    expect(seen).toEqual([{ type: "status", message: "working" }]);
  });
});
