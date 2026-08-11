import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { BuildWorldModal } from "./BuildWorldModal";

const DEFAULTS = { enabled: true, withArtwork: false };

describe("BuildWorldModal", () => {
  it("offers to build the cast by default, with artwork opted out", async () => {
    render(
      <BuildWorldModal open defaults={DEFAULTS} onCancel={vi.fn()} onConfirm={vi.fn()} />,
    );
    expect(screen.getByRole("dialog")).toHaveAccessibleName(/build the cast and settings/i);
    expect(screen.getByRole("checkbox", { name: /write the characters/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /paint portraits/i })).not.toBeChecked();
  });

  it("confirms with the author's choices", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <BuildWorldModal open defaults={DEFAULTS} onCancel={vi.fn()} onConfirm={onConfirm} />,
    );

    await user.click(screen.getByRole("checkbox", { name: /paint portraits/i }));
    await user.click(screen.getByRole("button", { name: /create & build/i }));

    expect(onConfirm).toHaveBeenCalledWith({ enabled: true, withArtwork: true });
  });

  it("creates the world alone when the cast is declined", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <BuildWorldModal open defaults={DEFAULTS} onCancel={vi.fn()} onConfirm={onConfirm} />,
    );

    await user.click(screen.getByRole("button", { name: /just the world/i }));

    expect(onConfirm).toHaveBeenCalledWith({ enabled: false, withArtwork: false });
  });

  it("cannot ask for artwork without the cast it would paint", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <BuildWorldModal open defaults={DEFAULTS} onCancel={vi.fn()} onConfirm={onConfirm} />,
    );

    await user.click(screen.getByRole("checkbox", { name: /paint portraits/i }));
    await user.click(screen.getByRole("checkbox", { name: /write the characters/i }));

    expect(screen.getByRole("checkbox", { name: /paint portraits/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /create world/i }));
    expect(onConfirm).toHaveBeenCalledWith({ enabled: false, withArtwork: false });
  });

  it("is keyboard-dismissible and returns nothing on cancel", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <BuildWorldModal open defaults={DEFAULTS} onCancel={onCancel} onConfirm={onConfirm} />,
    );

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
