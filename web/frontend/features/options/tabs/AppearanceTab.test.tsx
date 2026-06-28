import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { AppearanceTab } from "./AppearanceTab";

const setTheme = vi.fn();
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", setTheme }),
}));

const setFontSize = vi.fn();
vi.mock("@/hooks/use-font-size", () => ({
  useFontSize: () => ({ fontSize: "default", setFontSize }),
}));

describe("AppearanceTab — theme picker", () => {
  it("renders label-free colored swatches and switches theme", async () => {
    const user = userEvent.setup();
    render(<AppearanceTab />);

    const themeGroup = screen.getByRole("radiogroup", { name: /theme/i });
    const radios = Array.from(themeGroup.querySelectorAll('[role="radio"]'));
    expect(radios).toHaveLength(3);
    // Parchment is active (theme = light); accessible names come from aria-label.
    expect(screen.getByRole("radio", { name: /parchment/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    await user.click(screen.getByRole("radio", { name: /slate/i }));
    expect(setTheme).toHaveBeenCalledWith("slate");
  });
});

describe("AppearanceTab — text size picker", () => {
  it("renders all four font-size preset buttons", () => {
    render(<AppearanceTab />);
    expect(screen.getByRole("radio", { name: /compact/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /default/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /comfortable/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /large/i })).toBeInTheDocument();
  });

  it("marks the active preset as aria-checked", () => {
    render(<AppearanceTab />);
    expect(screen.getByRole("radio", { name: /default/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: /compact/i })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("calls setFontSize when a preset is clicked", async () => {
    const user = userEvent.setup();
    render(<AppearanceTab />);
    await user.click(screen.getByRole("radio", { name: /comfortable/i }));
    expect(setFontSize).toHaveBeenCalledWith("comfortable");
  });

  it("has a radiogroup with the correct accessible name", () => {
    render(<AppearanceTab />);
    expect(
      screen.getByRole("radiogroup", { name: /text size/i }),
    ).toBeInTheDocument();
  });
});
