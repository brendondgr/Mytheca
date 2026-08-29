import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { defaultScope } from "@/features/library/storylineAgent";
import type { StatDefinition, StoryPlan } from "@/lib/types";
import { StorylineAgentPanel } from "./StorylineAgentPanel";

const statDef: StatDefinition = {
  key: "resolve",
  displayName: "Resolve",
  description: "",
  min: 0,
  max: 80,
  default: 10,
  visibility: "public",
  guidance: null,
  appliesTo: ["character"],
  bands: [],
};

type Agent = Parameters<typeof StorylineAgentPanel>[0]["agent"];

function mkAgent(over: Partial<Agent> = {}): Agent {
  return {
    scope: defaultScope(["tagline"]),
    setWritable: vi.fn(),
    panel: { messages: [], streaming: "", pendingPlan: null, baseVersion: null, error: null },
    busy: false,
    applying: false,
    send: vi.fn(),
    refine: vi.fn(),
    approve: vi.fn(),
    dismissPlan: vi.fn(),
    newChat: vi.fn(),
    ...over,
  } as Agent;
}

describe("StorylineAgentPanel", () => {
  it("shows scope chips and toggles one", () => {
    const agent = mkAgent();
    render(<StorylineAgentPanel agent={agent} mode="edit" />);
    expect(screen.getByRole("button", { name: "Tagline" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Title" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "Title" }));
    expect(agent.setWritable).toHaveBeenCalledWith("title");
  });

  it("sends the message on Enter", () => {
    const agent = mkAgent();
    render(<StorylineAgentPanel agent={agent} mode="edit" />);
    const box = screen.getByLabelText("Message the assistant");
    fireEvent.change(box, { target: { value: "tighten the tagline" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(agent.send).toHaveBeenCalledWith("tighten the tagline");
  });

  it("renders the conversation and streaming reply", () => {
    const agent = mkAgent({
      panel: {
        messages: [{ role: "user", content: "hello" }],
        streaming: "typing…",
        pendingPlan: null,
        baseVersion: null,
        error: null,
      },
    });
    render(<StorylineAgentPanel agent={agent} mode="edit" />);
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("typing…")).toBeInTheDocument();
  });

  it("reviews a plan (before/after + flagged stat change) and approves", () => {
    const plan: StoryPlan = {
      changes: [{ field: "tagline", before: "Old tag", after: "New tag", rationale: "punchier" }],
      statChanges: [
        { key: "resolve", changeType: "add", after: statDef, schemaAltering: true, rationale: "grit" },
      ],
      styleChanges: [],
      notes: "",
    };
    const agent = mkAgent({
      panel: { messages: [], streaming: "", pendingPlan: plan, baseVersion: "v1", error: null },
    });
    render(<StorylineAgentPanel agent={agent} mode="edit" />);
    expect(screen.getByText("Old tag")).toBeInTheDocument();
    expect(screen.getByText("New tag")).toBeInTheDocument();
    expect(screen.getByText(/schema change/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /approve & apply/i }));
    expect(agent.approve).toHaveBeenCalled();
  });

  it("labels approve for create mode and resets the chat", () => {
    const plan: StoryPlan = {
      changes: [{ field: "title", after: "Embergate", rationale: "" }],
      statChanges: [],
      styleChanges: [],
      notes: "",
    };
    const agent = mkAgent({
      panel: { messages: [], streaming: "", pendingPlan: plan, baseVersion: null, error: null },
    });
    render(<StorylineAgentPanel agent={agent} mode="create" />);
    expect(screen.getByRole("button", { name: /approve & fill form/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /new chat/i }));
    expect(agent.newChat).toHaveBeenCalled();
  });
});
