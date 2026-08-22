"use client";

import { Modal } from "@/components/ui/Modal";
import { Eyebrow } from "@/components/ui/Eyebrow";

interface Binding {
  keys: string[];
  what: string;
}

/**
 * Grouped so the sheet reads as "here is what you can do", not "here is a key table".
 *
 * The **Already there** group is the point of the whole sheet: Enter sends, Shift+Enter makes
 * a newline, `@` names a character or a file. All three have worked since long before this
 * existed and none of them was written down anywhere a player would look.
 */
const GROUPS: { title: string; bindings: Binding[] }[] = [
  {
    title: "Getting around",
    bindings: [
      { keys: ["/"], what: "Jump to the message box" },
      { keys: ["Esc"], what: "Close whatever is open" },
      { keys: ["?"], what: "Open and close this sheet" },
    ],
  },
  {
    title: "Writing",
    bindings: [
      { keys: ["↑"], what: "Bring back your last message (from an empty box)" },
      { keys: ["Enter"], what: "Send" },
      { keys: ["Shift", "Enter"], what: "New line instead of sending" },
      { keys: ["@"], what: "Name a character, or attach one of your files" },
    ],
  },
];

/**
 * What the keyboard does, behind `?`.
 *
 * A shortcut sheet is also the cheapest place to *document the behaviours that already
 * exist and are invisible* — the composer has always sent on Enter and tagged on `@`, and a
 * player had no way to find that out short of trying it.
 */
export function ShortcutSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} ariaLabel="Keyboard shortcuts" className="max-w-[420px]">
      <div className="p-[18px_20px]">
        <h2 className="mb-[14px] font-display text-[18px] leading-none font-bold text-ink">
          Keyboard shortcuts
        </h2>
        <div className="flex flex-col gap-[16px]">
          {GROUPS.map((group) => (
            <section key={group.title}>
              <Eyebrow tracking="0.14em" className="mb-[8px] block">
                {group.title}
              </Eyebrow>
              <dl className="flex flex-col gap-[7px]">
                {group.bindings.map((b) => (
                  <div key={b.what} className="flex items-baseline justify-between gap-[12px]">
                    <dd className="order-2 flex-1 font-body text-[12.5px] leading-[1.4] text-ink-soft">
                      {b.what}
                    </dd>
                    <dt className="order-1 flex flex-none items-center gap-[3px]">
                      {b.keys.map((k) => (
                        <kbd
                          key={k}
                          className="rounded-[4px] border border-field-bd bg-field px-[6px] py-[2px] font-mono text-[10px] text-mute"
                        >
                          {k}
                        </kbd>
                      ))}
                    </dt>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <p className="mt-[16px] font-body text-[11.5px] leading-[1.45] text-mute2">
          Every one of these has a pointer equivalent — nothing here is the only way to do
          something.
        </p>
      </div>
    </Modal>
  );
}
