import { useState } from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("renders a textarea with aria-label 'Your message'", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
    expect(screen.getByRole("textbox", { name: /your message/i })).toBeInTheDocument();
  });

  it("omits the Config control when no config handlers are given", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
    expect(screen.queryByRole("button", { name: /scene configuration/i })).not.toBeInTheDocument();
  });

  it("renders the Config control on the bottom row when config handlers are provided", () => {
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
    expect(screen.getByRole("button", { name: /scene configuration/i })).toBeInTheDocument();
  });

  it("renders the context dial as a labelled button when the model window size is known", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        usedTokens={5000}
        maxContextTokens={16384}
        usedTokensExact
      />,
    );
    const dial = screen.getByRole("button", { name: /context usage/i });
    expect(dial.getAttribute("aria-label")).toContain("exact");
  });

  it("omits the context dial when the window size is unknown", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} maxContextTokens={null} />);
    expect(screen.queryByRole("button", { name: /context usage/i })).not.toBeInTheDocument();
  });

  it("typing fires onChange", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Composer value="" onChange={onChange} onSend={() => {}} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    await user.type(ta, "hello");
    expect(onChange).toHaveBeenCalled();
  });

  it("Enter key fires onSend when value is non-empty", () => {
    const onSend = vi.fn();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("Enter key does NOT fire onSend when value is empty", () => {
    const onSend = vi.fn();
    render(<Composer value="" onChange={() => {}} onSend={onSend} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: false });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("Shift+Enter does NOT fire onSend", () => {
    const onSend = vi.fn();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("Send button has aria-label 'Send' and fires onSend on click", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    const btn = screen.getByRole("button", { name: /^send$/i });
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  describe("Player POV", () => {
    const POV_OPTS = [{ id: "mei", name: "Mei", mono: "M", color: "#8E2B1C", portrait: null }];

    it("renders the 'Speaking as' dropdown to the right of Config when a POV handler is given", () => {
      render(
        <Composer
          value=""
          onChange={() => {}}
          onSend={() => {}}
          onMaxTurnsChange={() => {}}
          onPovChange={() => {}}
          povOptions={POV_OPTS}
          pov={null}
        />,
      );
      const config = screen.getByRole("button", { name: /scene configuration/i });
      const pov = screen.getByRole("button", { name: /speaking as/i });
      expect(pov).toBeInTheDocument();
      // POV sits AFTER the Config button in document order (to its right).
      expect(config.compareDocumentPosition(pov) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("omits the POV dropdown when no POV handler is given", () => {
      render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
      expect(screen.queryByRole("button", { name: /speaking as/i })).not.toBeInTheDocument();
    });

    it("placeholder reflects the active POV character", () => {
      render(
        <Composer
          value=""
          onChange={() => {}}
          onSend={() => {}}
          onPovChange={() => {}}
          povOptions={POV_OPTS}
          pov="mei"
        />,
      );
      expect(screen.getByRole("textbox", { name: /your message/i })).toHaveAttribute(
        "placeholder",
        "Speaking as Mei…",
      );
    });

    describe("scene-direction box", () => {
      it("is hidden in narrator mode — the message box already carries the direction", () => {
        render(
          <Composer
            value=""
            onChange={() => {}}
            onSend={() => {}}
            guidance=""
            onGuidanceChange={() => {}}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov={null}
          />,
        );
        expect(screen.queryByRole("textbox", { name: /scene direction/i })).not.toBeInTheDocument();
      });

      it("appears above the message box once the player speaks as a character", () => {
        render(
          <Composer
            value=""
            onChange={() => {}}
            onSend={() => {}}
            guidance=""
            onGuidanceChange={() => {}}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov="mei"
          />,
        );
        const direction = screen.getByRole("textbox", { name: /scene direction/i });
        const message = screen.getByRole("textbox", { name: /your message/i });
        expect(direction).toHaveAttribute("placeholder", "Guide the scene — what happens next…");
        // Direction sits BEFORE the message box in document order (above it on screen).
        expect(
          direction.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
      });

      it("stays hidden when no handler is wired, even under POV", () => {
        render(
          <Composer
            value=""
            onChange={() => {}}
            onSend={() => {}}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov="mei"
          />,
        );
        expect(screen.queryByRole("textbox", { name: /scene direction/i })).not.toBeInTheDocument();
      });

      it("typing fires onGuidanceChange", async () => {
        const onGuidanceChange = vi.fn();
        const user = userEvent.setup();
        render(
          <Composer
            value=""
            onChange={() => {}}
            onSend={() => {}}
            guidance=""
            onGuidanceChange={onGuidanceChange}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov="mei"
          />,
        );
        await user.type(screen.getByRole("textbox", { name: /scene direction/i }), "louder");
        expect(onGuidanceChange).toHaveBeenCalled();
      });

      it("Enter sends from the direction box too, Shift+Enter does not", () => {
        const onSend = vi.fn();
        render(
          <Composer
            value="hello"
            onChange={() => {}}
            onSend={onSend}
            guidance="make it worse"
            onGuidanceChange={() => {}}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov="mei"
          />,
        );
        const direction = screen.getByRole("textbox", { name: /scene direction/i });
        fireEvent.keyDown(direction, { key: "Enter", shiftKey: true });
        expect(onSend).not.toHaveBeenCalled();
        fireEvent.keyDown(direction, { key: "Enter", shiftKey: false });
        expect(onSend).toHaveBeenCalledTimes(1);
      });

      it("Enter sends a direction with no line at all", () => {
        // Direction-only is a real turn: under POV the message box is the character's own
        // words, so requiring a line to send would mean you can only steer the scene by
        // making them talk.
        const onSend = vi.fn();
        render(
          <Composer
            value=""
            onChange={() => {}}
            onSend={onSend}
            guidance="make it worse"
            onGuidanceChange={() => {}}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov="mei"
          />,
        );
        fireEvent.keyDown(screen.getByRole("textbox", { name: /scene direction/i }), {
          key: "Enter",
          shiftKey: false,
        });
        expect(onSend).toHaveBeenCalledTimes(1);
      });

      it("cannot send when both boxes are empty", () => {
        const onSend = vi.fn();
        render(
          <Composer
            value=""
            onChange={() => {}}
            onSend={onSend}
            guidance=""
            onGuidanceChange={() => {}}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov="mei"
          />,
        );
        fireEvent.keyDown(screen.getByRole("textbox", { name: /scene direction/i }), {
          key: "Enter",
          shiftKey: false,
        });
        expect(onSend).not.toHaveBeenCalled();
        expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      });

      it("stays editable while a turn streams", () => {
        render(
          <Composer
            value=""
            onChange={() => {}}
            onSend={() => {}}
            guidance=""
            onGuidanceChange={() => {}}
            onPovChange={() => {}}
            povOptions={POV_OPTS}
            pov="mei"
            sendDisabled
          />,
        );
        expect(screen.getByRole("textbox", { name: /scene direction/i })).not.toBeDisabled();
      });
    });

    it("keeps the default placeholder when POV is Narrator (null)", () => {
      render(
        <Composer
          value=""
          onChange={() => {}}
          onSend={() => {}}
          onPovChange={() => {}}
          povOptions={POV_OPTS}
          pov={null}
        />,
      );
      expect(screen.getByRole("textbox", { name: /your message/i })).toHaveAttribute(
        "placeholder",
        "Speak, or describe what you do…",
      );
    });
  });

  describe("while sendDisabled", () => {
    it("the textarea is NOT disabled — typing still fires onChange", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();
      render(<Composer value="" onChange={onChange} onSend={() => {}} sendDisabled />);
      const ta = screen.getByRole("textbox", { name: /your message/i });
      // textarea must NOT be disabled
      expect(ta).not.toBeDisabled();
      await user.type(ta, "a");
      expect(onChange).toHaveBeenCalled();
    });

    it("Enter does NOT call onSend", () => {
      const onSend = vi.fn();
      render(<Composer value="hello" onChange={() => {}} onSend={onSend} sendDisabled />);
      const ta = screen.getByRole("textbox", { name: /your message/i });
      fireEvent.keyDown(ta, { key: "Enter", shiftKey: false });
      expect(onSend).not.toHaveBeenCalled();
    });

    it("Send button has the disabled attribute", () => {
      render(<Composer value="hello" onChange={() => {}} onSend={() => {}} sendDisabled />);
      const btn = screen.getByRole("button", { name: /^send$/i });
      expect(btn).toBeDisabled();
    });

    it("shows the streaming placeholder", () => {
      render(<Composer value="" onChange={() => {}} onSend={() => {}} sendDisabled />);
      const ta = screen.getByRole("textbox", { name: /your message/i });
      expect(ta).toHaveAttribute("placeholder", "The scene responds…");
    });
  });

  describe("@ file tagging", () => {
    const DOCS = [
      { id: "cd_m", name: "maerin.md", charCount: 812 },
      { id: "cd_h", name: "harbor.md", charCount: 40 },
    ];

    /** Composer is controlled, so typing needs a stateful host. */
    function Harness({
      onSend = () => {},
      pov = null,
      withGuidance = false,
      mentionOptions = DOCS,
      initial = "",
    }: {
      onSend?: () => void;
      pov?: string | null;
      withGuidance?: boolean;
      mentionOptions?: typeof DOCS;
      initial?: string;
    }) {
      const [value, setValue] = useState(initial);
      const [guidance, setGuidance] = useState("");
      return (
        <Composer
          value={value}
          onChange={setValue}
          onSend={onSend}
          mentionOptions={mentionOptions}
          pov={pov}
          onPovChange={pov !== null ? () => {} : undefined}
          povOptions={pov ? [{ id: "mei", name: "Mei", mono: "M", color: "#8E2B1C", portrait: null }] : []}
          guidance={withGuidance ? guidance : undefined}
          onGuidanceChange={withGuidance ? setGuidance : undefined}
        />
      );
    }

    const message = () => screen.getByRole("textbox", { name: /your message/i });
    const direction = () => screen.getByRole("textbox", { name: /scene direction/i });

    it("opens the file list when the player types @", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("@");
      expect(screen.getByRole("listbox", { name: /context files/i })).toBeInTheDocument();
      expect(screen.getAllByRole("option")).toHaveLength(2);
    });

    it("narrows the list as the player keeps typing", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("@mae");
      expect(screen.getAllByRole("option")).toHaveLength(1);
      expect(screen.getByRole("option", { name: /maerin\.md/ })).toBeInTheDocument();
    });

    it("closes the list when nothing matches", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("@zzz");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });

    it("does not open mid-word", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("mail@x");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });

    it("stays inert when no documents are taggable", async () => {
      const user = userEvent.setup();
      render(<Harness mentionOptions={[]} />);
      await user.click(message());
      await user.keyboard("@");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });

    it("Enter selects the highlighted file instead of sending", async () => {
      const user = userEvent.setup();
      const onSend = vi.fn();
      render(<Harness onSend={onSend} />);
      await user.click(message());
      await user.keyboard("@mae{Enter}");
      expect(onSend).not.toHaveBeenCalled();
      expect(message()).toHaveValue("@maerin.md ");
    });

    it("Enter still sends once the list is closed", async () => {
      const user = userEvent.setup();
      const onSend = vi.fn();
      render(<Harness onSend={onSend} initial="ready" />);
      await user.click(message());
      await user.keyboard("{Enter}");
      expect(onSend).toHaveBeenCalledTimes(1);
    });

    it("arrow keys move the highlight and Enter takes that file", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("@{ArrowDown}{Enter}");
      expect(message()).toHaveValue("@harbor.md ");
    });

    it("Escape closes the list and leaves the text alone", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("@mae{Escape}");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(message()).toHaveValue("@mae");
    });

    it("clicking a row inserts it", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("@");
      await user.click(screen.getByRole("option", { name: /harbor\.md/ }));
      expect(message()).toHaveValue("@harbor.md ");
    });

    it("points aria-activedescendant at the highlighted row while open", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await user.click(message());
      await user.keyboard("@mae");
      const active = message().getAttribute("aria-activedescendant");
      expect(active).toBeTruthy();
      expect(screen.getByRole("option", { name: /maerin\.md/ })).toHaveAttribute("id", active!);
      expect(message()).toHaveAttribute("aria-expanded", "true");
    });

    it("lists the tagged file as a chip", async () => {
      const user = userEvent.setup();
      render(<Harness initial="@maerin.md what is she holding?" />);
      const chips = screen.getByRole("list", { name: /tagged in this turn/i });
      expect(within(chips).getByText("maerin.md")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /remove maerin\.md/i }));
      expect(message()).toHaveValue("what is she holding?");
      expect(screen.queryByRole("list", { name: /tagged in this turn/i })).not.toBeInTheDocument();
    });

    it("shows no chip row when nothing is tagged", () => {
      render(<Harness initial="just talking" />);
      expect(screen.queryByRole("list", { name: /tagged in this turn/i })).not.toBeInTheDocument();
    });

    it("works in the scene-direction box too", async () => {
      const user = userEvent.setup();
      render(<Harness pov="mei" withGuidance />);
      await user.click(direction());
      await user.keyboard("@har{Enter}");
      expect(direction()).toHaveValue("@harbor.md ");
      expect(
        within(screen.getByRole("list", { name: /tagged in this turn/i })).getByText("harbor.md"),
      ).toBeInTheDocument();
    });
  });
});

describe("Composer direction row", () => {
  const POV_OPTS = [{ id: "mei", name: "Mei", mono: "M", color: "#8E2B1C", portrait: null }];

  it("shows the direction strip in narrator mode, with no second textarea", () => {
    // Until the row was unconditional, the whole direction concept was invisible to any
    // player who had not happened to pick a POV character — which is most of them.
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov={null}
      />,
    );
    expect(screen.getByText(/this message steers the scene/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: /scene direction/i }),
    ).not.toBeInTheDocument();
  });

  it("swaps the strip for the direction box when a POV is picked", () => {
    const { rerender } = render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov={null}
      />,
    );
    rerender(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov="mei"
      />,
    );
    expect(screen.getByRole("textbox", { name: /scene direction/i })).toBeInTheDocument();
    expect(screen.queryByText(/this message steers the scene/i)).not.toBeInTheDocument();
  });

  it("has no direction row at all when the parent owns no direction", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
    expect(screen.queryByText(/^Direction$/)).not.toBeInTheDocument();
  });

  it("still writes the direction through onGuidanceChange under POV", () => {
    const onGuidanceChange = vi.fn();
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={onGuidanceChange}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov="mei"
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: /scene direction/i }), {
      target: { value: "make it worse" },
    });
    expect(onGuidanceChange).toHaveBeenCalledTimes(1);
    expect(onGuidanceChange).toHaveBeenCalledWith("make it worse");
  });

  it("does not offer Send for a direction that narrator mode will drop", () => {
    // A direction kept across a POV switch (or restored on resume) is inert in narrator
    // mode — the message box IS the direction there, so `send()` drops it. Counting it
    // would light up Send with nothing to post, and the turn would come back a 400.
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance="a direction from earlier"
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov={null}
      />,
    );
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("Composer chip removal", () => {
  const DOCS = [{ id: "cd_m", name: "maerin.md", charCount: 120 }];

  it("the chip's × deletes the whole token, name and all", () => {
    // Stripping now keeps the name and drops only the sigil, so untagging had to become its
    // own operation — routing the × through `stripMentions` would have removed nothing.
    const onChange = vi.fn();
    render(
      <Composer
        value="@maerin.md what is she holding?"
        onChange={onChange}
        onSend={() => {}}
        mentionOptions={DOCS}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove maerin.md" }));
    expect(onChange).toHaveBeenCalledWith("what is she holding?");
  });

  it("also clears the tag from the direction box under POV", () => {
    const onGuidanceChange = vi.fn();
    render(
      <Composer
        value="a line"
        onChange={() => {}}
        onSend={() => {}}
        guidance="@maerin.md the tide turns"
        onGuidanceChange={onGuidanceChange}
        onPovChange={() => {}}
        povOptions={[{ id: "mei", name: "Mei", mono: "M", color: "#8E2B1C", portrait: null }]}
        pov="mei"
        mentionOptions={DOCS}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove maerin.md" }));
    expect(onGuidanceChange).toHaveBeenCalledWith("the tide turns");
  });
});

describe("Composer direction verbs", () => {
  const POV_OPTS = [{ id: "mei", name: "Mei", mono: "M", color: "#8E2B1C", portrait: null }];
  const VERBS = [
    { id: "escalate", group: "tone" as const, label: "Escalate", text: "Make it worse." },
  ];

  it("writes a verb into the MESSAGE box in narrator mode — the box that is the direction", () => {
    const onChange = vi.fn();
    render(
      <Composer
        value=""
        onChange={onChange}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov={null}
        verbs={VERBS}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Escalate" }));
    expect(onChange).toHaveBeenCalledWith("Make it worse.");
  });

  it("writes it into the DIRECTION box under POV, where the message box is the character", () => {
    const onGuidanceChange = vi.fn();
    const onChange = vi.fn();
    render(
      <Composer
        value=""
        onChange={onChange}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={onGuidanceChange}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov="mei"
        verbs={VERBS}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Escalate" }));
    expect(onGuidanceChange).toHaveBeenCalledWith("Make it worse.");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("adds a verb as a new line rather than running it into what is already there", () => {
    // Each line of the direction box is one thing the turn owes (Phase 8), so appending to
    // the sentence in progress would merge two directives into one.
    const onChange = vi.fn();
    render(
      <Composer
        value="Mei backs down"
        onChange={onChange}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov={null}
        verbs={VERBS}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Escalate" }));
    expect(onChange).toHaveBeenCalledWith("Mei backs down\nMake it worse.");
  });

  it("hides the bar entirely when no verb is worth offering", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov={null}
        verbs={[]}
      />,
    );
    expect(screen.queryByRole("toolbar", { name: "Direction" })).not.toBeInTheDocument();
  });

  it("shows the bar in both modes — the row is the direction, only the target changes", () => {
    const { rerender } = render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov={null}
        verbs={VERBS}
      />,
    );
    expect(screen.getByRole("toolbar", { name: "Direction" })).toBeInTheDocument();
    rerender(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        guidance=""
        onGuidanceChange={() => {}}
        onPovChange={() => {}}
        povOptions={POV_OPTS}
        pov="mei"
        verbs={VERBS}
      />,
    );
    expect(screen.getByRole("toolbar", { name: "Direction" })).toBeInTheDocument();
  });
});

