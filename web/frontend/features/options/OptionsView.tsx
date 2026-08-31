"use client";

import { HeaderBar } from "@/components/layout/HeaderBar";
import { useRef, useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { useOptionsSettings } from "@/features/options/useOptionsSettings";
import { LanguageModelsTab } from "@/features/options/tabs/LanguageModelsTab";
import { ImageModelsTab } from "@/features/options/tabs/ImageModelsTab";
import { PromptsTab } from "@/features/options/tabs/PromptsTab";
import { StyleTab } from "@/features/options/tabs/StyleTab";
import { AppearanceTab } from "@/features/options/tabs/AppearanceTab";
import { LibraryDefaultsTab } from "@/features/options/tabs/LibraryDefaultsTab";
import { AboutTab } from "@/features/options/tabs/AboutTab";

type TabKey = "models" | "images" | "prompts" | "style" | "appearance" | "library" | "about";

const TABS: { key: TabKey; label: string; sub: string }[] = [
  { key: "models", label: "Language Models", sub: "endpoints & params" },
  { key: "images", label: "Image Generation", sub: "ComfyUI" },
  { key: "prompts", label: "Prompts", sub: "writing agents" },
  { key: "style", label: "Narrative style", sub: "saved presets" },
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
    <>
    {/* No <AppShell> here. The root layout already wraps every route in one;
        rendering a second nested it — two `.mytheca-themed` grounds, two
        MotionProviders, two ToastProviders, and (once the frame gained one) TWO
        skip links, so the first Tab and the second Tab both said "Skip to
        content". A fragment is all this needs: the shell supplies the ground
        and the flex column. */}
      <HeaderBar elevated>
        <div className="flex items-center gap-md">
          <span aria-hidden className="text-body text-accent-ink">
            ❖
          </span>
          <span className="font-display text-step-2 font-bold tracking-[0.2em] text-ink">
            MYTHECA
          </span>
          <span className="hidden h-5 w-px bg-hair-strong md:block" aria-hidden />
          <span className="hidden font-mono text-eyebrow tracking-[0.18em] text-mute uppercase md:block">
            Options
          </span>
        </div>
        <Link
          href="/"
          className="rounded-xs border border-field-bd bg-field px-md py-xs font-mono text-eyebrow tracking-[0.1em] text-ink uppercase hover:border-accent hover:bg-hover hover:text-accent-ink"
        >
          ← Library
        </Link>
      </HeaderBar>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1120px] flex-1 px-lg py-xl sm:px-xl lg:w-[66%]">
        <h1 className="mb-2xs font-display text-step-2 font-semibold text-ink">Options</h1>
        <p className="mb-lg font-body text-body-sm text-ink-soft">
          Everything customizable lives here — language models, appearance, and library defaults.
        </p>

        {opts.error ? (
          <div
            role="alert"
            className="mb-lg flex items-center justify-between gap-md rounded-sm border border-cardbd bg-card px-lg py-sm"
          >
            <span className="font-body text-body-sm text-ink">{opts.error}</span>
            <button
              type="button"
              onClick={opts.retry}
              className="cursor-pointer font-mono text-eyebrow tracking-[0.08em] text-accent-ink uppercase hover:underline"
            >
              Retry
            </button>
          </div>
        ) : null}

        <div className="flex flex-col gap-lg lg:flex-row lg:gap-xl">
          {/* Vertical tab list (left). Collapses to a horizontal scroller < lg. */}
          <div
            role="tablist"
            aria-label="Options sections"
            aria-orientation="vertical"
            // The edge fade applies only below `lg`, where this is a horizontal
            // strip that can clip; from `lg` it is a vertical rail with
            // `overflow-visible` and nothing to fade.
            className="scroll-fade flex flex-none gap-xs overflow-x-auto rounded-sm lg:w-[210px] lg:flex-col lg:self-start lg:overflow-visible lg:border lg:border-cardbd lg:bg-surface lg:p-sm lg:[&::before]:hidden lg:[&::after]:hidden"
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
                    "flex flex-none cursor-pointer flex-col gap-3xs rounded-xs border px-md py-sm text-left whitespace-nowrap lg:whitespace-normal",
                    selected
                      ? "border-accent bg-card2 text-ink"
                      : "border-cardbd bg-card text-ink-soft hover:border-hair-strong hover:bg-hover hover:text-ink",
                  )}
                >
                  <span className="font-display text-body-sm font-semibold">{tab.label}</span>
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
                className="rounded-sm border border-cardbd bg-card p-lg sm:p-xl"
              >
                {tab.key === "models" ? (
                  <LanguageModelsTab key={opts.settings ? "ready" : "loading"} opts={opts} />
                ) : null}
                {tab.key === "images" ? (
                  <ImageModelsTab key={opts.settings ? "ready" : "loading"} opts={opts} />
                ) : null}
                {tab.key === "prompts" ? (
                  <PromptsTab key={opts.settings ? "ready" : "loading"} opts={opts} />
                ) : null}
                {tab.key === "style" ? <StyleTab key={active} /> : null}
                {tab.key === "appearance" ? <AppearanceTab /> : null}
                {tab.key === "library" ? <LibraryDefaultsTab opts={opts} /> : null}
                {tab.key === "about" ? <AboutTab opts={opts} /> : null}
              </div>
            ))}
          </div>
        </div>
      </main>
    </>
  );
}
