import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ScenarioForm } from "./ScenarioForm";
import type { Character, Setting } from "@/lib/types";
import type { Draft } from "@/features/library/editor";

const characters = [
  { id: "c1", name: "Maerin", mono: "MA", color: "#3A5A78" },
  { id: "c2", name: "Doran", mono: "DO", color: "#7A3A3A" },
] as Character[];

const settings = [
  { id: "s1", name: "The Harbor" },
  { id: "s2", name: "The Lighthouse" },
] as Setting[];

function renderForm(draft: Draft, setDraft = vi.fn()) {
  render(
    <ScenarioForm draft={draft} setDraft={setDraft} characters={characters} settings={settings} />,
  );
  return setDraft;
}

describe("ScenarioForm", () => {
  it("renders the Cast and Setting dropdowns", () => {
    renderForm({ cast: [], settingId: "" });
    expect(screen.getByText("Cast — choose who appears")).toBeInTheDocument();
    expect(screen.getByText("Setting — choose one")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add characters/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pick a setting/ })).toBeInTheDocument();
  });

  it("pushes a chosen character id into draft.cast", async () => {
    const user = userEvent.setup();
    const setDraft = renderForm({ cast: [], settingId: "" });

    await user.click(screen.getByRole("button", { name: /Add characters/ }));
    await user.click(screen.getByRole("option", { name: /Doran/ }));

    expect(setDraft).toHaveBeenCalledWith("cast", ["c2"]);
  });

  it("sets draft.settingId and replaces (never appends) the prior choice", async () => {
    const user = userEvent.setup();
    const setDraft = renderForm({ cast: [], settingId: "s1" });

    await user.click(screen.getByRole("button", { name: /The Harbor/ }));
    await user.click(screen.getByRole("option", { name: /The Lighthouse/ }));

    // Single-select hands back a one-element array, which the form unwraps.
    expect(setDraft).toHaveBeenCalledWith("settingId", "s2");
  });

  it("shows empty-state text when the storyline has no cast or settings", () => {
    render(<ScenarioForm draft={{ cast: [], settingId: "" }} setDraft={vi.fn()} characters={[]} settings={[]} />);
    expect(screen.getByText("No characters yet — add one first")).toBeInTheDocument();
    expect(screen.getByText("No settings yet")).toBeInTheDocument();
  });
});

describe("ScenarioForm direction verbs", () => {
  function harness(initial: Record<string, unknown> = {}) {
    const setDraft = vi.fn();
    render(
      <ScenarioForm
        draft={initial as never}
        setDraft={setDraft}
        characters={[]}
        settings={[]}
      />,
    );
    return setDraft;
  }

  it("offers the scene its own verbs, empty by default", () => {
    harness();
    expect(screen.getByText(/direction verbs/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add a verb/i })).toBeInTheDocument();
  });

  it("adds a blank row to fill in", () => {
    const setDraft = harness();
    fireEvent.click(screen.getByRole("button", { name: /add a verb/i }));
    expect(setDraft).toHaveBeenCalledWith("directionVerbs", [
      { label: "", group: "event", text: "" },
    ]);
  });

  it("keeps the chip and the phrasing as separate fields", () => {
    // The split is the point: a label repeated as its own text gives the player a command
    // to fire instead of a sentence to argue with.
    harness({ directionVerbs: [{ label: "Ring the bell", group: "event", text: "It rings." }] });
    expect(screen.getByLabelText(/chip/i)).toHaveValue("Ring the bell");
    expect(screen.getByLabelText(/phrasing/i)).toHaveValue("It rings.");
  });

  it("removes a verb by name", () => {
    const setDraft = harness({
      directionVerbs: [{ label: "Ring the bell", group: "event", text: "It rings." }],
    });
    fireEvent.click(screen.getByRole("button", { name: "Remove Ring the bell" }));
    expect(setDraft).toHaveBeenCalledWith("directionVerbs", []);
  });

  it("stops offering more once the cap is reached", () => {
    harness({
      directionVerbs: Array.from({ length: 8 }, (_, i) => ({
        label: `V${i}`, group: "event", text: "x",
      })),
    });
    expect(screen.queryByRole("button", { name: /add a verb/i })).not.toBeInTheDocument();
    expect(screen.getByText(/8 is the limit/i)).toBeInTheDocument();
  });
});

