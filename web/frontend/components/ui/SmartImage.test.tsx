import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { SmartImage } from "./SmartImage";

describe("SmartImage", () => {
  it("reserves the frame's space before the image exists", () => {
    const { container } = render(
      <SmartImage src="/media/portraits/mei.webp" alt="Mei" aspect="2 / 3" />,
    );
    // Space is reserved on the frame, not by the image: nothing below can move
    // when the picture lands.
    const frame = container.firstElementChild as HTMLElement;
    expect(frame.style.aspectRatio).toBe("2 / 3");
  });

  it("stays transparent until the image actually loads", () => {
    render(<SmartImage src="/media/portraits/mei.webp" alt="Mei" aspect="2 / 3" />);
    const img = screen.getByAltText("Mei");
    expect(img).not.toHaveAttribute("data-loaded");

    fireEvent.load(img);
    expect(img).toHaveAttribute("data-loaded", "true");
  });

  it("reveals an image that was ALREADY cached on mount", () => {
    // The load event does not fire for an image the browser already has, so a
    // fade-in keyed only to onLoad leaves cached images permanently invisible.
    // This is the most common bug in hand-rolled image fade-ins, and the whole
    // reason SmartImage checks `complete` itself.
    const proto = Object.getPrototypeOf(new Image());
    const complete = Object.getOwnPropertyDescriptor(proto, "complete");
    const naturalWidth = Object.getOwnPropertyDescriptor(proto, "naturalWidth");
    Object.defineProperty(proto, "complete", { configurable: true, get: () => true });
    Object.defineProperty(proto, "naturalWidth", { configurable: true, get: () => 832 });

    try {
      render(<SmartImage src="/media/portraits/cached.webp" alt="Cached" aspect="2 / 3" />);
      expect(screen.getByAltText("Cached")).toHaveAttribute("data-loaded", "true");
    } finally {
      if (complete) Object.defineProperty(proto, "complete", complete);
      if (naturalWidth) Object.defineProperty(proto, "naturalWidth", naturalWidth);
    }
  });

  it("keeps the placeholder when the image fails, rather than a torn-page glyph", () => {
    render(
      <SmartImage
        src="/media/portraits/gone.webp"
        alt="Missing"
        aspect="2 / 3"
        placeholder={<span>MEI</span>}
      />,
    );
    fireEvent.error(screen.getByAltText("Missing"));
    expect(screen.getByText("MEI")).toBeInTheDocument();
    expect(screen.getByAltText("Missing")).not.toHaveAttribute("data-loaded");
  });

  it("shows the placeholder when there is no image at all", () => {
    render(
      <SmartImage src={null} alt="" aspect="16 / 9" placeholder={<span>No scene art yet</span>} />,
    );
    expect(screen.getByText("No scene art yet")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("loads the LCP image eagerly", () => {
    render(<SmartImage src="/media/hero.webp" alt="Hero" aspect="16 / 9" priority />);
    const img = screen.getByAltText("Hero");
    // Lazy-loading the largest above-the-fold image is a direct LCP regression.
    expect(img).toHaveAttribute("loading", "eager");
    expect(img).toHaveAttribute("decoding", "sync");
  });

  it("lazy-loads below-fold media by default", () => {
    render(<SmartImage src="/media/card.webp" alt="Card" aspect="16 / 9" />);
    expect(screen.getByAltText("Card")).toHaveAttribute("loading", "lazy");
  });
});
