import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneHeader } from "./SceneHeader";

describe("SceneHeader export control", () => {
  it("renders Export to the left of the theme switcher and fires the handler", async () => {
    const onExport = vi.fn();
    const { container } = render(
      <SceneHeader title="Standoff" settingName="Hearth" onExport={onExport} canExport />,
    );
    const exportBtn = screen.getByRole("button", { name: /export/i });
    // The theme switcher is a labeled group; Export must precede it in the DOM (to its left).
    const themeGroup = screen.getByRole("group", { name: /theme/i });
    expect(
      exportBtn.compareDocumentPosition(themeGroup) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    await userEvent.click(exportBtn);
    await userEvent.click(screen.getByRole("menuitem", { name: /markdown/i }));
    expect(onExport).toHaveBeenCalledWith("md");
    void container;
  });

  it("disables Export until a session exists", () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport={false} />);
    expect(screen.getByRole("button", { name: /export/i })).toBeDisabled();
  });

  it("omits the control when no export handler is given", () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" />);
    expect(screen.queryByRole("button", { name: /export/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader view switch (chat ⇄ graph)", () => {
  it("renders the Chat/Graph switch to the left of Export and fires the handler", async () => {
    const onViewModeChange = vi.fn();
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        viewMode="chat"
        onViewModeChange={onViewModeChange}
        onExport={vi.fn()}
        canExport
      />,
    );
    const group = screen.getByRole("group", { name: /scene view/i });
    const exportBtn = screen.getByRole("button", { name: /export/i });
    // The switch precedes Export in the DOM (to its left).
    expect(group.compareDocumentPosition(exportBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Active state reflects the current mode.
    expect(screen.getByRole("button", { name: /chat/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /graph/i })).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(screen.getByRole("button", { name: /graph/i }));
    expect(onViewModeChange).toHaveBeenCalledWith("graph");
  });

  it("omits the switch when no handler is given", () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport />);
    expect(screen.queryByRole("group", { name: /scene view/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader config control (relocated to the composer)", () => {
  it("no longer renders the Config control in the header", () => {
    // Scene Config now lives in the composer's bottom-left controls row, not the header.
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport />);
    expect(screen.queryByRole("button", { name: /scene configuration/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader model status", () => {
  const health = (over: Partial<import("@/lib/types").LlmHealth> = {}) => ({
    state: "reachable" as const,
    backend: "llamacpp",
    model: "test-model",
    checkedAt: "2026-08-22T00:00:00Z",
    detail: "test-model is served by this endpoint.",
    ...over,
  });

  it("shows nothing until the first check has answered", () => {
    // A light that guesses is worse than one that waits.
    render(<SceneHeader title="Salt" settingName="Hearth" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reports readiness in words, not only by colour", () => {
    render(<SceneHeader title="Salt" settingName="Hearth" health={health()} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/model ready/i);
    expect(status).toHaveAccessibleName(/model ready/i);
  });

  it("distinguishes a missing model from a dead endpoint", () => {
    // They are different problems with different fixes — a typo in Options versus a dead
    // process — and a single "something is wrong" would send the player to the wrong one.
    const { rerender } = render(
      <SceneHeader title="Salt" settingName="Hearth" health={health({ state: "model_missing" })} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/model not found/i);

    rerender(<SceneHeader title="Salt" settingName="Hearth" health={health({ state: "unreachable" })} />);
    expect(screen.getByRole("status")).toHaveTextContent(/model unreachable/i);
  });

  it("says nothing is set up rather than raising an alarm", () => {
    render(<SceneHeader title="Salt" settingName="Hearth" health={health({ state: "unconfigured" })} />);
    expect(screen.getByRole("status")).toHaveTextContent(/no model set/i);
  });

  it("carries the endpoint's own explanation in the accessible name", () => {
    render(
      <SceneHeader
        title="Salt"
        settingName="Hearth"
        health={health({ state: "unreachable", detail: "The endpoint answered 503." })}
      />,
    );
    expect(screen.getByRole("status")).toHaveAccessibleName(/the endpoint answered 503/i);
  });
});

