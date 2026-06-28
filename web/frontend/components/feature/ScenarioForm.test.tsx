import { render, screen } from "@testing-library/react";
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
