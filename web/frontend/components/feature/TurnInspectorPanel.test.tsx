import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { TurnInspectorPanel } from "./TurnInspectorPanel";
import type { TraceTurn } from "@/features/story-player/turn-stream";

function turn(id = "0", label = "I slide the coin pouch over."): TraceTurn {
  return {
    id,
    label,
    steps: [
      { type: "trace", n: 1, step: "turn", title: "You submitted a message", detail: label, data: {} },
      { type: "trace", n: 2, step: "plan", title: "Mei is up next", detail: "You addressed Mei directly.", data: {} },
      { type: "trace", n: 3, step: "thinking", title: "Mei thinks (private)", detail: "Coin first, favor later.", data: {} },
      { type: "trace", n: 4, step: "dialogue", title: "Mei speaks", detail: '"Coin is easy."', data: {} },
    ],
  };
}

describe("TurnInspectorPanel", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <TurnInspectorPanel open={false} onClose={() => {}} turns={[turn()]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the empty-state hint when there are no turns yet", () => {
    render(<TurnInspectorPanel open onClose={() => {}} turns={[]} />);
    expect(screen.getByText(/Send a message in the scene/i)).toBeInTheDocument();
  });

  it("renders step titles in order (the active turn is expanded)", () => {
    render(<TurnInspectorPanel open onClose={() => {}} turns={[turn()]} />);
    // Docked column (complementary landmark, not a modal dialog) so the chat stays visible.
    expect(screen.getByRole("complementary", { name: /turn inspector/i })).toBeInTheDocument();
    expect(screen.getByText("Mei is up next")).toBeInTheDocument();
    expect(screen.getByText("Mei speaks")).toBeInTheDocument();
    // The opening "turn" step is not repeated as a row (it labels the group instead).
    expect(screen.queryByText("You submitted a message")).not.toBeInTheDocument();
  });

  it("hides a step's detail until its row is expanded (per-entry dropdown)", async () => {
    render(<TurnInspectorPanel open onClose={() => {}} turns={[turn()]} />);
    // Detail is collapsed by default …
    expect(screen.queryByText("Coin first, favor later.")).not.toBeInTheDocument();
    const row = screen.getByRole("button", { name: /Mei thinks/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    // … and revealed when the row is activated (keyboard-operable button).
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Coin first, favor later.")).toBeInTheDocument();
  });

  it("color-codes each step type with a distinct tag", () => {
    const t: TraceTurn = {
      id: "0",
      label: "go",
      steps: [
        { type: "trace", n: 1, step: "turn", title: "You", detail: "go", data: {} },
        { type: "trace", n: 2, step: "plan", title: "Mei is up next", detail: "provoked", data: {} },
        { type: "trace", n: 3, step: "relationship_change", title: "Mei now resents Beth", detail: "betrayal", data: {} },
        { type: "trace", n: 4, step: "stat", title: "suspicion +2", detail: "guard raised", data: {} },
      ],
    };
    render(<TurnInspectorPanel open onClose={() => {}} turns={[t]} />);
    expect(screen.getByText("Plan")).toBeInTheDocument();
    expect(screen.getByText("Bond")).toBeInTheDocument();
    expect(screen.getByText("Stat")).toBeInTheDocument();
  });

  it("tags the @-tagged files step as Files, distinct from the gated Lore look-up", () => {
    const t: TraceTurn = {
      id: "0",
      label: "go",
      steps: [
        {
          type: "trace",
          n: 1,
          step: "lore",
          title: "World-lore look-up (RAG)",
          detail: "Skipped.",
          data: {},
        },
        {
          type: "trace",
          n: 2,
          step: "files",
          title: "Tagged files — 1 attached",
          detail: "Folded maerin.md into the prompt as reference material.",
          data: { names: ["maerin.md"], injected: true },
        },
      ],
    };
    render(<TurnInspectorPanel open onClose={() => {}} turns={[t]} />);
    expect(screen.getByText("Files")).toBeInTheDocument();
    expect(screen.getByText("Lore")).toBeInTheDocument();
    expect(screen.getByText("Tagged files — 1 attached")).toBeInTheDocument();
  });

  it("keeps only the newest turn expanded; older turns collapse (accordion)", async () => {
    render(
      <TurnInspectorPanel
        open
        onClose={() => {}}
        turns={[turn("0", "first"), turn("1", "second")]}
      />,
    );
    const older = screen.getByRole("button", { name: /Turn 1/ });
    const newer = screen.getByRole("button", { name: /Turn 2/ });
    expect(newer).toHaveAttribute("aria-expanded", "true"); // newest turn is active/open
    expect(older).toHaveAttribute("aria-expanded", "false"); // completed turn collapsed
    // Only the newest turn's steps are rendered while it is the sole open one.
    expect(screen.getAllByText("Mei is up next")).toHaveLength(1);
    // Clicking a completed turn opens it and collapses the newer one.
    await userEvent.click(older);
    expect(older).toHaveAttribute("aria-expanded", "true");
    expect(newer).toHaveAttribute("aria-expanded", "false");
  });

  it("closes via the close button", async () => {
    const onClose = vi.fn();
    render(<TurnInspectorPanel open onClose={onClose} turns={[turn()]} />);
    await userEvent.click(screen.getByRole("button", { name: /^close$/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });


  // The register control invites exactly one question — did my pin reach this beat? —
  // and the engine already answers it on the speaker step.

  it("says who pitched a beat when a register was pinned", async () => {
    const user = userEvent.setup();
    render(
      <TurnInspectorPanel
        open
        onClose={() => {}}
        turns={[
          {
            id: "0",
            label: "I press down.",
            steps: [
              {
                type: "trace",
                n: 1,
                step: "speaker",
                title: "Mei responds",
                detail: "addressed",
                data: { register: "grave", registerSource: "player" },
              },
            ],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: /mei responds/i }));
    expect(screen.getByText(/grave — pitched by you/i)).toBeInTheDocument();
  });

  it("credits the scene when the planner pitched it", async () => {
    const user = userEvent.setup();
    render(
      <TurnInspectorPanel
        open
        onClose={() => {}}
        turns={[
          {
            id: "0",
            label: "I press down.",
            steps: [
              {
                type: "trace",
                n: 1,
                step: "speaker",
                title: "Mei responds",
                detail: "addressed",
                data: { register: "tense", registerSource: "planner" },
              },
            ],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: /mei responds/i }));
    expect(screen.getByText(/tense — pitched by the scene/i)).toBeInTheDocument();
  });

  it("says nothing about pitch on a beat that carried no register", async () => {
    const user = userEvent.setup();
    render(
      <TurnInspectorPanel
        open
        onClose={() => {}}
        turns={[
          {
            id: "0",
            label: "I press down.",
            steps: [
              {
                type: "trace",
                n: 1,
                step: "speaker",
                title: "Mei responds",
                detail: "addressed",
                data: { register: "", registerSource: "" },
              },
            ],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: /mei responds/i }));
    expect(screen.queryByText(/pitched by/i)).not.toBeInTheDocument();
  });
});
