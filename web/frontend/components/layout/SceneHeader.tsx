import type { LlmHealth } from "@/lib/types";
import type { ReactNode } from "react";
import Link from "next/link";
import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";
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
  onToggleMemory,
  memoryOpen = false,
  health = null,
  tray,
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
}) {
  const meta = [`◆ ${settingName}`, genre, tone].filter(Boolean).join(" · ");
  // Built here rather than by the caller so the header owns which of its controls fold in.
  const sceneMenuItems: SceneMenuItem[] = [
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
  ];

  return (
    <header className="mytheca-header flex h-[50px] flex-none items-center justify-between gap-2 border-b border-hair-strong px-[12px] sm:gap-3 sm:px-[24px]">
      <div className="flex min-w-0 items-center gap-[8px] sm:gap-[14px]">
        <Link
          href={backHref}
          aria-label="Back to Library"
          className="flex flex-none items-center gap-[7px] rounded-[2px] border border-field-bd px-[9px] py-[6px] font-mono text-[10px] tracking-[0.1em] text-accent uppercase hover:bg-accent hover:text-[#F6ECDA] sm:px-[11px]"
        >
          ‹<span className="hidden sm:inline">&nbsp;Library</span>
        </Link>
        <span className="h-[22px] w-px flex-none bg-hair-strong" aria-hidden />
        <div className="min-w-0">
          <div className="truncate font-display text-[16px] font-bold leading-none text-ink">
            {title}
          </div>
          <div className="mt-1 truncate font-mono text-tag tracking-[0.14em] text-mute uppercase">
            {meta} · live scene
          </div>
        </div>
      </div>
      {/* Deliberately `flex-none`. Letting this cluster shrink was tried and is
        * worse: its children have intrinsic widths, so a squeezed container
        * pushes them 50–150px past the edge instead of 7px. The real fix for
        * the 320px floor is to collapse controls below `sm` — a design change,
        * not a layout tweak. Tracked in docs/checklist.md. */}
      <div className="flex flex-none items-center gap-[8px] sm:gap-[14px]">
        {onViewModeChange ? (
          <ViewModeSwitch viewMode={viewMode ?? "chat"} onChange={onViewModeChange} />
        ) : null}
        {tray}
        <ThemeSwitcher />
        {/* The real model-health indicator, in the slot where a hardcoded green dot and
            "Narrator active" used to sit — a literal `<span>` reflecting no state at all. A
            status light that is always on teaches players to ignore every status light.
            Inside the `hidden … sm:flex` cluster, so the 320px control count is unchanged;
            the durable 320px fix is `docs/plans/reach.md` Phase 4's header overflow menu. */}
        <ModelStatus health={health} />
        {/* Two rails, and they are for two different questions: this one is the player's
            ("what does the scene know"), the Inspector is the developer's ("what did the loop
            do"). Mutually exclusive, because two 340px columns cannot both dock. */}
        {onToggleMemory ? (
          <button
            type="button"
            onClick={onToggleMemory}
            aria-pressed={memoryOpen}
            aria-label="What the scene knows"
            title="How far back the cast remembers, and what it is reading"
            className="flex flex-none items-center gap-[6px] rounded-[2px] border border-field-bd px-[9px] py-[6px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-pressed:border-accent aria-pressed:text-accent sm:px-[10px]"
          >
            <span aria-hidden>◍</span>
            <span className="hidden sm:inline">Memory</span>
          </button>
        ) : null}
        {/* One popover replacing three inline controls (Export, Inspector, and the new
            Writing entry point). The cluster is `flex-none`, so every control here costs
            width a 320px screen does not have — folding them in is how the header gains
            capability while losing width. */}
        {sceneMenuItems.length > 0 ? <SceneMenu items={sceneMenuItems} /> : null}
      </div>
    </header>
  );
}

/** How each health state reads to a player, in words — never by colour alone. */
const HEALTH_COPY: Record<
  LlmHealth["state"],
  { label: string; dot: string; text: string }
> = {
  reachable: { label: "Model ready", dot: "bg-success", text: "text-mute" },
  model_missing: { label: "Model not found", dot: "bg-gold", text: "text-gold" },
  unreachable: { label: "Model unreachable", dot: "bg-danger", text: "text-danger" },
  unconfigured: { label: "No model set", dot: "bg-mute2", text: "text-mute2" },
};

/**
 * Whether the model behind the scene is actually there.
 *
 * The dot is never the only channel: the label changes with the state, the `aria-label`
 * carries the endpoint's own explanation, and `role="status"` announces a change rather than
 * leaving it to be noticed. Renders nothing until the first check has answered — a light that
 * guesses is worse than one that waits.
 */
function ModelStatus({ health }: { health: LlmHealth | null }) {
  if (!health) return null;
  const copy = HEALTH_COPY[health.state];
  return (
    <span
      role="status"
      aria-label={`${copy.label}. ${health.detail}`}
      title={
        health.backend ? `${health.detail} (${health.backend})` : health.detail
      }
      className="hidden flex-none items-center gap-[6px] font-mono text-[9px] tracking-[0.12em] uppercase sm:flex"
    >
      <span aria-hidden className={`h-[6px] w-[6px] flex-none rounded-full ${copy.dot}`} />
      <span className={copy.text}>{copy.label}</span>
    </span>
  );
}
