import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SealModal } from "./SealModal";

function renderSeal(over: Partial<Parameters<typeof SealModal>[0]> = {}) {
  const onSymbolChange = vi.fn();
  const onColorChange = vi.fn();
  render(
    <SealModal
      open
      onClose={vi.fn()}
      symbol="◆"
      color="#C8862A"
      onSymbolChange={onSymbolChange}
      onColorChange={onColorChange}
      {...over}
    />,
  );
  return { onSymbolChange, onColorChange };
}

describe("SealModal", () => {
  it("offers the expanded shape set and reports a pick", () => {
    const { onSymbolChange } = renderSeal();
    // ~3× the original eight shapes.
    expect(screen.getByRole("group", { name: "Seal symbol" }).querySelectorAll("button").length)
      .toBeGreaterThanOrEqual(20);
    fireEvent.click(screen.getByRole("button", { name: "Symbol ★" }));
    expect(onSymbolChange).toHaveBeenCalledWith("★");
  });

  it("writes a custom hex from the color wheel", () => {
    const { onColorChange } = renderSeal();
    fireEvent.change(screen.getByLabelText("Custom seal color"), {
      target: { value: "#123456" },
    });
    expect(onColorChange).toHaveBeenCalledWith("#123456");
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <SealModal
        open={false}
        onClose={vi.fn()}
        symbol="◆"
        color="#C8862A"
        onSymbolChange={vi.fn()}
        onColorChange={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
