import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { useStorylineAgent } from "./useStorylineAgent";

vi.mock("@/lib/api", () => ({
  storylineAgentEditStream: vi.fn(async function* () {
    yield { type: "message", delta: "Tighter.", done: false };
    yield { type: "message", delta: "", done: true };
    yield {
      type: "plan",
      plan: { changes: [{ field: "tagline", after: "New tag", rationale: "" }], statChanges: [], notes: "" },
      baseVersion: "v1",
    };
  }),
  storylineAgentCreateStream: vi.fn(async function* () {
    yield { type: "message", delta: "Draft.", done: false };
    yield { type: "message", delta: "", done: true };
    yield {
      type: "plan",
      plan: { changes: [{ field: "title", after: "Embergate", rationale: "" }], statChanges: [], notes: "" },
    };
  }),
  applyStorylineAgentPlan: vi.fn(async () => ({
    storyline: { id: "w1" },
    applied: ["Updated tagline"],
  })),
}));

const getFields = () => ({ tagline: "Old tag", stats: [] });

beforeEach(() => vi.clearAllMocks());

describe("useStorylineAgent (edit)", () => {
  it("streams a reply + plan into panel state (client-session memory)", async () => {
    const onApplied = vi.fn();
    const { result } = renderHook(() =>
      useStorylineAgent({ mode: "edit", storylineId: "w1", getFields, onApplied }),
    );
    await act(async () => {
      await result.current.send("tighten the tagline");
    });
    expect(result.current.panel.messages).toEqual([
      { role: "user", content: "tighten the tagline" },
      { role: "assistant", content: "Tighter." },
    ]);
    expect(result.current.panel.pendingPlan?.changes[0].field).toBe("tagline");
    expect(result.current.panel.baseVersion).toBe("v1");
  });

  it("approve applies the plan through the endpoint and mirrors it to the form", async () => {
    const onApplied = vi.fn();
    const { result } = renderHook(() =>
      useStorylineAgent({ mode: "edit", storylineId: "w1", getFields, onApplied }),
    );
    await act(async () => {
      await result.current.send("tighten");
    });
    await act(async () => {
      await result.current.approve();
    });
    expect(api.applyStorylineAgentPlan).toHaveBeenCalledWith(
      "w1",
      expect.objectContaining({ baseVersion: "v1" }),
    );
    expect(onApplied).toHaveBeenCalledWith(expect.objectContaining({ tagline: "New tag" }));
    expect(result.current.panel.pendingPlan).toBeNull();
  });

  it("newChat clears the conversation", async () => {
    const { result } = renderHook(() =>
      useStorylineAgent({ mode: "edit", storylineId: "w1", getFields, onApplied: vi.fn() }),
    );
    await act(async () => {
      await result.current.send("hi");
    });
    act(() => result.current.newChat());
    expect(result.current.panel.messages).toEqual([]);
    expect(result.current.panel.pendingPlan).toBeNull();
  });

  it("setWritable toggles a field's scope", () => {
    const { result } = renderHook(() =>
      useStorylineAgent({ mode: "edit", storylineId: "w1", getFields, onApplied: vi.fn() }),
    );
    act(() => result.current.setWritable("tagline"));
    expect(result.current.scope.tagline.writable).toBe(true);
  });
});

describe("useStorylineAgent (create)", () => {
  it("approve fills the form and never calls the apply endpoint", async () => {
    const onApplied = vi.fn();
    const { result } = renderHook(() => useStorylineAgent({ mode: "create", getFields, onApplied }));
    await act(async () => {
      await result.current.send("draft a title");
    });
    await act(async () => {
      await result.current.approve();
    });
    expect(api.storylineAgentCreateStream).toHaveBeenCalled();
    expect(api.applyStorylineAgentPlan).not.toHaveBeenCalled();
    expect(onApplied).toHaveBeenCalledWith(expect.objectContaining({ title: "Embergate" }));
  });
});
