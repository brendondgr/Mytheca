import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ExportMenu } from "./ExportMenu";

describe("ExportMenu", () => {
  it("opens the menu and exports the chosen format", async () => {
    const onExport = vi.fn();
    render(<ExportMenu onExport={onExport} />);
    const trigger = screen.getByRole("button", { name: /export/i });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");

    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByRole("menuitem", { name: /markdown/i }));
    expect(onExport).toHaveBeenCalledWith("md");

    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("menuitem", { name: /json/i }));
    expect(onExport).toHaveBeenCalledWith("json");
  });

  it("is disabled (and inert) until there is something to export", async () => {
    const onExport = vi.fn();
    render(<ExportMenu onExport={onExport} disabled />);
    const trigger = screen.getByRole("button", { name: /export/i });
    expect(trigger).toBeDisabled();
    await userEvent.click(trigger);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    render(<ExportMenu onExport={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /export/i }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
