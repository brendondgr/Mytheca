import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SettingCard } from "./SettingCard";
import type { Setting } from "@/lib/types";

const base: Setting = {
  id: "s1",
  name: "Shadow Keep",
  type: "Fortress",
  desc: "A grim, stone-carved monolith standing watch.",
  image: null,
};

describe("SettingCard", () => {
  it("falls back to the striped plate when there is no image", () => {
    render(<SettingCard setting={base} />);
    expect(screen.getByText(/setting plate/i)).toBeInTheDocument();
    expect(screen.queryByAltText(/establishing image of/i)).toBeNull();
  });

  it("renders a full-bleed establishing image when set", () => {
    render(<SettingCard setting={{ ...base, image: "/media/scenes/keep.webp" }} />);
    const img = screen.getByAltText("Establishing image of Shadow Keep");
    expect(img).toHaveAttribute("src", expect.stringContaining("keep.webp"));
    expect(img).toHaveClass("object-cover");
    expect(img.className).toMatch(/inset-0/);
    expect(screen.queryByText(/setting plate/i)).toBeNull();
  });

  it("renders name, type, and description", () => {
    render(<SettingCard setting={base} />);
    expect(screen.getByText("Shadow Keep")).toBeInTheDocument();
    expect(screen.getByText("Fortress")).toBeInTheDocument();
    expect(screen.getByText(/grim, stone-carved monolith/i)).toBeInTheDocument();
  });

  it("marks the active setting with a label + aria-current", () => {
    const { rerender, container } = render(<SettingCard setting={base} active />);
    expect(screen.getByText(/in this scene/i)).toBeInTheDocument();
    expect(container.querySelector('[aria-current="true"]')).not.toBeNull();
    rerender(<SettingCard setting={base} />);
    expect(screen.queryByText(/in this scene/i)).toBeNull();
    expect(container.querySelector('[aria-current="true"]')).toBeNull();
  });

  it("glows in the theme accent color only when active", () => {
    const { container, rerender } = render(<SettingCard setting={base} />);
    const card = container.firstElementChild as HTMLElement;
    expect(card.className).not.toContain("velora-glow");
    expect(card.style.getPropertyValue("--glow-color")).toBe("");

    rerender(<SettingCard setting={base} active />);
    expect(card.className).toContain("velora-glow");
    expect(card.style.getPropertyValue("--glow-color")).toBe("var(--accent)");
  });

  it("fires onEdit from the pencil", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(<SettingCard setting={base} onEdit={onEdit} />);
    await user.click(screen.getByRole("button", { name: /edit shadow keep/i }));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });
});
