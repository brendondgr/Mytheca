import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, it, expect, vi } from "vitest";
import { OptionsMenu } from "./OptionsMenu";

const setTheme = vi.fn();
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", setTheme }),
}));

/**
 * Make `useMediaQuery` answer for a given width.
 *
 * jsdom does not implement `matchMedia` and the shared setup stubs it to `matches: false`,
 * which is the NARROW form. That is the right default — it is what the server renders — but
 * it means the wide form is only exercised by a test that asks for it.
 */
function atWidth(width: number) {
  window.matchMedia = ((query: string) =>
    ({
      matches: (() => {
        const min = Number(/min-width:\s*(\d+)px/.exec(query)?.[1] ?? NaN);
        return Number.isNaN(min) ? false : width >= min;
      })(),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList) as typeof window.matchMedia;
}

const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

describe("OptionsMenu at sm and above", () => {
  it("opens, links to /options, and switches theme via colored swatches", async () => {
    atWidth(1024);
    const user = userEvent.setup();
    render(<OptionsMenu />);

    const trigger = screen.getByRole("button", { name: /options/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    expect(screen.getByRole("link", { name: /settings menu/i })).toHaveAttribute(
      "href",
      "/options",
    );

    await user.click(screen.getByRole("button", { name: /ember/i }));
    expect(setTheme).toHaveBeenCalledWith("dark");
  });

  it("closes on Escape", async () => {
    atWidth(1024);
    const user = userEvent.setup();
    render(<OptionsMenu />);
    const trigger = screen.getByRole("button", { name: /options/i });
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});

describe("OptionsMenu below sm", () => {
  it("is a link to the page, not a popover holding a link to the page", () => {
    // The dropdown's real content is one link to `/options`; the theme swatches beside it
    // are on the page it leads to, under Appearance. On a phone that makes the popover a
    // tap that buys a second tap.
    atWidth(390);
    render(<OptionsMenu />);

    const link = screen.getByRole("link", { name: /options/i });
    expect(link).toHaveAttribute("href", "/options");
    expect(screen.queryByRole("button", { name: /options/i })).not.toBeInTheDocument();
    // Nothing is lost: the swatches were never the reason anyone opened this.
    expect(screen.queryByRole("group", { name: /theme/i })).not.toBeInTheDocument();
  });
});
