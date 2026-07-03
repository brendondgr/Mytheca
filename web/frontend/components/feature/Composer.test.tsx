import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("renders the scene-config menu button to the left of the input", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        maxTurns={5}
        onMaxTurnsChange={() => {}}
        suggestionsCount={4}
        onSuggestionsCountChange={() => {}}
        contextBeats={14}
        onContextBeatsChange={() => {}}
      />,
    );
    const config = screen.getByRole("button", { name: /scene configuration/i });
    const input = screen.getByRole("textbox", { name: /your message/i });
    expect(config).toBeInTheDocument();
    // The config menu precedes the input in DOM order (it sits to its left).
    expect(config.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The controls live inside the popover, closed by default.
    expect(screen.queryByRole("combobox", { name: /max turns/i })).not.toBeInTheDocument();
  });

  it("still sends the typed message", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(onSend).toHaveBeenCalled();
  });
});
