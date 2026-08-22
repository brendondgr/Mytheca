import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { PromptOverridesEditor } from "./PromptOverridesEditor";
import type { PromptSpec } from "@/lib/api";

const CATALOG: PromptSpec[] = [
  {
    key: "narrator.system",
    agent: "Narrator",
    label: "Transition beat",
    description: "Short narration between beats.",
    default: "DEF NARR",
  },
  {
    key: "planner.system",
    agent: "Planner",
    label: "Next-beat loop",
    description: "Decides the next beat.",
    default: "DEF PLAN",
  },
];

const narratorField = () =>
  screen.getByRole("textbox", { name: /narrator — transition beat prompt/i }) as HTMLTextAreaElement;

describe("PromptOverridesEditor", () => {
  it("renders one sub-tab per agent and prefills the default text", () => {
    render(<PromptOverridesEditor catalog={CATALOG} overrides={{}} onSave={vi.fn()} />);
    expect(screen.getByRole("tab", { name: "Narrator" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Planner" })).toBeInTheDocument();
    // Narrator tab is active first; its field shows the inherited default.
    expect(narratorField().value).toBe("DEF NARR");
  });

  it("switches panels when a sub-tab is clicked", async () => {
    const user = userEvent.setup();
    render(<PromptOverridesEditor catalog={CATALOG} overrides={{}} onSave={vi.fn()} />);
    expect(screen.queryByRole("textbox", { name: /planner/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Planner" }));
    expect(screen.getByRole("textbox", { name: /planner — next-beat loop prompt/i })).toBeInTheDocument();
  });

  it("prefills an existing override and flags it as overridden", () => {
    render(
      <PromptOverridesEditor catalog={CATALOG} overrides={{ "narrator.system": "CUSTOM" }} onSave={vi.fn()} />,
    );
    expect(narratorField().value).toBe("CUSTOM");
    expect(screen.getByText(/overridden/i)).toBeInTheDocument();
  });

  it("saves only the modified keys", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<PromptOverridesEditor catalog={CATALOG} overrides={{}} onSave={onSave} />);
    // Disabled until something changes.
    expect(screen.getByRole("button", { name: /save prompts/i })).toBeDisabled();

    await user.clear(narratorField());
    await user.type(narratorField(), "NEW NARR");
    await user.click(screen.getByRole("button", { name: /save prompts/i }));
    expect(onSave).toHaveBeenCalledWith({ "narrator.system": "NEW NARR" });
  });

  it("reset-to-default drops the override on save", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <PromptOverridesEditor catalog={CATALOG} overrides={{ "narrator.system": "CUSTOM" }} onSave={onSave} />,
    );
    await user.click(screen.getByRole("button", { name: /reset to default/i }));
    expect(narratorField().value).toBe("DEF NARR");
    await user.click(screen.getByRole("button", { name: /save prompts/i }));
    expect(onSave).toHaveBeenCalledWith({});
  });

  it("uses the baseline as the revert target when provided", () => {
    render(
      <PromptOverridesEditor
        catalog={CATALOG}
        overrides={{}}
        baseline={{ "narrator.system": "INHERITED GLOBAL" }}
        onSave={vi.fn()}
      />,
    );
    // No override, so the field shows the inherited baseline (not the registry default).
    expect(narratorField().value).toBe("INHERITED GLOBAL");
    expect(screen.queryByText(/overridden/i)).not.toBeInTheDocument();
  });
});

describe("PromptOverridesEditor — layer attribution", () => {
  it("names where each prompt's live value comes from", () => {
    // The editor has never shown this, so three abstract layers read as one flat list and
    // "why is this not what I typed" has no answer on screen.
    render(
      <PromptOverridesEditor
        catalog={CATALOG}
        overrides={{}}
        onSave={vi.fn()}
        sources={{ "narrator.system": "storyline", "planner.system": "default" }}
      />,
    );
    expect(screen.getByText("This world")).toBeInTheDocument();
  });

  it("uses player words, not implementation words", () => {
    render(
      <PromptOverridesEditor
        catalog={CATALOG}
        overrides={{}}
        onSave={vi.fn()}
        sources={{ "narrator.system": "global", "planner.system": "default" }}
      />,
    );
    expect(screen.getByText("Everywhere")).toBeInTheDocument();
    expect(screen.queryByText(/^global$/i)).not.toBeInTheDocument();
  });

  it("renders no badges at all when the layers are unknown", () => {
    // Existing callers pass nothing and must be unchanged — and a surface that cannot see
    // every layer should not claim to name one.
    render(<PromptOverridesEditor catalog={CATALOG} overrides={{}} onSave={vi.fn()} />);
    for (const label of ["Default", "Everywhere", "This world", "This scene"]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });
});
