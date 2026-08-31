"use client";

import { useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { Monogram } from "@/components/ui/Monogram";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { useExitTransition } from "@/hooks/use-exit-transition";
import { Icon } from "@/components/ui/Icon";

export interface MultiSelectOption {
  id: string;
  label: string;
  /** Character monogram initials — renders a `Monogram` affordance on the row. */
  mono?: string;
  /** Character accent color (pairs with `mono`/`portrait`). */
  color?: string;
  /** Optional character portrait URL (falls back to the monogram). */
  portrait?: string | null;
  /** Setting affordance — renders the `◆` seal instead of a monogram. */
  seal?: boolean;
  /** Secondary descriptor shown in the dropdown list only (e.g. role/archetype). Not shown in selected chips. */
  sublabel?: string;
}

/**
 * Accessible single/multi-select dropdown. A button trigger opens a `listbox`
 * popover; `multiple` switches between checkbox-style multi-select (Cast) and
 * single-choice replacement (Setting). Behaviour mirrors `StorylineMenu` /
 * `CreateMenu`: outside-click + `Esc` close, plus roving focus over the options
 * (`ArrowUp`/`ArrowDown`/`Home`/`End`, `Enter`/`Space` to toggle).
 */
export function MultiSelect({
  options,
  selected,
  onChange,
  multiple = false,
  label,
  placeholder = "Choose…",
  emptyText = "Nothing to choose yet",
  className,
  disabled,
}: {
  options: MultiSelectOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  multiple?: boolean;
  label?: string;
  placeholder?: string;
  emptyText?: string;
  className?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLLIElement | null)[]>([]);
  const listId = useId();

  // The list outlives `open` by one beat so its dismissal animates out of the
  // trigger rather than blinking away.
  const { mounted: listMounted, closing: listClosing } = useExitTransition(open);

  const isEmpty = options.length === 0;
  const selectedSet = new Set(selected);
  const selectedOptions = options.filter((o) => selectedSet.has(o.id));

  // Outside-click + Esc close (mirrors StorylineMenu/CreateMenu).
  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // On open, move focus to the active option. The active index is chosen in the
  // open handler; the option refs are already attached when this effect runs.
  useEffect(() => {
    if (!open) return;
    optionRefs.current[active]?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function openMenu() {
    const firstSelected = options.findIndex((o) => selectedSet.has(o.id));
    setActive(firstSelected >= 0 ? firstSelected : 0);
    setOpen(true);
  }

  function focusOption(index: number) {
    const clamped = Math.max(0, Math.min(index, options.length - 1));
    setActive(clamped);
    optionRefs.current[clamped]?.focus();
  }

  function toggle(id: string) {
    if (multiple) {
      onChange(selectedSet.has(id) ? selected.filter((x) => x !== id) : [...selected, id]);
    } else {
      // Single-select: replace (or clear when re-picking the same one).
      onChange(selectedSet.has(id) ? [] : [id]);
      setOpen(false);
      triggerRef.current?.focus();
    }
  }

  function onListKeyDown(event: React.KeyboardEvent<HTMLUListElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusOption(active + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusOption(active - 1);
        break;
      case "Home":
        event.preventDefault();
        focusOption(0);
        break;
      case "End":
        event.preventDefault();
        focusOption(options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (options[active]) toggle(options[active].id);
        break;
      default:
        break;
    }
  }

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      {label ? <FieldLabel>{label}</FieldLabel> : null}
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled || isEmpty}
        onClick={() => (open ? setOpen(false) : openMenu())}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        className={cn(
          "flex w-full cursor-pointer items-center justify-between gap-2 rounded-xs border border-field-bd bg-field px-md py-sm text-left text-body",
          "touch-target press transition-[border-color] duration-fast ease-soft",
          "enabled:hover:border-accent focus-visible:border-accent",
          (disabled || isEmpty) && "cursor-not-allowed opacity-60",
        )}
      >
        <span className="flex min-w-0 flex-1 flex-wrap items-center gap-xs">
          {isEmpty ? (
            <span className="text-mute">{emptyText}</span>
          ) : selectedOptions.length === 0 ? (
            <span className="text-mute">{placeholder}</span>
          ) : multiple ? (
            selectedOptions.map((o) => (
              <span
                key={o.id}
                className="inline-flex items-center gap-2xs rounded-full border border-cardbd bg-card px-sm py-3xs text-eyebrow text-ink"
              >
                <Monogram
                  mono={o.mono ?? ""}
                  color={o.color ?? "var(--accent)"}
                  src={o.portrait ?? undefined}
                  size={16}
                  ring={1.5}
                  fontSize={7}
                />
                {o.label}
              </span>
            ))
          ) : (
            <span className="inline-flex items-center gap-xs text-ink">
              <span aria-hidden className="text-gold-ink">
                ◆
              </span>
              {selectedOptions[0].label}
            </span>
          )}
        </span>
        <Icon
          name="down"
          size={15}
          strokeWidth={2.2}
          className={cn("-mr-3xs text-mute transition-transform", open && "rotate-180")}
        />
      </button>
      {listMounted && !isEmpty ? (
        <ul
          id={listId}
          role="listbox"
          aria-label={label}
          aria-multiselectable={multiple || undefined}
          onKeyDown={onListKeyDown}
          data-closing={listClosing || undefined}
          className={cn(
            "absolute z-40 mt-2xs max-h-[240px] w-full overflow-auto mytheca-menu p-2xs",
            listClosing && "pointer-events-none",
          )}
        >
          {options.map((o, i) => {
            const isSelected = selectedSet.has(o.id);
            return (
              <li
                key={o.id}
                ref={(el) => {
                  optionRefs.current[i] = el;
                }}
                role="option"
                aria-selected={isSelected}
                tabIndex={i === active ? 0 : -1}
                onClick={() => toggle(o.id)}
                onFocus={() => setActive(i)}
                className={cn(
                  "flex cursor-pointer items-center gap-sm rounded-xs px-sm py-xs text-body-sm outline-none hover:bg-hover focus-visible:bg-hover focus-visible:ring-1 focus-visible:ring-accent",
                  isSelected && "bg-card2",
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "w-3 flex-none text-center text-eyebrow",
                    isSelected ? "text-accent-ink" : "text-transparent",
                  )}
                >
                  ✓
                </span>
                {o.seal ? (
                  <span aria-hidden className="w-4 flex-none text-center text-label text-gold-ink">
                    ◆
                  </span>
                ) : (
                  <Monogram
                    mono={o.mono ?? ""}
                    color={o.color ?? "var(--accent)"}
                    src={o.portrait ?? undefined}
                    size={20}
                    ring={1.5}
                    fontSize={9}
                  />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-ink">{o.label}</span>
                  {o.sublabel ? (
                    <span className="block font-mono text-eyebrow tracking-[0.06em] uppercase text-mute">
                      {o.sublabel}
                    </span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
