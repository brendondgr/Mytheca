import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { OptionsView } from "./OptionsView";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("OptionsView", () => {
  it("opens on the Language Models tab and shows the back link", async () => {
    render(<OptionsView />);
    expect(screen.getByRole("tab", { name: /language models/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/");
    // base-URL field hydrates from the (async) settings load
    expect(
      await screen.findByPlaceholderText("http://localhost:7070/v1"),
    ).toBeInTheDocument();
  });

  it("switches tabs by click", async () => {
    const user = userEvent.setup();
    render(<OptionsView />);
    await user.click(screen.getByRole("tab", { name: /appearance/i }));
    expect(
      screen.getByRole("heading", { name: /appearance/i, level: 2 }),
    ).toBeInTheDocument();
  });

  it("navigates tabs with the arrow keys (vertical tablist)", async () => {
    const user = userEvent.setup();
    render(<OptionsView />);
    const first = screen.getByRole("tab", { name: /language models/i });
    first.focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("tab", { name: /image generation/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("renders the diagnostics tab with backend health", async () => {
    const user = userEvent.setup();
    render(<OptionsView />);
    await user.click(screen.getByRole("tab", { name: /about/i }));
    const panel = screen.getByRole("tabpanel", { name: /about/i });
    expect(await within(panel).findByText("ok")).toBeInTheDocument();
  });
});
