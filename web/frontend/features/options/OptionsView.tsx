"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { cn } from "@/lib/cn";
import { useOptionsSettings } from "@/features/options/useOptionsSettings";
import { LanguageModelsTab } from "@/features/options/tabs/LanguageModelsTab";
import { ImageModelsTab } from "@/features/options/tabs/ImageModelsTab";
import { AppearanceTab } from "@/features/options/tabs/AppearanceTab";
import { LibraryDefaultsTab } from "@/features/options/tabs/LibraryDefaultsTab";
import { AboutTab } from "@/features/options/tabs/AboutTab";

type TabKey = "models" | "images" | "appearance" | "library" | "about";

const TABS: { key: TabKey; label: string; sub: string }[] = [
  { key: "models", label: "Language Models", sub: "endpoints & params" },
  { key: "images", label: "Image Generation", sub: "ComfyUI" },
  { key: "appearance", label: "Appearance", sub: "theme" },
  { key: "library", label: "Library defaults", sub: "startup" },
  { key: "about", label: "About", sub: "diagnostics" },
];

/**
 * The full-screen Options surface. Manuscript chrome, but a distinct structure:
 * a centered panel (66% width on desktop) with a **vertical tab list on the left**
 * and the active tab's content on the right.
 */
export function OptionsView() {
  const [active, setActive] = useState<TabKey>("models");
  const opts = useOptionsSettings();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    let next = index;
    if (event.key === "ArrowDown") next = (index + 1) % TABS.length;
    else if (event.key === "ArrowUp") next = (index - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    else return;
    event.preventDefault();
    setActive(TABS[next].key);
    refs.current[next]?.focus();
  }

  return (
    <AppShell>
      <header className="velora-header flex h-[52px] flex-none items-center justify-between gap-3 border-b border-hair-strong px-[16px] sm:px-[26px]">
        <div className="flex items-center gap-[13px]">
          <span aria-hidden className="text-[16px] text-accent">
            ❖
          </span>
          <span className="font-display text-[20px] font-bold tracking-[0.2em] text-ink">
            VELORA
          </span>
          <span className="hidden h-5 w-px bg-hair-strong md:block" aria-hidden />
          <span className="hidden font-mono text-[10.5px] tracking-[0.18em] text-mute uppercase md:block">
            Options
          </span>
        </div>
        <Link
          href="/"
          className="rounded-[2px] border border-field-bd bg-field px-[13px] py-[7px] font-mono text-[10.5px] tracking-[0.1em] text-ink uppercase hover:border-accent"
        >
          ← Library
        </Link>
      </header>

      <main className="mx-auto w-full max-w-[1120px] flex-1 px-[16px] py-[24px] sm:px-[24px] lg:w-[66%]">
        <h1 className="mb-[4px] font-display text-[26px] font-semibold text-ink">Options</h1>
        <p className="mb-[20px] font-body text-[14px] text-ink-soft">
          Everything customizable lives here — language models, appearance, and library defaults.
        </p>

        {opts.error ? (
          <div
            role="alert"
            className="mb-[16px] flex items-center justify-between gap-[12px] rounded-[6px] border border-cardbd bg-card px-[14px] py-[10px]"
          >
            <span className="font-body text-[14px] text-ink">{opts.error}</span>
            <button
              type="button"
              onClick={opts.retry}
              className="cursor-pointer font-mono text-[11px] tracking-[0.08em] text-accent uppercase hover:underline"
            >
              Retry
            </button>
          </div>
        ) : null}

        <div className="flex flex-col gap-[16px] lg:flex-row lg:gap-[24px]">
          {/* Vertical tab list (left). Collapses to a horizontal scroller < lg. */}
          <div
            role="tablist"
            aria-label="Options sections"
            aria-orientation="vertical"
            className="flex flex-none gap-[6px] overflow-x-auto lg:w-[210px] lg:flex-col lg:overflow-visible"
          >
            {TABS.map((tab, index) => {
              const selected = tab.key === active;
              return (
                <button
                  key={tab.key}
                  ref={(el) => {
                    refs.current[index] = el;
                  }}
                  role="tab"
                  id={`opt-tab-${tab.key}`}
                  aria-selected={selected}
                  aria-controls={`opt-panel-${tab.key}`}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => setActive(tab.key)}
                  onKeyDown={(event) => onKeyDown(event, index)}
                  className={cn(
                    "flex flex-none cursor-pointer flex-col gap-[2px] rounded-[3px] border px-[13px] py-[10px] text-left whitespace-nowrap lg:whitespace-normal",
                    selected
                      ? "border-accent bg-card2 text-ink"
                      : "border-cardbd bg-card text-ink-soft hover:bg-card2",
                  )}
                >
                  <span className="font-display text-[14.5px] font-semibold">{tab.label}</span>
                  <span className="font-mono text-tag tracking-[0.06em] text-mute uppercase">
                    {tab.sub}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Active panel (right). */}
          <div className="min-w-0 flex-1">
            {TABS.map((tab) => (
              <div
                key={tab.key}
                role="tabpanel"
                id={`opt-panel-${tab.key}`}
                aria-labelledby={`opt-tab-${tab.key}`}
                hidden={tab.key !== active}
                className="rounded-[5px] border border-cardbd bg-card p-[18px] sm:p-[22px]"
              >
                {tab.key === "models" ? (
                  <LanguageModelsTab key={opts.settings ? "ready" : "loading"} opts={opts} />
                ) : null}
                {tab.key === "images" ? (
                  <ImageModelsTab key={opts.settings ? "ready" : "loading"} opts={opts} />
                ) : null}
                {tab.key === "appearance" ? <AppearanceTab /> : null}
                {tab.key === "library" ? <LibraryDefaultsTab opts={opts} /> : null}
                {tab.key === "about" ? <AboutTab opts={opts} /> : null}
              </div>
            ))}
          </div>
        </div>
      </main>
    </AppShell>
  );
}
