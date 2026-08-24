"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Monogram } from "@/components/ui/Monogram";
import { mediaUrl } from "@/lib/api";

/** One selectable Player-POV target: a present cast member the player can speak AS. */
export interface PovOption {
  id: string;
  name: string;
  mono: string;
  color: string;
  /** Portrait `/media/...` URL; the avatar falls back to the monogram when absent. */
  portrait?: string | null;
}

/** A small drama/identity glyph for the "Playwright" (no-POV) row (decorative). */
function MaskIcon({ size = 12 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 3.5-6 8-6s8 2 8 6" />
    </svg>
  );
}

/** Down/up caret on the trigger, signalling the control opens a menu. */
function Caret({ open }: { open: boolean }) {
  return (
    <svg
      width="9"
      height="9"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="flex-none"
      style={{ transform: open ? "rotate(180deg)" : undefined }}
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

/** A parchment circle carrying the drama mask, sized to sit beside the monograms. */
function PlaywrightAvatar({ size = 22 }: { size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-flex flex-none items-center justify-center rounded-full border border-cardbd text-mute2"
      style={{ width: size, height: size, background: "#EDE3CD" }}
    >
      <MaskIcon size={Math.round(size * 0.5)} />
    </span>
  );
}

/** A small check on the currently-selected row. */
function CheckIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="flex-none"
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

const AVATAR = 22;

/**
 * The **Player POV** control — the "Speaking as" dropdown that lives in the composer's
 * bottom-left controls row, immediately to the right of the Config button. A **custom**
 * dropdown (not a native `<select>`) so each option can show the character's **portrait
 * avatar + name**; "Playwright" (→ `null`) is the default — the player steering the scene
 * from outside it rather than speaking inside it. **Not** the Narrator: that word names the
 * AI voice that writes third-person prose in the scene, and nothing here is it.
 *
 * Accessible menu pattern: a disclosure `<button>` (`aria-haspopup="menu"` / `aria-expanded`)
 * opens a `role="menu"` popover of `role="menuitemradio"` rows. Keyboard: Enter/Space/↓ opens
 * and focuses the checked row; ↑/↓/Home/End roam; Enter/Space (or click) selects; Esc/Tab or
 * an outside click closes. Opens **upward** (the composer sits at the bottom). Hidden entirely
 * when there is no present cast member to speak as (only "Playwright" would remain).
 */
export function PovSelect({
  pov,
  onPovChange,
  options,
}: {
  pov: string | null;
  onPovChange: (id: string | null) => void;
  options: PovOption[];
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  // Focus the checked (or first) row when the menu opens; close on Esc / outside pointerdown.
  useEffect(() => {
    if (!open) return;
    const menu = menuRef.current;
    const checked = menu?.querySelector<HTMLButtonElement>('[role="menuitemradio"][aria-checked="true"]');
    const first = menu?.querySelector<HTMLButtonElement>('[role="menuitemradio"]');
    (checked ?? first)?.focus();
    const onDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  if (options.length === 0) return null;

  const selected = pov ? (options.find((o) => o.id === pov) ?? null) : null;

  function choose(id: string | null) {
    onPovChange(id);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onMenuKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') ?? [],
    );
    if (items.length === 0) return;
    const i = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      items[(i + 1) % items.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      items[(i - 1 + items.length) % items.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      items[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      items[items.length - 1]?.focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      buttonRef.current?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  }

  const rowClass =
    "flex w-full items-center gap-[8px] rounded-[3px] px-[8px] py-[6px] text-left text-ink hover:bg-hover focus:bg-hover focus:outline-none aria-checked:text-accent";

  return (
    // `min-w-0` (no `flex-none`) lets the control shrink on a narrow composer row rather than
    // overflowing — the trigger label truncates; the avatar + caret stay put.
    <div ref={rootRef} className="relative flex min-w-0">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label="Speaking as"
        // The one control whose name genuinely does not explain itself: "Speaking as" reads
        // as a label, not as a choice about who your words belong to.
        title="Choose whose voice your message is in — a character's, or your own as the Playwright"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setOpen(true);
          }
        }}
        // `min-w-[24px]`, not `min-w-0`: the label inside still truncates on a narrow
        // composer row, but the control cannot collapse below the WCAG 2.5.8 floor doing it.
        // It measured 18px wide at 320 — and the global coarse-pointer floor could not save
        // it, because that rule is zero-specificity by design and `min-w-0` outranks it.
        className="flex min-w-[24px] items-center gap-[5px] rounded-[8px] border border-field-bd px-[8px] py-[3px] text-mute hover:border-accent hover:text-accent aria-expanded:border-accent aria-expanded:text-accent"
      >
        {selected ? (
          <Monogram
            mono={selected.mono}
            color={selected.color}
            src={selected.portrait ? mediaUrl(selected.portrait) : undefined}
            size={18}
            fontSize={8}
            ring={1.5}
          />
        ) : (
          <PlaywrightAvatar size={18} />
        )}
        <span className="min-w-0 max-w-[96px] truncate font-mono text-[9px] tracking-[0.1em] text-current uppercase">
          {selected ? selected.name : "Playwright"}
        </span>
        <Caret open={open} />
      </button>

      {open ? (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Speaking as"
          onKeyDown={onMenuKeyDown}
          className="absolute bottom-[40px] left-0 z-40 flex max-h-[280px] min-w-[176px] max-w-[240px] flex-col gap-[2px] overflow-auto mytheca-menu p-[6px]"
        >
          <button
            type="button"
            role="menuitemradio"
            aria-checked={selected === null}
            tabIndex={-1}
            onClick={() => choose(null)}
            className={rowClass}
          >
            <PlaywrightAvatar size={AVATAR} />
            <span className="min-w-0 flex-1 truncate font-display text-[13px] font-semibold">
              Playwright
            </span>
            {selected === null ? <CheckIcon /> : null}
          </button>
          {options.map((o) => {
            const isSel = o.id === pov;
            return (
              <button
                key={o.id}
                type="button"
                role="menuitemradio"
                aria-checked={isSel}
                tabIndex={-1}
                onClick={() => choose(o.id)}
                className={rowClass}
              >
                <Monogram
                  mono={o.mono}
                  color={o.color}
                  src={o.portrait ? mediaUrl(o.portrait) : undefined}
                  size={AVATAR}
                  fontSize={9}
                  ring={1.5}
                />
                <span className="min-w-0 flex-1 truncate font-display text-[13px] font-semibold">
                  {o.name}
                </span>
                {isSel ? <CheckIcon /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
