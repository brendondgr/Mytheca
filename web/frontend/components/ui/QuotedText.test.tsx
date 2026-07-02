import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { QuotedText } from "./QuotedText";

describe("QuotedText", () => {
  it("bolds a straight-quoted span, keeping the quotes visible", () => {
    const { container } = render(<QuotedText text={'She said "back off" and left.'} />);
    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong?.textContent).toBe('"back off"'); // quotes preserved inside the bold run
    expect(container.textContent).toBe('She said "back off" and left.'); // nothing dropped
  });

  it("bolds a curly-quoted span too", () => {
    const { container } = render(<QuotedText text={"He whispered “it’s a trap”."} />);
    const strong = container.querySelector("strong");
    expect(strong?.textContent).toBe("“it’s a trap”");
  });

  it("bolds multiple quoted runs and leaves unquoted text plain", () => {
    const { container } = render(<QuotedText text={'"Yes." Then, softer: "maybe."'} />);
    const strongs = [...container.querySelectorAll("strong")].map((s) => s.textContent);
    expect(strongs).toEqual(['"Yes."', '"maybe."']);
  });

  it("renders plain text with no bold when there are no quotes", () => {
    const { container } = render(<QuotedText text="Just narration, no quotes." />);
    expect(container.querySelector("strong")).toBeNull();
    expect(screen.getByText("Just narration, no quotes.")).toBeTruthy();
  });
});
