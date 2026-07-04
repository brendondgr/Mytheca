import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useScenePlay } from "./useScenePlay";
import {
  closePlaySession,
  getSessionHistory,
  listPlaySessions,
  setPresence as apiSetPresence,
} from "@/lib/api";
import type { SessionHistory } from "@/lib/events";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";

// Keep the real api (buildScene etc. don't need it) but stub the session endpoints.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  listPlaySessions: vi.fn(async () => ({ sessions: [] })),
  getSessionHistory: vi.fn(),
  closePlaySession: vi.fn(),
  setPresence: vi.fn(async () => ({}) as never),
}));

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
