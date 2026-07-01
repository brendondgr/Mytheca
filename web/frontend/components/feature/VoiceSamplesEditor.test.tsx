import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { VoiceSamplesEditor } from "./VoiceSamplesEditor";
import type { VoiceSample } from "@/lib/types";

/** A tiny controlled harness so add/remove/patch reflect back into the rows. */
function Harness({
  initial = [],
  onChange,
}: {
  initial?: VoiceSample[];
  onChange?: (next: VoiceSample[]) => void;
}) {
  const [samples, setSamples] = useState<VoiceSample[]>(initial);
  return (
    <VoiceSamplesEditor
      samples={samples}
      onChange={(next) => {
        setSamples(next);
        onChange?.(next);
      }}
    />
  );
}

describe("VoiceSamplesEditor", () => {
  it("shows an empty-state hint when there are no samples", () => {
    render(<Harness />);
    expect(screen.getByText(/no samples yet/i)).toBeInTheDocument();
  });

  it("adds a blank row", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: /add sample/i }));
    expect(screen.getByLabelText(/sample 1 situation/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/sample 1 response/i)).toBeInTheDocument();
  });

  it("edits a row's situation and response", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness initial={[{ situation: "", sample: "" }]} onChange={onChange} />);
    await user.type(screen.getByLabelText(/sample 1 situation/i), "cornered");
    await user.type(screen.getByLabelText(/sample 1 response/i), "Back off.");
    // Last change carries the fully-typed values.
    expect(onChange).toHaveBeenLastCalledWith([{ situation: "cornered", sample: "Back off." }]);
  });

  it("removes a row", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[
          { situation: "a", sample: "one" },
          { situation: "b", sample: "two" },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: /remove sample 1/i }));
    // The second row shifts up to become sample 1.
    expect(screen.getByLabelText(/sample 1 situation/i)).toHaveValue("b");
    expect(screen.queryByLabelText(/sample 2 situation/i)).not.toBeInTheDocument();
  });
});
