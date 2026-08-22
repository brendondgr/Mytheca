import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { useScenePlay } from "./useScenePlay";
import {
  branchPlaySession,
  closePlaySession,
  createPlaySession,
  deletePlaySession,
  getCharacterStats,
  getLlmContextWindow,
  getSessionHistory,
  listPlaySessions,
  postSceneMoment,
  postTurn,
  clearStandingDirection,
  renamePlaySession,
  rewindPlaySession,
  setPresence as apiSetPresence,
  updateScenario,
  getScenePresets,
} from "@/lib/api";
import type { MomentStreamFrame, SessionHistory, TurnStreamFrame } from "@/lib/events";
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
  clearStandingDirection: vi.fn(),
  getScenarioRelationships: vi.fn(async () => ({ relationships: [] })),
  createPlaySession: vi.fn(),
  branchPlaySession: vi.fn(),
  rewindPlaySession: vi.fn(),
  renamePlaySession: vi.fn(async () => ({}) as never),
  deletePlaySession: vi.fn(async () => undefined),
  getLlmContextWindow: vi.fn(async () => ({ maxContextTokens: 16384, source: "configured" as const })),
  postSceneMoment: vi.fn(),
  updateScenario: vi.fn(async () => ({}) as never),
  getScenePresets: vi.fn(async () => []),
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
      closedAt: null, turnCount: 1, preview: "Prior line", name: null, parentSessionId: null, forkSeq: null,
    },
    events: [
      { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId, ts: "t", visibility: "public", data: { text: "Prior line", directedAt: null } },
      { type: "character_dialogue", id: "d", seq: 1, scenarioId: scenario.id, sessionId, ts: "t", visibility: "public", data: { characterId: speaker.id, text: '"Resumed."', done: true } },
    ],
    traces: [
      { turn: 0, n: 1, step: "turn", title: "You", detail: "Prior line", data: {} },
      { turn: 0, n: 2, step: "commit", title: "Graph", detail: "wrote", data: {} },
    ],
    standingDirection: [],
  };
}

describe("useScenePlay scene reveal", () => {
  it("holds the curtain until the scene is actually ready, then reveals", async () => {
    const { result } = renderHook(() => useScenePlay(scenario));

    // The reveal used to be a blind setTimeout(2200) on mount — the curtain
    // held for 2.2s whether the scene was ready in 100ms or not ready at 5s.
    // It is now driven by the resume/baseline load settling, with a short
    // minimum so an instant load does not flash the curtain and snatch it away.
    expect(result.current.loading).toBe(true);
    expect(result.current.reveal).toBe(false);

    await waitFor(() => expect(result.current.reveal).toBe(true), { timeout: 4000 });
    expect(result.current.loading).toBe(false);
  });

  it("reveals even when the resume fails — a failed load is a fresh scene, not a stuck curtain", async () => {
    vi.mocked(listPlaySessions).mockRejectedValueOnce(new Error("offline"));
    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() => expect(result.current.reveal).toBe(true), { timeout: 4000 });
    expect(result.current.loading).toBe(false);
  });
});

describe("useScenePlay resume + save-on-close", () => {
  it("rehydrates the transcript + trace from the latest saved session and continues it", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_prior", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "Prior line", name: null, parentSessionId: null, forkSeq: null }],
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
      sessions: [{ id: "ps_prior", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "Prior line", name: null, parentSessionId: null, forkSeq: null }],
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
      session: { id: "ps_p", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_p", ts: "t", visibility: "public", data: { text: "x", directedAt: null } },
        { type: "character_status_change", id: "s", seq: 1, scenarioId: scenario.id, sessionId: "ps_p", ts: "t", visibility: "public", data: { characterId: speaker.id, status: "dead", reason: "", auto: true } },
      ],
      traces: [],
      standingDirection: [],
    };
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_p", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce(history);

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.presenceByChar[speaker.id]).toBe("dead"));
  });

  it("setPresence updates state and persists to the session", async () => {
    vi.mocked(apiSetPresence).mockClear();
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_prior", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "Prior line", name: null, parentSessionId: null, forkSeq: null }],
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
      sessions: [{ id: "ps_b", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce({
      session: { id: "ps_b", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_b", ts: "t", visibility: "public", data: { text: "x", directedAt: null } },
        { type: "state_update", id: "s", seq: 1, scenarioId: scenario.id, sessionId: "ps_b", ts: "t", visibility: "public", data: { patch: {}, stat: { characterId: speaker.id, key: "trust", value: 85, reason: "won them over" } } },
      ],
      traces: [],
      standingDirection: [],
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

describe("useScenePlay maxContextTokens", () => {
  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  it("fetches maxContextTokens on mount and exposes it", async () => {
    vi.mocked(getLlmContextWindow).mockResolvedValueOnce({
      maxContextTokens: 32768,
      source: "detected" as const,
    });
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.maxContextTokens).toBe(32768));
  });

  it("leaves maxContextTokens as null when the fetch fails", async () => {
    vi.mocked(getLlmContextWindow).mockRejectedValueOnce(new Error("network"));
    const { result } = renderHook(() => useScenePlay(scenario));
    // Wait for mount effects to settle (session fetch etc.) without crashing.
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    expect(result.current.maxContextTokens).toBeNull();
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

  it("turnStatus tracks who is up mid-turn, then returns to idle", async () => {
    // The stream parks after the speaker trace so the mid-turn status can be observed;
    // releasing it lets the turn finish.
    let release = () => {};
    const parked = new Promise<void>((resolve) => {
      release = resolve;
    });
    async function* twoPart(): AsyncGenerator<TurnStreamFrame> {
      yield traceFrame("turn", 1, {});
      yield traceFrame("speaker", 2, { characterId: cid, name: speaker.name });
      await parked;
      yield envelope("character_dialogue", "d1", { characterId: cid, text: "Hi.", done: true });
      yield traceFrame("plan", 3, { end: true });
    }
    vi.mocked(postTurn).mockReturnValue(twoPart());

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => {
      result.current.setComposer("Hello");
    });
    act(() => {
      result.current.send();
    });

    // Mid-turn: the strip can name who is about to speak.
    await waitFor(() => expect(result.current.turnStatus.phase).toBe("thinking"));
    expect(result.current.turnStatus.characterId).toBe(cid);
    expect(result.current.turnStatus.name).toBe(speaker.name);

    await act(async () => {
      release();
    });

    // Turn over → idle, so nobody is left frozen as "about to speak".
    await waitFor(() => expect(result.current.sending).toBe(false));
    expect(result.current.turnStatus).toEqual({ phase: "idle" });
  });

  it("turnStatus clears even when the stream fails before the end-of-turn trace", async () => {
    async function* failing(): AsyncGenerator<TurnStreamFrame> {
      yield traceFrame("speaker", 1, { characterId: cid, name: speaker.name });
      throw new Error("connection lost");
    }
    vi.mocked(postTurn).mockReturnValue(failing());

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => {
      result.current.setComposer("Hello");
    });
    act(() => {
      result.current.send();
    });

    await waitFor(() => expect(result.current.sending).toBe(false));
    expect(result.current.turnStatus).toEqual({ phase: "idle" });
  });

  it("activity feed starts empty and accumulates only live frames (no rehydration)", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_old", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "old", name: null, parentSessionId: null, forkSeq: null }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce({
      session: { id: "ps_old", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "old", name: null, parentSessionId: null, forkSeq: null },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_old", ts: "t", visibility: "public", data: { text: "old", directedAt: null } },
        { type: "character_dialogue", id: "d_old", seq: 1, scenarioId: scenario.id, sessionId: "ps_old", ts: "t", visibility: "public", data: { characterId: cid, text: '"Resumed."', done: true } },
      ],
      traces: [],
      standingDirection: [],
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

describe("useScenePlay Player POV", () => {
  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  it("sends povCharacterId and renders an optimistic player-authored character beat", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([])); // no server events needed here
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setComposer("I have nothing to say."));
    act(() => result.current.send());

    // The optimistic bubble is a right-side character beat wearing the POV char's identity.
    await waitFor(() =>
      expect(
        result.current.messages.some(
          (m) =>
            m.kind === "char" &&
            m.fromPlayer === true &&
            m.who === speaker.id &&
            m.text === "I have nothing to say.",
        ),
      ).toBe(true),
    );
    // The turn request carried the POV character id.
    expect(vi.mocked(postTurn)).toHaveBeenCalledWith(
      scenario.id,
      expect.objectContaining({ text: "I have nothing to say.", povCharacterId: speaker.id }),
      expect.anything(),
    );
  });

  it("sends povCharacterId: null and a plain player bubble when no POV is set", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setComposer("A plain line."));
    act(() => result.current.send());

    await waitFor(() =>
      expect(result.current.messages.some((m) => m.kind === "player" && m.text === "A plain line.")).toBe(true),
    );
    expect(vi.mocked(postTurn)).toHaveBeenCalledWith(
      scenario.id,
      expect.objectContaining({ povCharacterId: null }),
      expect.anything(),
    );
  });

  it("resets POV to null when the chosen character is no longer present", async () => {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    await waitFor(() => expect(result.current.pov).toBe(speaker.id));

    // The POV character leaves the scene → POV falls back to the guide/narrator default.
    act(() => result.current.setPresence(speaker.id, "left"));
    await waitFor(() => expect(result.current.pov).toBeNull());
  });

  it("restores POV from the most recent user_turn on resume", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_pov", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce({
      session: { id: "ps_pov", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_pov", ts: "t", visibility: "public", data: { text: "I say nothing.", directedAt: null, pov: speaker.id } },
      ],
      traces: [],
      standingDirection: [],
    });

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.pov).toBe(speaker.id));
    // …and the resumed line renders as a player-authored character beat.
    expect(
      result.current.messages.some((m) => m.kind === "char" && m.fromPlayer === true && m.who === speaker.id),
    ).toBe(true);
  });
});

describe("useScenePlay context tokens (exact vs. estimate)", () => {
  function traceFrame(step: string, n: number, data: Record<string, unknown> = {}): TurnStreamFrame {
    return { type: "trace", n, step, title: `${step} ${n}`, detail: "", data } as TurnStreamFrame;
  }

  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  it("shows the char/4 estimate before any turn reports usage", async () => {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    // No live value yet → not exact, and the count is the (small) transcript estimate.
    expect(result.current.usedTokensExact).toBe(false);
    expect(typeof result.current.usedTokens).toBe("number");
  });

  it("adopts the exact prompt_tokens from a live `context` trace frame", async () => {
    vi.mocked(postTurn).mockReturnValue(
      makeStream([
        traceFrame("turn", 1, {}),
        traceFrame("context", 2, { characterId: speaker.id, promptTokens: 8321 }),
      ]),
    );
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setComposer("Go"));
    act(() => result.current.send());

    await waitFor(() => expect(result.current.usedTokens).toBe(8321));
    expect(result.current.usedTokensExact).toBe(true);
  });

  it("seeds the exact value from a resumed session's persisted `context` trace", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_ct", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce({
      session: { id: "ps_ct", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null },
      events: [
        { type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_ct", ts: "t", visibility: "public", data: { text: "x", directedAt: null } },
      ],
      traces: [
        { turn: 0, n: 1, step: "turn", title: "You", detail: "x", data: {} },
        { turn: 0, n: 2, step: "context", title: "Context window", detail: "", data: { promptTokens: 5120 } },
      ],
      standingDirection: [],
    });

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.usedTokens).toBe(5120));
    expect(result.current.usedTokensExact).toBe(true);
  });
});

describe("useScenePlay create image", () => {
  async function* momentStream(frames: MomentStreamFrame[]): AsyncGenerator<MomentStreamFrame> {
    for (const f of frames) yield f;
  }

  const imageEvent = (sessionId: string): MomentStreamFrame => ({
    type: "scene_image",
    id: "img1",
    seq: 4,
    scenarioId: scenario.id,
    sessionId,
    ts: "t",
    visibility: "public",
    data: {
      url: "/media/moments/abc.webp",
      prompt: "two figures at a lamplit table, wide landscape composition",
      negative: "text, watermark",
      caption: "Two figures at a lamplit table.",
      characterIds: [speaker.id],
    },
  });

  /** Resume a saved session so the hook has a session id to attach a moment to. */
  async function renderWithSession() {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({
      sessions: [{ id: "ps_img", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null }],
    });
    vi.mocked(getSessionHistory).mockResolvedValueOnce(historyOf("ps_img"));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_img"));
    return result;
  }

  beforeEach(() => vi.mocked(postSceneMoment).mockReset());

  it("streams both stages and folds the finished picture into the transcript", async () => {
    const result = await renderWithSession();
    vi.mocked(postSceneMoment).mockReturnValue(
      momentStream([
        { type: "moment_stage", stage: "prompt", message: "Reading the scene…", positive: "", caption: "" },
        { type: "moment_stage", stage: "render", message: "Painting…", positive: "two figures", caption: "Two figures at a lamplit table." },
        imageEvent("ps_img"),
      ]),
    );

    act(() => result.current.createImage());

    await waitFor(() =>
      expect(result.current.messages.some((m) => m.kind === "image")).toBe(true),
    );
    const beat = result.current.messages.find((m) => m.kind === "image");
    expect(beat?.image?.url).toBe("/media/moments/abc.webp");
    expect(beat?.image?.caption).toBe("Two figures at a lamplit table.");
    // The picture lands at the END of the transcript — under the moment it depicts.
    expect(result.current.messages[result.current.messages.length - 1]).toBe(beat);

    await waitFor(() => expect(result.current.creatingImage).toBe(false));
    expect(result.current.imageStage).toBeNull();
    expect(result.current.imageError).toBeNull();
    expect(vi.mocked(postSceneMoment)).toHaveBeenCalledWith(
      scenario.id,
      { sessionId: "ps_img" },
      expect.anything(),
    );
  });

  it("surfaces a mid-stream failure and adds no picture", async () => {
    const result = await renderWithSession();
    vi.mocked(postSceneMoment).mockReturnValue(
      momentStream([
        { type: "moment_stage", stage: "prompt", message: "Reading the scene…", positive: "", caption: "" },
        { type: "error", message: "ComfyUI never returned an image." },
      ]),
    );

    act(() => result.current.createImage());

    await waitFor(() =>
      expect(result.current.imageError).toBe("ComfyUI never returned an image."),
    );
    expect(result.current.messages.some((m) => m.kind === "image")).toBe(false);
  });

  it("does nothing before a session exists", async () => {
    vi.mocked(listPlaySessions).mockResolvedValueOnce({ sessions: [] });
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.createImage());
    expect(vi.mocked(postSceneMoment)).not.toHaveBeenCalled();
  });

  it("ignores a second request while one is already painting", async () => {
    const result = await renderWithSession();
    // A stream that never resolves keeps the hook in the streaming state.
    vi.mocked(postSceneMoment).mockReturnValue(
      (async function* () {
        yield { type: "moment_stage", stage: "prompt", message: "…", positive: "", caption: "" } as MomentStreamFrame;
        await new Promise(() => {});
      })(),
    );

    act(() => result.current.createImage());
    await waitFor(() => expect(result.current.creatingImage).toBe(true));
    act(() => result.current.createImage());

    expect(vi.mocked(postSceneMoment)).toHaveBeenCalledTimes(1);
  });
});

describe("@-tagged context files", () => {
  const DOCS = [
    { id: "cd_m", name: "maerin.md" },
    { id: "cd_h", name: "harbor.md" },
  ];

  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
  });

  async function ready(docs = DOCS) {
    const { result } = renderHook(() => useScenePlay(scenario, docs));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    return result;
  }

  it("sends the tagged ids and strips the @name tokens from the line", async () => {
    const result = await ready();
    act(() => result.current.setComposer("@maerin.md what is she holding?"));
    act(() => result.current.send());

    expect(vi.mocked(postTurn)).toHaveBeenCalledWith(
      scenario.id,
      expect.objectContaining({
        // The sigil goes, the name stays — the sent prose still says what it is about.
        text: "maerin.md what is she holding?",
        taggedDocIds: ["cd_m"],
      }),
      expect.anything(),
    );
  });

  it("omits taggedDocIds entirely when nothing is tagged", async () => {
    const result = await ready();
    act(() => result.current.setComposer("A plain line."));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body.text).toBe("A plain line.");
    expect(body).not.toHaveProperty("taggedDocIds");
  });

  it("drops a tag the player deleted by hand", async () => {
    const result = await ready();
    act(() => result.current.setComposer("@maerin.md tell me"));
    act(() => result.current.setComposer("tell me"));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body).not.toHaveProperty("taggedDocIds");
  });

  it("unions tags from the message and the scene-direction box under POV", async () => {
    const result = await ready();
    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setComposer("@maerin.md I say nothing."));
    act(() => result.current.setGuidance("@harbor.md the tide turns"));
    act(() => result.current.send());

    expect(vi.mocked(postTurn)).toHaveBeenCalledWith(
      scenario.id,
      expect.objectContaining({
        text: "maerin.md I say nothing.",
        guidance: "harbor.md the tide turns",
        taggedDocIds: ["cd_m", "cd_h"],
      }),
      expect.anything(),
    );
  });

  it("clears the tags with the boxes on send — a tag never carries into the next turn", async () => {
    const result = await ready();
    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setComposer("@maerin.md first"));
    act(() => result.current.setGuidance("@harbor.md then"));
    act(() => result.current.send());

    // Tags are derived from the two boxes, so emptying them is what un-tags the turn.
    expect(result.current.composer).toBe("");
    expect(result.current.guidance).toBe("");
  });

  it("leaves an @token alone when no documents are taggable", async () => {
    const result = await ready([]);
    act(() => result.current.setComposer("@maerin.md stays"));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body.text).toBe("@maerin.md stays");
    expect(body).not.toHaveProperty("taggedDocIds");
  });
});

describe("useScenePlay play-through tray", () => {
  const summary = (over: Partial<import("@/lib/events").SessionSummary>) => ({
    id: "ps_x",
    scenarioId: scenario.id,
    createdAt: "2026-08-21T10:00:00Z",
    updatedAt: "2026-08-21T10:00:00Z",
    closedAt: null,
    turnCount: 1,
    preview: "x",
    name: null,
    parentSessionId: null,
    forkSeq: null,
    ...over,
  });

  it("resumes the most-recently-played play-through, not the first in the array", async () => {
    // Deliberately out of recency order: the old code took sessions[0] unconditionally, so a
    // list that is not pre-sorted would silently open the wrong story.
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [
        summary({ id: "ps_old", updatedAt: "2026-08-20T10:00:00Z" }),
        summary({ id: "ps_new", updatedAt: "2026-08-21T18:00:00Z" }),
      ],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_new"));

    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() => expect(result.current.sessionId).toBe("ps_new"));
    expect(vi.mocked(getSessionHistory)).toHaveBeenCalledWith(scenario.id, "ps_new");
  });

  it("exposes every play-through for the tray", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [summary({ id: "ps_a" }), summary({ id: "ps_b", updatedAt: "2026-08-19T10:00:00Z" })],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_a"));

    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() => expect(result.current.sessions).toHaveLength(2));
    expect(result.current.sessions.map((s) => s.id)).toEqual(["ps_a", "ps_b"]);
  });

  it("starting a new play-through does not clobber the existing one", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [summary({ id: "ps_first" })] });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_first"));
    vi.mocked(createPlaySession).mockResolvedValue(summary({ id: "ps_second", turnCount: 0, preview: "" }));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_first"));

    await act(async () => {
      await result.current.startNewPlaythrough();
    });

    // The scene moved to the new session, and the old one was closed rather than deleted.
    expect(result.current.sessionId).toBe("ps_second");
    expect(vi.mocked(closePlaySession)).toHaveBeenCalledWith(scenario.id, "ps_first");
    expect(vi.mocked(deletePlaySession)).not.toHaveBeenCalled();
    // The resumed transcript is gone from view — this is a fresh story, not a continuation.
    expect(result.current.messages.some((m) => m.text === '"Resumed."')).toBe(false);
  });

  it("switching play-throughs loads the target's history", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [summary({ id: "ps_a" }), summary({ id: "ps_b", updatedAt: "2026-08-19T10:00:00Z" })],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_a"));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_a"));

    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_b"));
    await act(async () => {
      await result.current.openSession("ps_b");
    });

    expect(result.current.sessionId).toBe("ps_b");
  });

  it("switching to the play-through already open is a no-op", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [summary({ id: "ps_a" })] });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_a"));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_a"));
    const callsBefore = vi.mocked(getSessionHistory).mock.calls.length;

    await act(async () => {
      await result.current.openSession("ps_a");
    });

    expect(vi.mocked(getSessionHistory).mock.calls.length).toBe(callsBefore);
  });

  it("deleting the open play-through falls back to the newest survivor", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [summary({ id: "ps_a" }), summary({ id: "ps_b", updatedAt: "2026-08-19T10:00:00Z" })],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_a"));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_a"));

    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [summary({ id: "ps_b", updatedAt: "2026-08-19T10:00:00Z" })],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_b"));

    await act(async () => {
      await result.current.deletePlaythrough("ps_a");
    });

    expect(vi.mocked(deletePlaySession)).toHaveBeenCalledWith(scenario.id, "ps_a");
    expect(result.current.sessionId).toBe("ps_b");
  });

  it("deleting the last play-through returns to the seed scene rather than an empty column", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [summary({ id: "ps_only" })] });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_only"));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_only"));

    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    await act(async () => {
      await result.current.deletePlaythrough("ps_only");
    });

    expect(result.current.sessionId).toBeNull();
    expect(result.current.messages.length).toBeGreaterThan(0);
  });

  it("renaming refreshes the list", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [summary({ id: "ps_a" })] });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_a"));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_a"));

    await act(async () => {
      await result.current.renamePlaythrough("ps_a", "  The kind run  ");
    });

    expect(vi.mocked(renamePlaySession)).toHaveBeenCalledWith(scenario.id, "ps_a", "The kind run");
  });

  it("a blank rename clears the label", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [summary({ id: "ps_a" })] });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_a"));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_a"));

    await act(async () => {
      await result.current.renamePlaythrough("ps_a", "   ");
    });

    expect(vi.mocked(renamePlaySession)).toHaveBeenCalledWith(scenario.id, "ps_a", null);
  });
});

describe("useScenePlay branch + rewind", () => {
  const summary = (over: Partial<import("@/lib/events").SessionSummary>) => ({
    id: "ps_x", scenarioId: scenario.id, createdAt: "t", updatedAt: "2026-08-21T10:00:00Z",
    closedAt: null, turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null,
    ...over,
  });

  async function openScene() {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [summary({ id: "ps_a" })] });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_a"));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_a"));
    return result;
  }

  it("branching moves the player into the fork and keeps the original", async () => {
    const result = await openScene();
    vi.mocked(branchPlaySession).mockResolvedValue(summary({ id: "ps_fork", parentSessionId: "ps_a" }));
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_fork"));
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [summary({ id: "ps_fork", parentSessionId: "ps_a" }), summary({ id: "ps_a" })],
    });

    await act(async () => {
      await result.current.branchFrom("ev_1");
    });

    expect(vi.mocked(branchPlaySession)).toHaveBeenCalledWith(
      scenario.id, "ps_a", expect.objectContaining({ atEventId: "ev_1" }),
    );
    expect(result.current.sessionId).toBe("ps_fork");
    // The original is still listed — branching must never cost you the story you had.
    expect(result.current.sessions.map((s) => s.id)).toContain("ps_a");
  });

  it("rewinding hands the player's line back with its direction and POV", async () => {
    const result = await openScene();
    vi.mocked(rewindPlaySession).mockResolvedValue({
      session: summary({ id: "ps_a" }),
      cutSeq: 0,
      removedEvents: 4,
      removedTraces: 1,
      snapshotSessionId: "ps_snap",
      restoredTurn: {
        text: "I say the wrong thing.",
        guidance: "Mei should storm out.",
        pov: speaker.id,
        taggedDocIds: [],
      },
    });

    await act(async () => {
      await result.current.rewindTo("ev_1");
    });

    // This is the "natural prompt": the words come back, editable, with what they rode in with.
    expect(result.current.composer).toBe("I say the wrong thing.");
    expect(result.current.guidance).toBe("Mei should storm out.");
    expect(result.current.pov).toBe(speaker.id);
  });

  it("a rewind reports what it removed and how to undo it", async () => {
    const result = await openScene();
    vi.mocked(rewindPlaySession).mockResolvedValue({
      session: summary({ id: "ps_a" }), cutSeq: 0, removedEvents: 4, removedTraces: 1,
      snapshotSessionId: "ps_snap", restoredTurn: null,
    });

    await act(async () => {
      await result.current.rewindTo("ev_1");
    });

    expect(result.current.rewound).toEqual({ removedEvents: 4, snapshotSessionId: "ps_snap" });
    act(() => result.current.clearRewound());
    expect(result.current.rewound).toBeNull();
  });

  it("a rewind reloads the session rather than truncating the transcript locally", async () => {
    const result = await openScene();
    const before = vi.mocked(getSessionHistory).mock.calls.length;
    vi.mocked(rewindPlaySession).mockResolvedValue({
      session: summary({ id: "ps_a" }), cutSeq: 0, removedEvents: 2, removedTraces: 0,
      snapshotSessionId: null, restoredTurn: null,
    });

    await act(async () => {
      await result.current.rewindTo("ev_1");
    });

    // Reload is the one path already proven to produce a faithful transcript; a second,
    // subtly different local truncation is exactly how the two would drift.
    expect(vi.mocked(getSessionHistory).mock.calls.length).toBeGreaterThan(before);
  });

  it("carries an expectedSeq precondition so a stale view cannot cut the wrong rows", async () => {
    const result = await openScene();
    vi.mocked(rewindPlaySession).mockResolvedValue({
      session: summary({ id: "ps_a" }), cutSeq: 0, removedEvents: 1, removedTraces: 0,
      snapshotSessionId: null, restoredTurn: null,
    });

    await act(async () => {
      await result.current.rewindTo("ev_1");
    });

    const body = vi.mocked(rewindPlaySession).mock.calls[0][2];
    expect(body).toHaveProperty("expectedSeq");
  });
});

describe("useScenePlay direction restore", () => {
  it("puts the direction back in the box on reload", async () => {
    // Direction used to die with the turn it rode in on, so reopening a scene silently
    // dropped what the player had asked it to do.
    const history = historyOf("ps_dir");
    history.events = [
      {
        type: "user_turn", id: "u", seq: 0, scenarioId: scenario.id, sessionId: "ps_dir",
        ts: "t", visibility: "public",
        data: { text: "I hold my ground.", directedAt: null, guidance: "Mei should snap." },
      },
    ];
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [{
        id: "ps_dir", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null,
        turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null,
      }],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(history);

    const { result } = renderHook(() => useScenePlay(scenario));

    await waitFor(() => expect(result.current.guidance).toBe("Mei should snap."));
  });

  it("leaves the box empty when the last turn carried no direction", async () => {
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [{
        id: "ps_nodir", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null,
        turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null,
      }],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(historyOf("ps_nodir"));

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.sessionId).toBe("ps_nodir"));
    expect(result.current.guidance).toBe("");
  });
});

describe("useScenePlay direction-only turns", () => {
  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  it("sends a turn with a direction and no line, and shows it as an aside", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setGuidance("Someone should lose their temper."));
    act(() => result.current.send());

    expect(vi.mocked(postTurn)).toHaveBeenCalledWith(
      scenario.id,
      expect.objectContaining({ text: "", guidance: "Someone should lose their temper." }),
      expect.anything(),
    );
    // Not a speech bubble: nobody in the scene heard this.
    await waitFor(() =>
      expect(
        result.current.messages.some(
          (m) => m.kind === "direction" && m.text === "Someone should lose their temper.",
        ),
      ).toBe(true),
    );
    expect(result.current.messages.some((m) => m.kind === "player" && !m.text)).toBe(false);
  });

  it("sends nothing when both boxes are empty", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    const before = vi.mocked(postTurn).mock.calls.length;
    act(() => result.current.send());
    expect(vi.mocked(postTurn).mock.calls.length).toBe(before);
  });

  it("a message still wins: a line plus a direction is a spoken turn", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setComposer("I refuse."));
    act(() => result.current.setGuidance("Make it land badly."));
    act(() => result.current.send());

    await waitFor(() =>
      expect(result.current.messages.some((m) => m.kind === "char" && m.text === "I refuse.")).toBe(
        true,
      ),
    );
    expect(result.current.messages.some((m) => m.kind === "direction")).toBe(false);
  });
});

describe("useScenePlay direction survives a POV change", () => {
  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  it("keeps the direction when the player leaves POV", async () => {
    // The direction is a scene-level intent, not a POV artefact — and with the row present
    // in both modes, clearing it on the way out would silently discard what was written.
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setGuidance("Make it worse."));
    act(() => result.current.setPov(null));
    expect(result.current.guidance).toBe("Make it worse.");
  });

  it("still clears the direction on send — it applies to that turn only", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setGuidance("Make it worse."));
    act(() => result.current.send());
    expect(result.current.guidance).toBe("");
  });
});

describe("useScenePlay @ a character", () => {
  const DOCS = [
    { id: "cd_m", name: "maerin.md" },
    { id: "cd_h", name: "harbor.md" },
  ];

  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
  });

  it("offers the present cast alongside the context files", async () => {
    const { result } = renderHook(() => useScenePlay(scenario, DOCS));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    const kinds = result.current.mentionOptions.map((o) => o.kind);
    expect(kinds).toContain("cast");
    expect(kinds).toContain("doc");
    // Cast first, so a typed `@M` reaches a character before a same-lettered file.
    expect(result.current.mentionOptions[0].kind).toBe("cast");
  });

  it("aims the turn at the first character named in the message box", async () => {
    const { result } = renderHook(() => useScenePlay(scenario, DOCS));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setComposer(`@${speaker.name} what did you see?`));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body.directedAt).toBe(speaker.id);
    // The name survives in the prose — it is who the sentence is about.
    expect(body.text).toBe(`${speaker.name} what did you see?`);
    expect(body).not.toHaveProperty("taggedDocIds");
  });

  it("does not aim the turn from a character named in the direction box", async () => {
    // The message is what the player says; the direction is what they ask the scene to do.
    // A character named there is the subject of the direction, not the addressee.
    const { result } = renderHook(() => useScenePlay(scenario, DOCS));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setGuidance(`@${speaker.name} should storm out`));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body).not.toHaveProperty("directedAt");
    expect(body.guidance).toBe(`${speaker.name} should storm out`);
  });

  it("omits directedAt when no character was named", async () => {
    const { result } = renderHook(() => useScenePlay(scenario, DOCS));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    act(() => result.current.setComposer("A plain line."));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body).not.toHaveProperty("directedAt");
  });
});

describe("useScenePlay directives + standing direction", () => {
  const DOCS = [{ id: "cd_m", name: "maerin.md" }];

  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
  });

  it("sends directives when a direction line names a character", async () => {
    const { result } = renderHook(() => useScenePlay(scenario, DOCS));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setGuidance(`@${speaker.name} backs down\nthe lamp goes over`));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body.directives).toEqual([
      { text: `${speaker.name} backs down`, actorId: speaker.id },
      { text: "the lamp goes over", actorId: null },
    ]);
  });

  it("omits directives for a free-prose direction", async () => {
    // Nothing regresses for a player who ignores the feature — the backend parses the box
    // exactly as it does today.
    const { result } = renderHook(() => useScenePlay(scenario, DOCS));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setPov(speaker.id));
    act(() => result.current.setGuidance("Something happens and it goes badly."));
    act(() => result.current.send());

    const body = vi.mocked(postTurn).mock.calls.at(-1)?.[1] as unknown as Record<string, unknown>;
    expect(body).not.toHaveProperty("directives");
    expect(body.guidance).toBe("Something happens and it goes badly.");
  });

  it("seeds the standing debt from a resumed session", async () => {
    const history = historyOf("ps_debt");
    history.standingDirection = [
      { id: "s1", text: "the lamp goes over", actorId: null, pinned: false, fromTurn: 0 },
    ];
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [{
        id: "ps_debt", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null,
        turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null,
      }],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(history);

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.standing).toHaveLength(1));
    expect(result.current.standing[0].text).toBe("the lamp goes over");
  });

  it("drops a dismissed item immediately, without waiting for the server", async () => {
    // The player has decided; waiting on a round-trip to acknowledge a cancellation reads
    // as the control not working.
    const history = historyOf("ps_debt2");
    history.standingDirection = [
      { id: "s1", text: "the lamp goes over", actorId: null, pinned: false, fromTurn: 0 },
    ];
    vi.mocked(listPlaySessions).mockResolvedValue({
      sessions: [{
        id: "ps_debt2", scenarioId: scenario.id, createdAt: "t", updatedAt: "t", closedAt: null,
        turnCount: 1, preview: "x", name: null, parentSessionId: null, forkSeq: null,
      }],
    });
    vi.mocked(getSessionHistory).mockResolvedValue(history);
    vi.mocked(clearStandingDirection).mockResolvedValue({ standingDirection: [] });

    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.standing).toHaveLength(1));

    act(() => result.current.dismissStanding("s1"));
    expect(result.current.standing).toEqual([]);
    expect(vi.mocked(clearStandingDirection)).toHaveBeenCalledWith(
      scenario.id,
      "ps_debt2",
      ["s1"],
    );
  });
});

describe("useScenePlay play it out", () => {
  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
  });

  it("sends the choice's outcome on a direction-only turn", async () => {
    // `outcome` makes the engine open with a fuller progression passage that plays the
    // choice out. It had been engine-supported all along with no UI producer.
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() =>
      result.current.playOut({
        id: "c1",
        label: "Take the deal",
        outcome: "she takes the deal",
        player: "I take it.",
        follow: { who: "", text: "" },
      }),
    );

    expect(vi.mocked(postTurn)).toHaveBeenCalledWith(
      scenario.id,
      expect.objectContaining({
        text: "",
        guidance: "I take it.",
        outcome: "she takes the deal",
      }),
      expect.anything(),
    );
  });

  it("shows it as a direction aside, not a spoken line", async () => {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    act(() =>
      result.current.playOut({
        id: "c1", label: "Take the deal", outcome: "o", player: "",
        follow: { who: "", text: "" },
      }),
    );
    await waitFor(() =>
      expect(
        result.current.messages.some((m) => m.kind === "direction" && m.text === "Take the deal"),
      ).toBe(true),
    );
  });

  it("leaves the composer alone — this is the path that skips the typing", async () => {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    act(() => result.current.setComposer("something I was writing"));
    act(() =>
      result.current.playOut({
        id: "c1", label: "Take the deal", outcome: "o", player: "x",
        follow: { who: "", text: "" },
      }),
    );
    expect(result.current.composer).toBe("something I was writing");
  });
});

describe("useScenePlay recall", () => {
  beforeEach(() => {
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
  });

  it("hands back what the player actually typed, not the stripped version", async () => {
    // The `@name` tokens are stripped for the model; the player would be editing their own
    // words, so recall must give those back.
    const { result } = renderHook(() => useScenePlay(scenario, [{ id: "cd_m", name: "maerin.md" }]));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));

    act(() => result.current.setComposer("@maerin.md what is she holding?"));
    act(() => result.current.send());
    expect(result.current.composer).toBe("");

    act(() => result.current.recallLast());
    expect(result.current.composer).toBe("@maerin.md what is she holding?");
  });

  it("does nothing before anything has been sent", async () => {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    act(() => result.current.recallLast());
    expect(result.current.composer).toBe("");
  });

  it("keeps the last message available after a second recall", async () => {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    act(() => result.current.setComposer("A line."));
    act(() => result.current.send());

    act(() => result.current.recallLast());
    act(() => result.current.setComposer(""));
    act(() => result.current.recallLast());
    expect(result.current.composer).toBe("A line.");
  });
});

describe("useScenePlay — pinned versus per-turn scene controls", () => {
  beforeEach(() => {
    vi.mocked(updateScenario).mockClear();
    vi.mocked(postTurn).mockClear();
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  async function ready() {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    return result;
  }

  it("starts with every control pinned, so nothing changes for a player who ignores this", async () => {
    const result = await ready();
    expect(result.current.pinned).toEqual({
      maxTurns: true,
      suggestionsCount: true,
      beatLength: true,
      planner: true,
    });
    expect(result.current.turnOverrides).toEqual({});
  });

  it("writes a pinned change to the scenario and sends no overrides", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const result = await ready();

    act(() => result.current.setMaxTurns(3));
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(scenario.id, { maxTurns: 3 });
    expect(result.current.turnOverrides).toEqual({});

    act(() => result.current.setComposer("Go on."));
    act(() => result.current.send());
    await waitFor(() => expect(vi.mocked(postTurn)).toHaveBeenCalled());
    expect(vi.mocked(postTurn).mock.calls[0][1]).not.toHaveProperty("overrides");
  });

  it("keeps an unpinned change off the scenario and sends it as an override", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const result = await ready();

    act(() => result.current.setPinned("maxTurns", false));
    act(() => result.current.setMaxTurns(1));

    // Nothing was written. The value is still shown, because `effective` prefers the
    // override — that is what lets the menu display a choice that lives nowhere yet.
    expect(vi.mocked(updateScenario)).not.toHaveBeenCalled();
    expect(result.current.effective.maxTurns).toBe(1);
    expect(result.current.maxTurns).toBe(scenario.maxTurns ?? 5);

    act(() => result.current.setComposer("Just this once."));
    act(() => result.current.send());
    await waitFor(() => expect(vi.mocked(postTurn)).toHaveBeenCalled());
    expect(vi.mocked(postTurn).mock.calls[0][1]).toMatchObject({
      overrides: { maxTurns: 1 },
    });
  });

  it("springs back once the turn settles", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const result = await ready();

    act(() => result.current.setPinned("beatLength", false));
    act(() => result.current.setBeatLength("long"));
    act(() => result.current.setComposer("A long one."));
    act(() => result.current.send());

    await waitFor(() => expect(result.current.turnOverrides).toEqual({}));
    // The pin itself does not spring back — only the value it scoped.
    expect(result.current.pinned.beatLength).toBe(false);
    expect(result.current.effective.beatLength).toBe(scenario.beatLength ?? "medium");
  });

  it("springs back on the error path too — a failed turn still spent the intent", async () => {
    async function* failing(): AsyncGenerator<TurnStreamFrame> {
      throw new Error("stream died");
    }
    vi.mocked(postTurn).mockReturnValue(failing());
    const result = await ready();

    act(() => result.current.setPinned("suggestionsCount", false));
    act(() => result.current.setSuggestionsCount(0));
    expect(result.current.turnOverrides).toEqual({ suggestionsCount: 0 });

    act(() => result.current.setComposer("Boom."));
    act(() => result.current.send());

    await waitFor(() => expect(result.current.turnOverrides).toEqual({}));
  });

  it("discards a pending override when the control is re-pinned, never promotes it", async () => {
    // Promoting would make a pin click a silent permanent write to the player's scene,
    // which is exactly the surprise this feature removes.
    const result = await ready();

    act(() => result.current.setPinned("suggestionsCount", false));
    act(() => result.current.setSuggestionsCount(0));
    expect(result.current.effective.suggestionsCount).toBe(0);

    act(() => result.current.setPinned("suggestionsCount", true));
    expect(result.current.turnOverrides).toEqual({});
    expect(vi.mocked(updateScenario)).not.toHaveBeenCalled();
    expect(result.current.effective.suggestionsCount).toBe(scenario.suggestionsCount ?? 4);
  });

  it("carries an unpinned setting onto a Continue turn", async () => {
    // The footer promises "your next message", and pressing Continue is that message.
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const result = await ready();

    act(() => result.current.setPinned("maxTurns", false));
    act(() => result.current.setMaxTurns(2));
    act(() => result.current.continueTurn());

    await waitFor(() => expect(vi.mocked(postTurn)).toHaveBeenCalled());
    expect(vi.mocked(postTurn).mock.calls[0][1]).toMatchObject({
      continuation: true,
      overrides: { maxTurns: 2 },
    });
  });
});

describe("useScenePlay — scene presets", () => {
  const PRESETS = [
    {
      id: "interrogation",
      label: "Interrogation",
      blurb: "Two beats a message.",
      values: { maxTurns: 2, suggestionsCount: 3, beatLength: "medium" as const },
    },
  ];

  beforeEach(() => {
    vi.mocked(updateScenario).mockClear();
    vi.mocked(getScenePresets).mockResolvedValue(PRESETS);
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  async function ready() {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.presets.length).toBe(1));
    return result;
  }

  it("applies every bundled value in ONE call, and records the id", async () => {
    const result = await ready();
    act(() => result.current.applyPreset("interrogation"));

    expect(vi.mocked(updateScenario)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(scenario.id, {
      scenePreset: "interrogation",
      maxTurns: 2,
      suggestionsCount: 3,
      beatLength: "medium",
    });
    expect(result.current.presetState).toBe("clean");
  });

  it("reads as modified once a control is moved, and the reset restores it", async () => {
    const result = await ready();
    act(() => result.current.applyPreset("interrogation"));
    act(() => result.current.setMaxTurns(9));

    expect(result.current.presetState).toBe("modified");
    // The id is deliberately NOT cleared on a manual change — clearing it would discard
    // the very thing the reset returns to.
    expect(result.current.scenePreset).toBe("interrogation");

    act(() => result.current.applyPreset("interrogation"));
    expect(result.current.presetState).toBe("clean");
    expect(result.current.maxTurns).toBe(2);
  });

  it("Custom clears the id without touching a value", async () => {
    const result = await ready();
    act(() => result.current.applyPreset("interrogation"));
    vi.mocked(updateScenario).mockClear();

    act(() => result.current.applyPreset(null));

    expect(result.current.scenePreset).toBeNull();
    expect(result.current.presetState).toBe("none");
    expect(result.current.maxTurns).toBe(2); // unchanged
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(scenario.id, { scenePreset: null });
  });

  it("drops a pending per-turn override when a preset is applied", async () => {
    // Leaving one would have the next turn silently contradict the preset just chosen.
    const result = await ready();
    act(() => result.current.setPinned("maxTurns", false));
    act(() => result.current.setMaxTurns(1));
    expect(result.current.turnOverrides).toEqual({ maxTurns: 1 });

    act(() => result.current.applyPreset("interrogation"));
    expect(result.current.turnOverrides).toEqual({});
  });

  it("leaves the scene fully usable when the preset fetch fails", async () => {
    vi.mocked(getScenePresets).mockRejectedValueOnce(new Error("offline"));
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.reveal).toBe(true), { timeout: 4000 });

    expect(result.current.presets).toEqual([]);
    expect(result.current.presetState).toBe("none");
    act(() => result.current.setMaxTurns(4));
    expect(result.current.maxTurns).toBe(4);
  });
});

describe("useScenePlay — turn planning", () => {
  beforeEach(() => {
    vi.mocked(updateScenario).mockClear();
    vi.mocked(postTurn).mockClear();
    vi.mocked(listPlaySessions).mockResolvedValue({ sessions: [] });
    vi.mocked(getCharacterStats).mockResolvedValue({});
  });

  async function ready() {
    const { result } = renderHook(() => useScenePlay(scenario));
    await waitFor(() => expect(result.current.messages.length).toBeGreaterThan(0));
    return result;
  }

  it("defaults to the planner, so an existing scene is unchanged", async () => {
    const result = await ready();
    expect(result.current.plannerMode).toBe("planner");
    expect(result.current.effective.planner).toBe("planner");
  });

  it("persists a pinned change to the scene", async () => {
    const result = await ready();
    act(() => result.current.setPlannerMode("off"));
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(scenario.id, { plannerMode: "off" });
    expect(result.current.effective.planner).toBe("off");
  });

  it("sends an unpinned change as a per-turn override and writes nothing", async () => {
    vi.mocked(postTurn).mockReturnValue(makeStream([]));
    const result = await ready();

    act(() => result.current.setPinned("planner", false));
    act(() => result.current.setPlannerMode("off"));
    expect(vi.mocked(updateScenario)).not.toHaveBeenCalled();
    expect(result.current.plannerMode).toBe("planner");
    expect(result.current.effective.planner).toBe("off");

    act(() => result.current.setComposer("One fast turn."));
    act(() => result.current.send());
    await waitFor(() => expect(vi.mocked(postTurn)).toHaveBeenCalled());
    expect(vi.mocked(postTurn).mock.calls[0][1]).toMatchObject({
      overrides: { planner: "off" },
    });
    await waitFor(() => expect(result.current.effective.planner).toBe("planner"));
  });
});
