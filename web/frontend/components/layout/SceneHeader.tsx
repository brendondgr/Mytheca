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
import { Icon } from "@/components/ui/Icon";

/** Which face of the story player is showing: the running chat, or the graph. */
export type SceneViewMode = "chat" | "graph";

const VIEW_MODES: { key: SceneViewMode; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "graph", label: "Graph" },
];

/** A compact segmented Chat ⇄ Graph switch (mirrors the ThemeSwitcher idiom).
 *
 * Rendered inline at `sm`+ and inside the scene menu below it — as a `render` row, not as
 * two menu items. Flattened into "Chat" and "Graph" commands it would read as two
 * unrelated actions rather than as one control with two positions, and the current
 * position would have nowhere to show.
 */
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
      className="flex items-center rounded-full border border-field-bd bg-field p-3xs"
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
            className={`rounded-full px-sm py-2xs font-mono text-eyebrow tracking-[0.08em] uppercase transition-colors sm:px-sm sm:tracking-[0.12em] ${
              active
                ? "bg-card2 font-semibold text-accent-ink"
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
  railTriggers = [],
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
  /**
   * The rails the player reaches below `lg` — the cast, the scene state, what the scene
   * knows. They used to be a third bar of their own (`SceneRailBar`) between the transcript
   * and the composer, which is one horizontal band of chrome on the smallest screen in the
   * app; they are menu rows now. Empty at `lg`+, where every rail is docked and visible.
   */
  railTriggers?: SceneMenuItem[];
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
            icon: <Icon name="pencil" size={14} />,
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
            icon: <Icon name="book" size={14} />,
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
            icon: <Icon name="gear" size={14} />,
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
            icon: <Icon name="down" size={14} />,
            disabled: !canExport,
            onSelect: () => onExport("md"),
          },
          {
            key: "export-json",
            label: "Export as JSON",
            hint: canExport
              ? "structured record for debugging"
              : "nothing to export until the scene has a turn",
            icon: <Icon name="down" size={14} />,
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
            icon: <Icon name="chat" size={14} />,
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
        // The rails come FIRST. Below `sm` they are the only way to the cast, the scene
        // state and the direction checklist, so they outrank the housekeeping below them.
        ...railTriggers,
        ...(trayPanel
          ? [{
              key: "playthroughs",
              label: "Play-throughs",
              hint: "switch stories, or start another",
              icon: <Icon name="book" size={14} />,
              panel: trayPanel,
            }]
          : []),
        ...(onToggleMemory
          ? [
              {
                key: "memory",
                label: "What the scene knows",
                hint: "how far back the cast remembers, and what it is reading",
                icon: <Icon name="knows" size={14} />,
                pressed: memoryOpen,
                // The rail takes the full width below `sm`, so leaving the menu open
                // would park it on top of the thing it just revealed.
                closesMenu: true,
                onSelect: onToggleMemory,
              },
            ]
          : []),
      ];

  const sceneMenuItems: SceneMenuItem[] = [
    ...foldedIn,
    ...alwaysInMenu,
    ...extraControls,
    // Two `render` rows, both for the same reason: a control with more than two positions
    // flattened into that many menu items reads as that many unrelated commands, and the
    // current position has nowhere to show.
    ...(wide
      ? []
      : [
          ...(onViewModeChange
            ? [{
                key: "view",
                label: "View",
                render: (
                  <ViewModeSwitch viewMode={viewMode ?? "chat"} onChange={onViewModeChange} />
                ),
              }]
            : []),
          ...(health
            ? [{ key: "model", label: "Model", render: <ModelStatus health={health} /> }]
            : []),
          { key: "theme", label: "Theme", render: <ThemeSwitcher /> },
        ]),
  ];

  return (
    <HeaderBar>
      <HeaderLead>
        {/* A SQUARE below `sm`, and it has to be said in both dimensions: `px-sm py-xs`
            gave a control 10px taller than it was wide, which is what made the old bar
            read as a row of mismatched shapes rather than a set of buttons. */}
        <Link
          href={backHref}
          aria-label="Back to Library"
          className="flex h-control w-control touch-target-overlay flex-none items-center justify-center gap-2xs rounded-xs border border-field-bd font-mono text-eyebrow tracking-[0.1em] text-accent-ink uppercase hover:bg-accent hover:text-on-accent sm:w-auto sm:px-md"
        >
          <Icon name="back" size={14} />
          <span className="hidden sm:inline">Library</span>
        </Link>
        <span className="hidden h-[22px] w-px flex-none bg-hair-strong sm:block" aria-hidden />
        <div className="min-w-0">
          <div className="truncate font-display text-step-0 leading-none font-bold text-ink">
            {title}
          </div>
          {/* The title stands alone on a phone. The setting, genre and tone are all
              visible in the scene itself — `SceneIntro` opens with them — so a second
              line of chrome buys nothing and costs the bar its calm. */}
          <div className="mt-1 hidden truncate font-mono text-tag tracking-[0.14em] text-mute uppercase sm:block">
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
      {/* **Below `sm` this bar is back, title, menu — and nothing else.** Every control
          that used to sit here inline is in the menu instead, which is where the narrow
          header already sent most of them. The rule is not "fewer controls": it is that a
          `flex-none` cluster spends width a 320px screen does not have, so a control kept
          inline for convenience is paid for by the title being squeezed. */}
      <HeaderTrail className="gap-sm sm:gap-md">
        {wide ? (
          <>
            {onViewModeChange ? (
              <ViewModeSwitch viewMode={viewMode ?? "chat"} onChange={onViewModeChange} />
            ) : null}
            {wide ? tray : null}
            {wide ? <ThemeSwitcher /> : null}
            {/* The real model-health indicator, in the slot where a hardcoded green dot and
                "Narrator active" used to sit — a literal `<span>` reflecting no state at
                all. A status light that is always on teaches players to ignore every
                status light. */}
            <ModelStatus health={health} />
            {/* Two rails, and they are for two different questions: this one is the
                player's ("what does the scene know"), the Inspector is the developer's
                ("what did the loop do"). Mutually exclusive, because two 340px columns
                cannot both dock. */}
            {wide && onToggleMemory ? (
              <button
                type="button"
                onClick={onToggleMemory}
                aria-pressed={memoryOpen}
                aria-label="What the scene knows"
                title="How far back the cast remembers, and what it is reading"
                className="flex flex-none items-center gap-xs rounded-xs border border-field-bd px-sm py-xs font-mono text-eyebrow tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent-ink aria-pressed:border-accent aria-pressed:text-accent-ink"
              >
                <Icon name="knows" size={14} />
                <span className="hidden sm:inline">Memory</span>
              </button>
            ) : null}
          </>
        ) : null}
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
  { label: string; dot: string; text: string }
> = {
  reachable: { label: "Model ready", dot: "bg-success", text: "text-mute" },
  model_missing: { label: "Model not found", dot: "bg-gold", text: "text-gold-ink" },
  unreachable: { label: "Model unreachable", dot: "bg-danger", text: "text-danger-ink" },
  unconfigured: { label: "No model set", dot: "bg-mute2", text: "text-mute2" },
};

/**
 * Whether the model behind the scene is actually there.
 *
 * The dot is never the only channel: the label changes with the state, the `aria-label`
 * carries the endpoint's own explanation, and `role="status"` announces a change rather than
 * leaving it to be noticed. Renders nothing until the first check has answered — a light that
 * guesses is worse than one that waits.
 *
 * There used to be a second, glyph-only form for below `sm`, where the labelled one did not
 * fit the bar. It is gone with the bar: below `sm` this renders as a scene-menu row, where
 * there is room for the words. The state is still carried by shape as well as colour — the
 * label changes, not just the dot.
 */
function ModelStatus({ health }: { health: LlmHealth | null }) {
  if (!health) return null;
  const copy = HEALTH_COPY[health.state];
  return (
    <span
      role="status"
      aria-label={`${copy.label}. ${health.detail}`}
      title={health.backend ? `${health.detail} (${health.backend})` : health.detail}
      className="flex flex-none items-center gap-xs font-mono text-eyebrow tracking-[0.12em] uppercase"
    >
      <span aria-hidden className={`h-[6px] w-[6px] flex-none rounded-full ${copy.dot}`} />
      <span className={copy.text}>{copy.label}</span>
    </span>
  );
}
