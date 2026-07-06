import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { useScenePlay } from "./useScenePlay";
import {
  closePlaySession,
  getCharacterStats,
  getSessionHistory,
  listPlaySessions,
  postTurn,
  setPresence as apiSetPresence,
} from "@/lib/api";
import type { SessionHistory, TurnStreamFrame } from "@/lib/events";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";

// Keep the real api (buildScene etc. don't need it) but stub the session + stat endpoints.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  listPlaySessions: vi.fn(async () => ({ sessions: [] })),
  getSessionHistory: vi.fn(),
  closePlaySession: vi.fn(),
  setPresence: vi.fn(async () => ({}) as never),
  getCharacterStats: vi.fn(async () => ({}) as Record<string, number>),
  postTurn: vi.fn(),
  getScenarioRelationships: vi.fn(async () => ({ relationships: [] })),
}));

/** Build a mock async generator that yields the given frames then completes. */
async function* makeStream(frames: TurnStreamFrame[]): AsyncGenerator<TurnStreamFrame> {
  for (const f of frames) yield f;
}

const scenario = resolveScenario(SEED_SCENARIOS[0], SEED_CHARACTERS, SEED_SETTINGS);
const speaker = scenario.cast[0];

function historyOf(sessionId: string): SessionHistory {
  return {
    session: {
      id: sessionId, scenarioId: scenario.id, createdAt: "t", updatedAt: "t",
      closedAt: null, turnCount: 1, preview: "Prior line",
    },
    events: [
      { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId, ts: "t", visibility: "public", data: { text: "Prior line", directedAt: null } },
      { type: "character_dialogue", id: "d", seq: 1, scenarioId: scenario.id, sessionId, ts: "t", visibility: "public", data: { characterId: speaker.id, text: '"Resumed."', done: true } },
    ],
    traces: [
      { turn: 0, n: 1, step: "turn", title: "You", detail: "Prior line", data: {} },
      { turn: 0, n: 2, step: "commit", title: "Graph", detail: "wrote", data: {} },
    ],
  };
}

describe("useScenePlay resume + save-on-close", () => {
  it("rehydrates the transcript + trace from the latest saved session and continues it", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_prior", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "Prior line" }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce(historyOf("ps_prior"));

    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() =>
      expect(result.current.messages.some((m) => m.text === '"Resumed."')).toBe(true),
    );
    // The prior player line and the resumed session id are restored …
    expect(result.current.messages.some((m) => m.kind === "player" && m.text === "Prior line")).toBe(true);
    expect(result.current.sessionId).toBe("ps_prior");
    // … and the persisted graph trace is grouped back into the Inspector.
    expect(result.current.traceTurns[0].steps.map((s) => s.step)).toEqual(["turn", "commit"]);
  });

  it("keeps the seed scene when there is no saved session", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({ sessions: [] });
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    expect(result.current.sessionId).toBeNull();
  });

  it("fires the save-on-close signal when the player leaves", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_prior", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "Prior line" }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce(historyOf("ps_prior"));
    const { result, unmount } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_prior"));
    unmount();
    expect(vi.mocked(closePlaySession)).toHaveBeenCalledWith(scenario.id, "ps_prior");
  });
});

describe("useScenePlay presence", () => {
  it("rehydrates presenceByChar from a persisted status change", async () => {
    const history: SessionHistory = {
      session: { id: "ps_p", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x" },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_p", ts: "t", visibility: "public", data: { text: "x", directedAt: null } },
        { type: "character_status_change", id: "s", seq: 1, scenarioId: scenario.id, sessionId: "ps_p", ts: "t", visibility: "public", data: { characterId: speaker.id, status: "dead", reason: "", auto: true } },
      ],
      traces: [],
    };
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_p", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x" }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce(history);

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.presenceByChar[speaker.id]).toBe("dead"));
  });

  it("setPresence updates state and persists to the session", async () => {
    vi.mocked(apiSetPresence).mockClear();
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_prior", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "Prior line" }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce(historyOf("ps_prior"));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_prior"));

    act(() => result.current.setPresence(speaker.id, "left"));
    expect(result.current.presenceByChar[speaker.id]).toBe("left");
    expect(vi.mocked(apiSetPresence)).toHaveBeenCalledWith(scenario.id, {
      sessionId: "ps_prior",
      characterId: speaker.id,
      status: "left",
    });
  });
});

describe("useScenePlay stats baseline", () => {
  it("seeds statsByChar from each cast member's persisted starting stats", async () => {
    vi.mocked(getCharacterStats).mockReset();
    vi.mocked(getCharacterStats).mockImplementation(async (id: string): Promise<Record<string, number>> =>
      id === speaker.id ? { trust: 70, suspicion: 5 } : {},
    );
    vi.mocked(listPlaySessions).mockResolvedValueOnce({ sessions: [] });

    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() => expect(result.current.statsByChar[speaker.id]).toBeDefined());
    expect(result.current.statsByChar[speaker.id]).toEqual(
      expect.arrayContaining([
        { label: "Trust", value: 70, reason: "" },
        { label: "Suspicion", value: 5, reason: "" },
      ]),
    );
  });

  it("layers a resumed session's persisted stat deltas on top of the baseline", async () => {
    vi.mocked(getCharacterStats).mockReset();
    vi.mocked(getCharacterStats).mockImplementation(async (id: string): Promise<Record<string, number>> =>
      id === speaker.id ? { trust: 40, suspicion: 5 } : {},
    );
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_b", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x" }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce({
      session: { id: "ps_b", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x" },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_b", ts: "t", visibility: "public", data: { text: "x", directedAt: null } },
        { type: "state_update", id: "s", seq: 1, scenarioId: scenario.id, sessionId: "ps_b", ts: "t", visibility: "public", data: { patch: {}, stat: { characterId: speaker.id, key: "trust", value: 85, reason: "won them over" } } },
      ],
      traces: [],
    });

    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() => {
      const chip = result.current.statsByChar[speaker.id]?.find((c) => c.label === "Trust");
      expect(chip?.value).toBe(85);
    });
    // The untouched baseline stat (suspicion) survives the resume, not just the touched one.
    const suspicion = result.current.statsByChar[speaker.id]?.find((c) => c.label === "Suspicion");
    expect(suspicion?.value).toBe(5);
  });

  it("degrades to no baseline for a character whose stats fetch fails", async () => {
    vi.mocked(getCharacterStats).mockReset();
    vi.mocked(getCharacterStats).mockRejectedValue(new Error("network"));
    vi.mocked(listPlaySessions).mockResolvedValueOnce({ sessions: [] });

    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    expect(result.current.statsByChar[speaker.id]).toBeUndefined();
  });
});

describe("useScenePlay activity feed + per-character status", () => {
  const cid = speaker.id;

  function envelope(type: string, id: string, data: unknown): TurnStreamFrame {
    return {
      type,
      id,
      seq: 1,
      scenarioId: scenario.id,
      sessionId: "ps_live",
      ts: "t",
      visibility: "public",
      data,
    } as TurnStreamFrame;
  }

  function traceFrame(step: string, n: number, data: Record<string, unknown> = {}): TurnStreamFrame {
    return { type: "trace", n, step, title: `${step} ${n}`, detail: "", data } as TurnStreamFrame;
  }

  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  it("activity feed accumulates entries and character goes thinking → speaking during a turn", async () => {
    const frames: TurnStreamFrame[] = [
      traceFrame("turn", 1, {}),
      traceFrame("speaker", 2, { characterId: cid, name: speaker.name }),
      envelope("internal_thought", "t1", { characterId: cid, text: "Let me think." }),
      envelope("character_dialogue", "d1", { characterId: cid, text: "Hello", done: false }),
      envelope("character_dialogue", "d1", { characterId: cid, text: " world.", done: true }),
    ];
    vi.mocked(postTurn).mockReturnValue(makeStream(frames));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => {
      result.current.send();
    });

    // Force send with a composer value
    act(() => {
      result.current.setComposer("Hi there");
    });
    act(() => {
      result.current.send();
    });

    await waitFor(() =>
      expect(result.current.activity.some((e) => e.kind === "thinking")).toBe(true),
    );

    // At least the speaker trace → thinking and the dialogue → speaking entries exist.
    const feed = result.current.activity;
    expect(feed.some((e) => e.kind === "thinking")).toBe(true);
    expect(feed.some((e) => e.kind === "speaking")).toBe(true);

    // Dialogue id is stable (no duplicate for each chunk).
    const speakingEntries = feed.filter((e) => e.id === `dialogue-d1`);
    expect(speakingEntries).toHaveLength(1);
  });

  it("activityByChar resets to empty after the stream ends", async () => {
    const frames: TurnStreamFrame[] = [
      traceFrame("speaker", 1, { characterId: cid, name: speaker.name }),
      envelope("character_dialogue", "d1", { characterId: cid, text: "Hi.", done: false }),
      envelope("character_dialogue", "d1", { characterId: cid, text: "", done: true }),
    ];
    vi.mocked(postTurn).mockReturnValue(makeStream(frames));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => {
      result.current.setComposer("Hello");
    });
    act(() => {
      result.current.send();
    });

    // Wait for stream to complete (sending flips back to false → activityByChar clears).
    await waitFor(() => expect(result.current.sending).toBe(false));
    expect(result.current.activityByChar).toEqual({});
  });

  it("activity feed starts empty and accumulates only live frames (no rehydration)", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_old", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "old" }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce({
      session: { id: "ps_old", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "old" },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_old", ts: "t", visibility: "public", data: { text: "old", directedAt: null } },
        { type: "character_dialogue", id: "d_old", seq: 1, scenarioId: scenario.id, sessionId: "ps_old", ts: "t", visibility: "public", data: { characterId: cid, text: '"Resumed."', done: true } },
      ],
      traces: [],
    });

    const { result } = renderHook(() => useScenePlay(scenario));

    // Wait for rehydration to complete.
    await waitFor(() =>
      expect(result.current.messages.some((m) => m.text === '"Resumed."')).toBe(true),
    );

    // Activity feed should be empty — it is live-only.
    expect(result.current.activity).toEqual([]);
    expect(result.current.activityByChar).toEqual({});
  });
});
