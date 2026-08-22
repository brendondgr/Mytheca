import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneRailBar, type RailTrigger } from "./SceneRailBar";

function trigger(over: Partial<RailTrigger> = {}): RailTrigger {
  return { key: "cast", label: "Cast", open: false, onSelect: vi.fn(), ...over };
}

describe("SceneRailBar", () => {
  it("renders nothing when there is nothing to open", () => {
    const { container } = render(<SceneRailBar triggers={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("declares what each button opens and whether it is open", async () => {
    const onSelect = vi.fn();
    render(<SceneRailBar triggers={[trigger({ onSelect })]} />);
    const button = screen.getByRole("button", { name: "Cast" });

    expect(button).toHaveAttribute("aria-haspopup", "dialog");
    expect(button).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(button);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("reflects the open state back", () => {
    render(<SceneRailBar triggers={[trigger({ open: true })]} />);
    expect(screen.getByRole("button", { name: "Cast" })).toHaveAttribute("aria-expanded", "true");
  });

  it("folds the count into the name instead of leaving a bare numeral", () => {
    // "Scene 2" read aloud says nothing. The badge is the only place this number exists on
    // a phone, so it has to be in the accessible name.
    render(
      <SceneRailBar
        triggers={[
          trigger({ key: "scene", label: "Scene", count: 2, countLabel: (n) => `${n} still owed` }),
        ]}
      />,
    );
    expect(screen.getByRole("button", { name: "Scene, 2 still owed" })).toBeInTheDocument();
    // The visible badge is aria-hidden — it would otherwise be read twice.
    expect(screen.getByText("2")).toHaveAttribute("aria-hidden", "true");
  });

  it("shows no badge at zero", () => {
    render(
      <SceneRailBar
        triggers={[
          trigger({ key: "scene", label: "Scene", count: 0, countLabel: (n) => `${n} still owed` }),
        ]}
      />,
    );
    expect(screen.getByRole("button", { name: "Scene" })).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("does not promise a dialog for a control that only discloses a panel", () => {
    render(<SceneRailBar triggers={[trigger({ key: "knows", label: "Knows", dialog: false })]} />);
    const button = screen.getByRole("button", { name: "Knows" });
    expect(button).not.toHaveAttribute("aria-haspopup");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("is hidden at the widths where the rails themselves are on screen", () => {
    const { container } = render(<SceneRailBar triggers={[trigger()]} />);
    expect(container.firstElementChild?.className).toContain("lg:hidden");
  });
});
