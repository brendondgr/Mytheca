import { render, screen, fireEvent } from "@testing-library/react";
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

describe("SceneHeader config control", () => {
  it("renders Config button when a config handler is provided", () => {
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        onMaxTurnsChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /scene configuration/i })).toBeInTheDocument();
  });

  it("omits Config when no config handlers are provided", () => {
    render(<SceneHeader title="Standoff" settingName="Hearth" />);
    expect(screen.queryByRole("button", { name: /scene configuration/i })).not.toBeInTheDocument();
  });

  it("Config button appears before (left of) Export in DOM order", () => {
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        onExport={vi.fn()}
        canExport
        onMaxTurnsChange={vi.fn()}
      />,
    );
    const configBtn = screen.getByRole("button", { name: /scene configuration/i });
    const exportBtn = screen.getByRole("button", { name: /export/i });
    // Config precedes Export in DOM order (Config is to its left).
    expect(
      configBtn.compareDocumentPosition(exportBtn) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("opening Config shows the config dialog with controls", async () => {
    const user = userEvent.setup();
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        maxTurns={5}
        onMaxTurnsChange={vi.fn()}
        suggestionsCount={4}
        onSuggestionsCountChange={vi.fn()}
        contextBeats={14}
        onContextBeatsChange={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    expect(screen.getByRole("dialog", { name: /scene configuration/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /max turns/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /suggestions/i })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: /number of beats/i })).toBeInTheDocument();
  });

  it("a handler fired from the header config dialog calls the provided callback", async () => {
    const user = userEvent.setup();
    const onMaxTurnsChange = vi.fn();
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        maxTurns={5}
        onMaxTurnsChange={onMaxTurnsChange}
        suggestionsCount={4}
        onSuggestionsCountChange={vi.fn()}
        contextBeats={14}
        onContextBeatsChange={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /max turns/i }), "3");
    expect(onMaxTurnsChange).toHaveBeenCalledWith(3);
  });

  it("beats slider in the header config dialog fires its handler", async () => {
    const user = userEvent.setup();
    const onContextBeatsChange = vi.fn();
    render(
      <SceneHeader
        title="Standoff"
        settingName="Hearth"
        contextBeats={14}
        onContextBeatsChange={onContextBeatsChange}
      />,
    );
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    fireEvent.change(screen.getByRole("slider", { name: /number of beats/i }), {
      target: { value: "40" },
    });
    expect(onContextBeatsChange).toHaveBeenCalledWith(40);
  });
});
