import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Modal } from "./Modal";

function Fixture({ onClose }: { onClose: () => void }) {
  return (
    <Modal open onClose={onClose} ariaLabel="Test dialog">
      <button>Inside</button>
    </Modal>
  );
}

describe("Modal", () => {
  it("renders an accessible dialog and moves focus inside", () => {
    render(<Fixture onClose={() => {}} />);
    expect(
      screen.getByRole("dialog", { name: "Test dialog" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inside" })).toHaveFocus();
  });

  it("calls onClose on Escape", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Fixture onClose={onClose} />);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose on backdrop click", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Fixture onClose={onClose} />);
    await user.click(screen.getByTestId("modal-overlay"));
    expect(onClose).toHaveBeenCalled();
  });
});
