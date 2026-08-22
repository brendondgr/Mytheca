import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AppHeader } from "./AppHeader";

describe("AppHeader Mytheca brand", () => {
  it("renders the MYTHECA wordmark", () => {
    render(<AppHeader query="" onQuery={vi.fn()} />);
    expect(screen.getByText("MYTHECA")).toBeInTheDocument();
  });

  it("renders the theme-aware brand emblem (CSS swaps the icon per theme)", () => {
    const { container } = render(<AppHeader query="" onQuery={vi.fn()} />);
    // The emblem is a decorative span; `.mytheca-brandmark` carries the dark icon
    // by default and CSS (.theme-dark/.theme-slate .mytheca-brandmark) swaps to
    // the cream icon on the dark themes.
    const emblem = container.querySelector(".mytheca-brandmark");
    expect(emblem).not.toBeNull();
    expect(emblem).toHaveAttribute("aria-hidden");
  });
});

describe("AppHeader storyline slot", () => {
  it("renders the switcher at every width, with no width-gated wrapper", () => {
    // It used to sit inside `hidden md:block`, which made a phone a single-world device:
    // deep links already worked, the control simply did not exist there.
    const { container } = render(
      <AppHeader
        query=""
        onQuery={vi.fn()}
        storylineSlot={<button type="button" data-testid="switcher">Switch</button>}
      />,
    );
    const slot = screen.getByTestId("switcher");
    expect(slot).toBeInTheDocument();

    for (let el = slot.parentElement; el && el !== container; el = el.parentElement) {
      expect(el.className).not.toMatch(/(^|\s)hidden(\s|$)/);
    }
  });

  it("keeps the divider decoration md-gated", () => {
    const { container } = render(
      <AppHeader query="" onQuery={vi.fn()} storylineSlot={<span>Switch</span>} />,
    );
    expect(container.querySelector("span.hidden.md\\:block[aria-hidden]")).not.toBeNull();
  });
});
