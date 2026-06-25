import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { LibraryView } from "./LibraryView";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("LibraryView — URL ↔ active-storyline sync", () => {
  let replaceSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    replaceSpy = vi.spyOn(window.history, "replaceState");
  });
  afterEach(() => {
    replaceSpy.mockRestore();
  });

  const urls = () => replaceSpy.mock.calls.map((c: unknown[]) => c[2]);

  it("reflects the active storyline into the URL as /{id} after load", async () => {
    render(<LibraryView initialStorylineId="embergate" />);
    await screen.findAllByText("The Embergate Conspiracy");
    await waitFor(() => expect(urls()).toContain("/embergate"));
  });

  it("still loads (falls back) when the deep-linked id is unknown", async () => {
    render(<LibraryView initialStorylineId="nonexistent" />);
    // Falls back to the first storyline; the library still renders its scenarios.
    expect(await screen.findAllByText("The Embergate Conspiracy")).not.toHaveLength(0);
    await waitFor(() => expect(urls()).toContain("/embergate"));
  });
});
