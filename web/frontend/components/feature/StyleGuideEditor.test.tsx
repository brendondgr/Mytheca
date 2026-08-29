import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StyleGuideEditor } from "./StyleGuideEditor";
import type { StyleBlockSpec, StylePreset } from "@/lib/api";

const CATALOG: StyleBlockSpec[] = [
  {
    id: "attention",
    label: "Attention",
    helper: "What the prose dwells on.",
    placeholder: "Dwell on hands…",
    reader: "prose",
    placement: "prefix",
  },
  {
    id: "voice",
    label: "Voice",
    helper: "How people sound.",
    placeholder: "People talk around it…",
    reader: "prose",
    placement: "prefix",
  },
  {
    id: "signature",
    label: "Signature",
    helper: "The whole guide in one clause.",
    placeholder: "Low and slow.",
    reader: "prose",
    placement: "tail",
  },
];

const PRESETS: StylePreset[] = [
  {
    id: "romance",
    name: "Romance",
    blurb: "Close and unsaid.",
    blocks: { attention: "Proximity.", voice: "Less than they mean.", signature: "Close." },
    builtin: true,
  },
];

const field = (label: string) =>
  screen.getByRole("textbox", { name: new RegExp(`${label} — style`, "i") }) as HTMLTextAreaElement;

describe("StyleGuideEditor", () => {
  it("renders one field per block, empty when nothing is set", () => {
    render(
      <StyleGuideEditor catalog={CATALOG} presets={[]} blocks={{}} onSave={vi.fn()} />,
    );
    expect(field("Attention").value).toBe("");
    expect(field("Voice").value).toBe("");
    expect(field("Signature").value).toBe("");
  });

  it("does not prefill inherited text into the field itself", () => {
    // The whole reason this editor is not built like PromptOverridesEditor: prefilling
    // would make an unset block look set, and clearing it would look like deleting text.
    render(
      <StyleGuideEditor
        catalog={CATALOG}
        presets={[]}
        blocks={{}}
        inherited={{ voice: "The world's voice." }}
        layer="scenario"
        onSave={vi.fn()}
      />,
    );
    expect(field("Voice").value).toBe("");
    expect(field("Voice").placeholder).toBe("The world's voice.");
    expect(screen.getByText(/inheriting from the world/i)).toBeInTheDocument();
  });

  it("labels each block with the layer supplying its value", () => {
    render(
      <StyleGuideEditor
        catalog={CATALOG}
        presets={[]}
        blocks={{ attention: "Mine." }}
        inherited={{ voice: "Theirs." }}
        layer="scenario"
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByText("This scene")).toBeInTheDocument();
    expect(screen.getByText("This world")).toBeInTheDocument();
    expect(screen.getByText("Not set")).toBeInTheDocument();
  });

  it("clearing a field marks the block inherited again", async () => {
    const user = userEvent.setup();
    render(
      <StyleGuideEditor
        catalog={CATALOG}
        presets={[]}
        blocks={{ voice: "Mine." }}
        inherited={{ voice: "Theirs." }}
        layer="scenario"
        onSave={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /use the world's voice/i }));
    expect(field("Voice").value).toBe("");
    expect(screen.getByText("This world")).toBeInTheDocument();
  });

  it("saves only non-blank blocks, trimmed", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <StyleGuideEditor catalog={CATALOG} presets={[]} blocks={{}} onSave={onSave} />,
    );
    await user.type(field("Voice"), "  Plain.  ");
    await user.click(screen.getByRole("button", { name: /save style/i }));
    expect(onSave).toHaveBeenCalledWith({ voice: "Plain." });
  });

  it("can clear every block, so a world opts back out entirely", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <StyleGuideEditor
        catalog={CATALOG}
        presets={[]}
        blocks={{ voice: "Plain." }}
        onSave={onSave}
      />,
    );
    await user.click(screen.getByRole("button", { name: /clear voice/i }));
    await user.click(screen.getByRole("button", { name: /save style/i }));
    expect(onSave).toHaveBeenCalledWith({});
  });

  it("applying a preset fills the fields and leaves them editable", async () => {
    const user = userEvent.setup();
    render(
      <StyleGuideEditor catalog={CATALOG} presets={PRESETS} blocks={{}} onSave={vi.fn()} />,
    );
    await user.click(screen.getByRole("button", { name: "Romance" }));
    expect(field("Attention").value).toBe("Proximity.");
    await user.clear(field("Attention"));
    await user.type(field("Attention"), "Mine instead.");
    expect(field("Attention").value).toBe("Mine instead.");
  });

  it("the save button stays disabled until something actually changes", async () => {
    const user = userEvent.setup();
    render(
      <StyleGuideEditor
        catalog={CATALOG}
        presets={[]}
        blocks={{ voice: "Plain." }}
        onSave={vi.fn()}
      />,
    );
    const save = screen.getByRole("button", { name: /save style/i });
    expect(save).toBeDisabled();
    // Whitespace-only edits are not changes: the backend trims them away too.
    await user.type(field("Voice"), "   ");
    expect(save).toBeDisabled();
    await user.type(field("Voice"), "Short.");
    expect(save).toBeEnabled();
  });

  it("offers Save as preset only when a handler is given and something is set", async () => {
    const user = userEvent.setup();
    const onSavePreset = vi.fn();
    const { unmount } = render(
      <StyleGuideEditor catalog={CATALOG} presets={[]} blocks={{}} onSave={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: /save as preset/i })).not.toBeInTheDocument();
    unmount();

    // A fresh mount, not a rerender: the editor seeds its draft once, by design — see the
    // component doc, and `StyleGuideModal`'s key.
    render(
      <StyleGuideEditor
        catalog={CATALOG}
        presets={[]}
        blocks={{ voice: "Plain." }}
        onSave={vi.fn()}
        onSavePreset={onSavePreset}
      />,
    );
    await user.click(screen.getByRole("button", { name: /save as preset/i }));
    expect(onSavePreset).toHaveBeenCalledWith({ voice: "Plain." });
  });

  it("surfaces a save failure instead of closing over it", async () => {
    const user = userEvent.setup();
    render(
      <StyleGuideEditor
        catalog={CATALOG}
        presets={[]}
        blocks={{}}
        onSave={() => Promise.reject(new Error("nope"))}
      />,
    );
    await user.type(field("Voice"), "Plain.");
    await user.click(screen.getByRole("button", { name: /save style/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("nope");
  });
});
