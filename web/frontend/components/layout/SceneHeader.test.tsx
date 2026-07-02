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
