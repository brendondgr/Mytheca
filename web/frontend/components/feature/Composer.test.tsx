import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("does not render a Config button (Config lives in the SceneHeader)", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /scene configuration/i })).not.toBeInTheDocument();
    // The input and Send button are present.
    expect(screen.getByRole("textbox", { name: /your message/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("still sends the typed message", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(onSend).toHaveBeenCalled();
  });
});
