import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneHeader } from "./SceneHeader";

describe("SceneHeader export control", () => {
  // Export is no longer an inline header control: it folded into the scene menu along with
  // the Inspector toggle and the new Writing item, so the header can gain capability while
  // losing width. The behaviour it had is unchanged — it is one click further in.
  it("exports as Markdown from the scene menu", async () => {
    const onExport = vi.fn();
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={onExport} canExport />);

    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /export as markdown/i }));
    expect(onExport).toHaveBeenCalledWith("md");
  });

  it("exports as JSON from the scene menu", async () => {
    const onExport = vi.fn();
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={onExport} canExport />);

    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /export as json/i }));
    expect(onExport).toHaveBeenCalledWith("json");
  });

  it("disables the export items until a session exists, and says why", async () => {
    // A disabled control with no explanation reads as a bug.
    render(
      <SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport={false} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    const md = screen.getByRole("menuitem", { name: /export as markdown/i });
    expect(md).toBeDisabled();
    expect(md).toHaveTextContent(/nothing to export until the scene has a turn/i);
  });

  it("omits the export items when no export handler is given", async () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" onToggleInspector={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.queryByRole("menuitem", { name: /export as/i })).not.toBeInTheDocument();
  });

  it("shows no scene menu at all when it would be empty", () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" />);
    expect(screen.queryByRole("button", { name: /scene menu/i })).not.toBeInTheDocument();
  });
});

describe("SceneHeader scene menu", () => {
  it("carries the Inspector as a toggle that announces its state", async () => {
    const onToggleInspector = vi.fn();
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        onToggleInspector={onToggleInspector}
        inspectorOpen
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    const item = screen.getByRole("menuitemcheckbox", { name: /turn inspector/i });
    expect(item).toHaveAttribute("aria-checked", "true");

    await userEvent.click(item);
    expect(onToggleInspector).toHaveBeenCalled();
    // A toggle keeps the panel open — closing it would hide the state change just made.
    expect(screen.getByRole("menu", { name: /scene menu/i })).toBeInTheDocument();
  });

  it("opens the writing prompts", async () => {
    const onOpenWriting = vi.fn();
    render(
      <SceneHeader title="Standoff" settingName="Hearth" onOpenWriting={onOpenWriting} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /writing/i }));
    expect(onOpenWriting).toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" onExport={vi.fn()} canExport />);
    await userEvent.click(screen.getByRole("button", { name: /scene menu/i }));
    expect(screen.getByRole("menu", { name: /scene menu/i })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu", { name: /scene menu/i })).not.toBeInTheDocument();
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
    const menuBtn = screen.getByRole("button", { name: /scene menu/i });
    // The switch precedes the scene menu in the DOM (to its left).
    expect(group.compareDocumentPosition(menuBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

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

