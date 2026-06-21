import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { THEME_STORAGE_KEY } from "@/lib/theme";
import { ThemeSwitcher } from "./ThemeSwitcher";

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    document.documentElement.className = "theme-light";
    localStorage.clear();
  });

  it("marks the active theme with aria-pressed", () => {
    render(<ThemeSwitcher />);
    expect(
      screen.getByRole("button", { name: /parchment/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("switches the <html> theme class and persists the choice", async () => {
    const user = userEvent.setup();
    render(<ThemeSwitcher />);

    await user.click(screen.getByRole("button", { name: /ember/i }));
    expect(document.documentElement.classList.contains("theme-dark")).toBe(true);
    expect(document.documentElement.classList.contains("theme-light")).toBe(false);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    await user.click(screen.getByRole("button", { name: /slate/i }));
    expect(document.documentElement.classList.contains("theme-slate")).toBe(true);
    expect(document.documentElement.classList.contains("theme-dark")).toBe(false);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("slate");
  });
});
