import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { BuildWorldModal } from "./BuildWorldModal";
import * as api from "@/lib/api";
import { emptyBuild, type BuildState } from "@/features/library/worldBuild";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

beforeEach(() => vi.clearAllMocks());

const DEFAULTS = { enabled: true, withArtwork: false };

function show(build: BuildState = emptyBuild(), props: Record<string, unknown> = {}) {
  const handlers = {
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
    onStop: vi.fn(),
    onEnter: vi.fn(),
  };
  render(
    <BuildWorldModal
      open
      build={build}
      defaults={DEFAULTS}
      worldTitle="Embergate"
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

const building = (over: Partial<BuildState> = {}): BuildState => ({
  ...emptyBuild(),
  phase: "building",
  step: "Writing Maerin Voss…",
  index: 1,
  total: 3,
  ...over,
});

const MAERIN = {
  id: "c1",
  kind: "character" as const,
  name: "Maerin Voss",
  role: "Smuggler",
  image: null,
};

describe("BuildWorldModal — asking", () => {
  it("offers to build the cast, and pre-checks artwork when ComfyUI answers", async () => {
    show();
    expect(screen.getByRole("dialog")).toHaveAccessibleName(/build the cast and settings/i);
    expect(screen.getByRole("checkbox", { name: /write the characters/i })).toBeChecked();
    // The probe decides — a running ComfyUI means the author expects images.
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /paint portraits/i })).toBeChecked(),
    );
    expect(screen.getByText(/ComfyUI is running/i)).toBeInTheDocument();
  });

  it("cannot offer artwork when no render server answers", async () => {
    vi.mocked(api.checkComfyStatus).mockResolvedValueOnce({
      ok: false,
      comfyuiVersion: "",
      device: "",
      pythonVersion: "",
    });
    const h = show();

    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /paint portraits/i })).toBeDisabled(),
    );
    expect(screen.getByText(/No ComfyUI server is answering/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create & build/i }));
    expect(h.onConfirm).toHaveBeenCalledWith({ enabled: true, withArtwork: false });
  });

  it("confirms with the author's choices", async () => {
    const user = userEvent.setup();
    const h = show();
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /paint portraits/i })).toBeChecked(),
    );

    await user.click(screen.getByRole("button", { name: /create & build/i }));

    expect(h.onConfirm).toHaveBeenCalledWith({ enabled: true, withArtwork: true });
  });

  it("creates the world alone when the cast is declined", async () => {
    const h = show();
    await userEvent.click(screen.getByRole("button", { name: /just the world/i }));
    expect(h.onConfirm).toHaveBeenCalledWith({ enabled: false, withArtwork: false });
  });
});

describe("BuildWorldModal — building", () => {
  it("shows the step in progress and every entity as it lands", () => {
    show(building({ entities: [MAERIN] }));

    expect(screen.getByRole("dialog")).toHaveAccessibleName(/building embergate/i);
    expect(screen.getByText("Writing Maerin Voss…")).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    const list = screen.getByRole("list");
    expect(within(list).getByText("Maerin Voss")).toBeInTheDocument();
    expect(within(list).getByText("Smuggler")).toBeInTheDocument();
  });

  it("shows a portrait once it has been painted", () => {
    show(building({ entities: [{ ...MAERIN, image: "/media/portraits/m.webp" }] }));
    // The thumbnail sits beside the visible name, so it is decorative (alt="").
    expect(screen.getByRole("presentation")).toHaveAttribute(
      "src",
      expect.stringContaining("/media/portraits/m.webp"),
    );
  });

  it("keeps the author here — no way out but Stop", async () => {
    const user = userEvent.setup();
    const h = show(building());

    expect(screen.queryByRole("button", { name: /enter the world/i })).not.toBeInTheDocument();
    // Escape and the backdrop must not drop the only progress report there is.
    await user.keyboard("{Escape}");
    expect(h.onCancel).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("modal-overlay"));
    expect(h.onCancel).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /stop/i }));
    expect(h.onStop).toHaveBeenCalled();
  });

  it("lists the items that were skipped without stopping the run", () => {
    show(building({ problems: ["Could not render a portrait for Cael: timed out"] }));
    expect(screen.getByText(/skipped/i)).toBeInTheDocument();
    expect(screen.getByText(/Could not render a portrait for Cael/)).toBeInTheDocument();
  });
});

describe("BuildWorldModal — finished", () => {
  it("invites the author in once everything is built", async () => {
    const h = show({ ...emptyBuild(), phase: "done", entities: [MAERIN] });

    expect(screen.getByRole("dialog")).toHaveAccessibleName(/the world is built/i);
    expect(screen.getByText("1 character · 0 settings")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^enter the world$/i }));
    expect(h.onEnter).toHaveBeenCalled();
  });

  it("says so when the build stopped early, and still lets them in", async () => {
    const h = show({
      ...emptyBuild(),
      phase: "failed",
      error: "The build stopped early — the world was only partly built.",
      entities: [MAERIN],
    });

    expect(screen.getByRole("dialog")).toHaveAccessibleName(/stopped early/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/only partly built/i);
    await userEvent.click(screen.getByRole("button", { name: /enter the world anyway/i }));
    expect(h.onEnter).toHaveBeenCalled();
  });
});
