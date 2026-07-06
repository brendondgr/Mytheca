import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DirectorRail } from "./DirectorRail";
import type { ActivityEntry } from "@/features/story-player/turn-stream";

const stats = [{ label: "Suspicion", value: 2, kind: "neutral" as const }];

const activity: ActivityEntry[] = [
  {
    id: "dialogue-d1",
    kind: "speaking",
    who: "char_maerin",
    label: "char_maerin speaks",
    detail: "in a low voice",
  },
  {
    id: "thought-t1",
    kind: "thinking",
    who: "char_wren",
    label: "char_wren is thinking",
  },
  {
    id: "narration-n1",
    kind: "narration",
    label: "The narrator sets the scene",
  },
];

function charById(id: string): { name: string; color: string } | undefined {
  const map: Record<string, { name: string; color: string }> = {
    char_maerin: { name: "Maerin", color: "#C8543E" },
    char_wren: { name: "Wren", color: "#A8762A" },
  };
  return map[id];
}

describe("DirectorRail", () => {
  it("renders the role=log region with aria-live=polite", () => {
    render(<DirectorRail stats={stats} />);
    const log = screen.getByRole("log");
    expect(log).toBeInTheDocument();
    expect(log).toHaveAttribute("aria-live", "polite");
  });

  it("shows the empty-state line when activity is empty", () => {
    render(<DirectorRail stats={stats} />);
    expect(screen.getByText(/The scene is quiet/i)).toBeInTheDocument();
  });

  it("renders feed entries with resolved character names in their color", () => {
    render(<DirectorRail stats={stats} activity={activity} charById={charById} />);
    // Resolved names appear
    expect(screen.getByText("Maerin")).toBeInTheDocument();
    expect(screen.getByText("Wren")).toBeInTheDocument();
    // The raw characterId is stripped from labels — only the verb part remains
    expect(screen.queryByText("char_maerin")).not.toBeInTheDocument();
    expect(screen.queryByText("char_wren")).not.toBeInTheDocument();
  });

  it("strips a display-name subject too (trace speaker labels lead with the name, not the id)", () => {
    const speakerEntry: ActivityEntry[] = [
      {
        id: "trace-speaker-char_maerin-1",
        kind: "thinking",
        who: "char_maerin",
        label: "Maerin is about to speak",
      },
    ];
    render(<DirectorRail stats={stats} activity={speakerEntry} charById={charById} />);
    expect(screen.getByText("Maerin")).toBeInTheDocument();
    expect(screen.getByText("is about to speak")).toBeInTheDocument();
    // The name never appears twice
    expect(screen.queryByText("Maerin is about to speak")).not.toBeInTheDocument();
  });

  it("renders detail text beneath the main label", () => {
    render(<DirectorRail stats={stats} activity={activity} charById={charById} />);
    expect(screen.getByText("in a low voice")).toBeInTheDocument();
  });

  it("renders a narration entry without a character name", () => {
    render(<DirectorRail stats={stats} activity={activity} charById={charById} />);
    expect(screen.getByText("The narrator sets the scene")).toBeInTheDocument();
  });

  it("renders the Scene state chips section", () => {
    render(<DirectorRail stats={stats} />);
    expect(screen.getByText("Scene state")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
  });

  it("does NOT render a Scene goal section (regression)", () => {
    render(<DirectorRail stats={stats} />);
    expect(screen.queryByText("Scene goal")).not.toBeInTheDocument();
  });

  it("does NOT render a Tension section (regression)", () => {
    render(<DirectorRail stats={stats} />);
    expect(screen.queryByText("Tension")).not.toBeInTheDocument();
  });

  it("does NOT render a Relationships section (regression)", () => {
    render(<DirectorRail stats={stats} />);
    expect(screen.queryByText("Relationships")).not.toBeInTheDocument();
  });
});
