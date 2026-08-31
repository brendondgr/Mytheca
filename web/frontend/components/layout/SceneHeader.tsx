"use client";

import { HeaderBar, HeaderLead, HeaderTrail } from "@/components/layout/HeaderBar";
import type { LlmHealth } from "@/lib/types";
import type { ReactNode } from "react";
import Link from "next/link";
import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";
import { useMediaQuery } from "@/hooks/use-media-query";
import {
  SceneMenu,
  type ExportFormat,
  type SceneMenuItem,
} from "@/components/feature/SceneMenu";

/** Which face of the story player is showing: the running chat, or the graph. */
export type SceneViewMode = "chat" | "graph";

const VIEW_MODES: { key: SceneViewMode; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "graph", label: "Graph" },
];

/** A compact segmented Chat ⇄ Graph switch (mirrors the ThemeSwitcher idiom). */
function ViewModeSwitch({
  viewMode,
  onChange,
}: {
  viewMode: SceneViewMode;
  onChange: (mode: SceneViewMode) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Scene view"
      className="flex items-center rounded-full border border-field-bd bg-field p-[2px]"
    >
      {VIEW_MODES.map((mode) => {
        const active = viewMode === mode.key;
        return (
          <button
            key={mode.key}
            type="button"
            onClick={() => onChange(mode.key)}
            aria-pressed={active}
            title={mode.key === "graph" ? "See the scene's story graph" : "Back to the running scene"}
            className={`rounded-full px-[8px] py-[4px] font-mono text-[9px] tracking-[0.08em] uppercase transition-colors sm:px-[10px] sm:tracking-[0.12em] ${
              active
                ? "bg-card2 font-semibold text-accent"
                : "text-mute hover:bg-hover hover:text-ink"
            }`}
          >
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}

/** Story-player header: back to the Library, scene title/setting, view switch, export, theme, status.
 * Scene Config now lives in the composer's bottom controls row (not the header). */
export function SceneHeader({
  title,
  settingName,
  genre,
  tone,
  backHref = "/",
  viewMode,
  onViewModeChange,
  onExport,
  canExport = false,
  onToggleInspector,
  inspectorOpen = false,
  onOpenWriting,
  onOpenStyle,
  onToggleMemory,
  memoryOpen = false,
  health = null,
  tray,
  trayPanel,
  onOpenShortcuts,
  extraControls = [],
  extraSlot,
}: {
  title: string;
  settingName: string;
  genre?: string;
  tone?: string;
  backHref?: string;
  /** Current view (chat/graph). Omit `onViewModeChange` to hide the switch. */
  viewMode?: SceneViewMode;
  /** Switch between the chat and the graph view (omit to hide the control). */
  onViewModeChange?: (mode: SceneViewMode) => void;
  /** Download the full conversation record (omit to hide the Export control). */
  onExport?: (format: ExportFormat) => void;
  /** Whether there is a saved session to export yet (disables the control until then). */
  canExport?: boolean;
  /** Toggle the Turn Inspector drawer (omit to hide the control). */
  onToggleInspector?: () => void;
  inspectorOpen?: boolean;
  /** Open the writing-prompt modal (omit to hide the item). */
  onOpenWriting?: () => void;
  onOpenStyle?: () => void;
  /** Opens the player-facing "what the scene knows" rail. */
  onToggleMemory?: () => void;
  memoryOpen?: boolean;
  /** Whether the configured model endpoint is usable. `null` before the first check. */
  health?: LlmHealth | null;
  /**
   * The play-through tray, rendered left of Export. Passed as a node rather than as props
   * because the header is presentational and the tray needs the play hook's session state;
   * threading six callbacks through here would make this component know about sessions.
   */
  tray?: ReactNode;
  /**
   * The tray's rows *without* its popover, for the narrow form — where the tray is a
   * drill-down inside the scene menu rather than a second popover beside it. Two nodes
   * rather than one because the header must not know about sessions either way.
   */
  trayPanel?: ReactNode;
  /** Open the keyboard-shortcut sheet. Without this it is reachable only by pressing `?`,
   *  which is to say: not at all on a phone. */
  onOpenShortcuts?: () => void;
  /** Anything another plan adds to the header. One array entry, at every width. */
  extraControls?: SceneMenuItem[];
  /** Rendered at the foot of the scene menu. */
  extraSlot?: ReactNode;
}) {
  // The Tailwind `sm` breakpoint. `false` during SSR and wherever `matchMedia` is absent, so
  // the server-rendered form is the NARROW one — safe in both directions, because the
  // overflow menu is fully functional at every width while an inline cluster that never
  // collapses is the bug being fixed.
  const wide = useMediaQuery("(min-width: 640px)");
  const meta = [`◆ ${settingName}`, genre, tone].filter(Boolean).join(" · ");
  // Built here rather than by the caller so the header owns which of its controls fold in.
  const alwaysInMenu: SceneMenuItem[] = [
    ...(onOpenWriting
      ? [
          {
            key: "writing",
            label: "Writing…",
            hint: "the instructions the narrator and cast are given",
            icon: "✎",
            onSelect: onOpenWriting,
          },
        ]
      : []),
    ...(onOpenStyle
      ? [
          {
            key: "style",
            label: "Style…",
            hint: "how this scene is written, where it differs from the world",
            icon: "❧",
            onSelect: onOpenStyle,
          },
        ]
      : []),
    ...(onToggleInspector
      ? [
          {
            key: "inspector",
            label: "Turn Inspector",
            hint: "what the scene read, who it chose, and why",
            icon: "⚙",
            pressed: inspectorOpen,
            onSelect: onToggleInspector,
          },
        ]
      : []),
    ...(onExport
      ? [
          {
            key: "export-md",
            label: "Export as Markdown",
            // The hint doubles as the reason it is unavailable: a disabled control with no
            // explanation reads as a bug.
            hint: canExport
              ? "readable transcript + diagnostics"
              : "nothing to export until the scene has a turn",
            icon: "⭳",
            disabled: !canExport,
            onSelect: () => onExport("md"),
          },
          {
            key: "export-json",
            label: "Export as JSON",
            hint: canExport
              ? "structured record for debugging"
              : "nothing to export until the scene has a turn",
            icon: "⭳",
            disabled: !canExport,
            onSelect: () => onExport("json"),
          },
        ]
      : []),
    ...(onOpenShortcuts
      ? [
          {
            key: "shortcuts",
            label: "Keyboard shortcuts",
            hint: "the keys this scene answers to",
            icon: "⌨",
            onSelect: onOpenShortcuts,
          },
        ]
      : []),
  ];

  /**
   * What folds in below `sm`: the play-through tray, the memory toggle and the theme
   * switcher, ahead of the items that are in the menu at every width.
   *
   * The tray arrives as a **drill-down panel**, not as a nested popover — see
   * `SceneMenuItem.panel`. Theme arrives as a `render` row, because a three-way switch
   * flattened into three menu items would read as three unrelated commands.
   */
  const foldedIn: SceneMenuItem[] = wide
    ? []
    : [
        ...(trayPanel
          ? [{ key: "playthroughs", label: "Play-throughs", hint: "switch stories, or start another", icon: "❑", panel: trayPanel }]
          : []),
        ...(onToggleMemory
          ? [
              {
                key: "memory",
                label: "What the scene knows",
                hint: "how far back the cast remembers, and what it is reading",
                icon: "◍",
                pressed: memoryOpen,
                onSelect: onToggleMemory,
              },
            ]
          : []),
      ];

  const sceneMenuItems: SceneMenuItem[] = [
    ...foldedIn,
    ...alwaysInMenu,
    ...extraControls,
    ...(wide ? [] : [{ key: "theme", label: "Theme", render: <ThemeSwitcher /> }]),
  ];

  return (
    <HeaderBar>
      <HeaderLead>
        <Link
          href={backHref}
          aria-label="Back to Library"
          className="flex flex-none items-center gap-2xs rounded-xs border border-field-bd px-sm py-xs font-mono text-eyebrow tracking-[0.1em] text-accent uppercase hover:bg-accent hover:text-on-accent sm:px-md"
        >
          ‹<span className="hidden sm:inline">&nbsp;Library</span>
        </Link>
        <span className="h-[22px] w-px flex-none bg-hair-strong" aria-hidden />
        <div className="min-w-0">
          <div className="truncate font-display text-step-0 leading-none font-bold text-ink">
            {title}
          </div>
          <div className="mt-1 truncate font-mono text-tag tracking-[0.14em] text-mute uppercase">
            {meta} · live scene
          </div>
        </div>
      </HeaderLead>
      {/* Deliberately `flex-none`. Letting this cluster shrink was tried and is
        * worse: its children have intrinsic widths, so a squeezed container
        * pushes them 50–150px past the edge instead of 7px. The real fix was never a
        * layout tweak but a design change — collapsing controls below `sm` — and that is
        * what this component now does, via `useMediaQuery` + the scene menu's item list.
        *
        * Rendered ONCE in one of two forms, never twice with one copy `aria-hidden`: a
        * duplicated cluster produces duplicate accessible names and a tab order that
        * visits invisible buttons. */}
      <HeaderTrail className="gap-sm sm:gap-md">
        {/* Inline at every width: the scene's primary mode toggle, and whether the model
            behind it is actually there. Both are compact, and both answer a question the
            player should not have to open a menu to ask. */}
        {onViewModeChange ? (
          <ViewModeSwitch viewMode={viewMode ?? "chat"} onChange={onViewModeChange} />
        ) : null}
        {wide ? tray : null}
        {wide ? <ThemeSwitcher /> : null}
        {/* The real model-health indicator, in the slot where a hardcoded green dot and
            "Narrator active" used to sit — a literal `<span>` reflecting no state at all. A
            status light that is always on teaches players to ignore every status light. */}
        <ModelStatus health={health} wide={wide} />
        {/* Two rails, and they are for two different questions: this one is the player's
            ("what does the scene know"), the Inspector is the developer's ("what did the loop
            do"). Mutually exclusive, because two 340px columns cannot both dock. */}
        {wide && onToggleMemory ? (
          <button
            type="button"
            onClick={onToggleMemory}
            aria-pressed={memoryOpen}
            aria-label="What the scene knows"
            title="How far back the cast remembers, and what it is reading"
            className="flex flex-none items-center gap-xs rounded-xs border border-field-bd px-sm py-xs font-mono text-eyebrow tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-pressed:border-accent aria-pressed:text-accent"
          >
            <span aria-hidden>◍</span>
            <span className="hidden sm:inline">Memory</span>
          </button>
        ) : null}
        {/* One popover holding everything that does not fit. Below `sm` that is most of the
            header; the cluster is `flex-none`, so every control left inline costs width a
            320px screen does not have. */}
        {sceneMenuItems.length > 0 || extraSlot ? (
          <SceneMenu items={sceneMenuItems} extraSlot={extraSlot} />
        ) : null}
      </HeaderTrail>
    </HeaderBar>
  );
}

/** How each health state reads to a player, in words — never by colour alone. */
const HEALTH_COPY: Record<
  LlmHealth["state"],
  { label: string; dot: string; text: string; glyph: string }
> = {
  // `glyph` is the narrow form's second channel. A bare coloured dot at 320px would be
  // colour alone, which is exactly what the labelled form exists to avoid — so the shape
  // changes with the state too.
  reachable: { label: "Model ready", dot: "bg-success", text: "text-mute", glyph: "●" },
  model_missing: { label: "Model not found", dot: "bg-gold", text: "text-gold", glyph: "!" },
  unreachable: { label: "Model unreachable", dot: "bg-danger", text: "text-danger", glyph: "✕" },
  unconfigured: { label: "No model set", dot: "bg-mute2", text: "text-mute2", glyph: "○" },
};

/**
 * Whether the model behind the scene is actually there.
 *
 * The dot is never the only channel: the label changes with the state, the `aria-label`
 * carries the endpoint's own explanation, and `role="status"` announces a change rather than
 * leaving it to be noticed. Renders nothing until the first check has answered — a light that
 * guesses is worse than one that waits.
 */
function ModelStatus({ health, wide }: { health: LlmHealth | null; wide: boolean }) {
  if (!health) return null;
  const copy = HEALTH_COPY[health.state];
  return (
    <span
      role="status"
      aria-label={`${copy.label}. ${health.detail}`}
      title={
        health.backend ? `${health.detail} (${health.backend})` : health.detail
      }
      className="flex flex-none items-center gap-[6px] font-mono text-[9px] tracking-[0.12em] uppercase"
    >
      {wide ? (
        <>
          <span aria-hidden className={`h-[6px] w-[6px] flex-none rounded-full ${copy.dot}`} />
          <span className={copy.text}>{copy.label}</span>
        </>
      ) : (
        // The name still says it in words; only the drawing shrinks. It used to be
        // `hidden sm:flex` — invisible at exactly the width where a broken endpoint is
        // hardest to diagnose.
        <span aria-hidden className={`text-[11px] leading-none ${copy.text}`}>{copy.glyph}</span>
      )}
    </span>
  );
}
