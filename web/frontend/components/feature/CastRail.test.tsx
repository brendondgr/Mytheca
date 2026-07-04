import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CastRail } from "./CastRail";
import type { Character } from "@/lib/types";

function char(id: string, name: string): Character {
  return {
    id, name, role: "Role", color: "#000", mono: name.slice(0, 2).toUpperCase(),
    traits: "", speech: "", goal: "", secret: "",
  };
}

const cast = [char("mei", "Mei"), char("kira", "Kira")];
const noop = () => undefined;

function renderRail(props: Partial<React.ComponentProps<typeof CastRail>> = {}) {
  return render(
    <CastRail
      cast={cast}
      speakingId={null}
      turnOrder={["You", "mei", "kira"]}
      charById={(id) => cast.find((c) => c.id === id)}
      onProfile={noop}
      presenceByChar={{}}
      {...props}
    />,
  );
}

describe("CastRail presence", () => {
  it("groups present vs. out-of-scene and marks the dead with a strike", () => {
    renderRail({ presenceByChar: { kira: "dead" } });
    expect(screen.getByText("In the Scene")).toBeTruthy();
    expect(screen.getByText("Out of the Scene")).toBeTruthy();
    // Kira is dead → shows the "Dead" badge and a struck-through name.
    expect(screen.getByText("Dead")).toBeTruthy();
    expect(screen.getByText("Kira").className).toContain("line-through");
    // Mei stays present → no strike.
    expect(screen.getByText("Mei").className).not.toContain("line-through");
  });

  it("has no Out-of-the-Scene group when everyone is present", () => {
    renderRail();
    expect(screen.queryByText("Out of the Scene")).toBeNull();
  });

  it("fires setPresence when the per-character control changes", () => {
    const setPresence = vi.fn();
    renderRail({ setPresence });
    fireEvent.change(screen.getByLabelText("Presence for Mei"), { target: { value: "left" } });
    expect(setPresence).toHaveBeenCalledWith("mei", "left");
  });

  it("omits the control when no setPresence handler is given (read-only)", () => {
    renderRail();
    expect(screen.queryByLabelText("Presence for Mei")).toBeNull();
  });
});
