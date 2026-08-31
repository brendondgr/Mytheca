import { cn } from "@/lib/cn";

/**
 * The one icon set.
 *
 * There were nine components drawing their own inline `<svg>`, each with its own
 * viewBox, stroke width and size — the same problem the design scales exist to fix,
 * one layer down. An icon tuned to look right beside one label cannot line up with an
 * icon tuned beside another, because there is nothing to line up to.
 *
 * The rules that make a set a set, rather than a folder of drawings:
 *
 * - **One 24 viewBox and one stroke weight**, so two icons at the same `size` have the
 *   same visual mass. A path drawn on a 16 grid and scaled up arrives 1.5x heavier.
 * - **`currentColor`, never a literal.** Every one of these sits inside a button that
 *   already changes colour on hover, focus and `aria-pressed`; a hardcoded stroke turns
 *   those states off for the glyph and leaves it stranded on the hover ground. `filled`
 *   flips fill from `none` to `currentColor` and is the one exception, for `pin`.
 * - **`aria-hidden` by default.** These are almost always beside a label or inside a
 *   button that carries an `aria-label`, and an icon that announces itself there is a
 *   duplicate reading. Passing `label` promotes it to `role="img"` for the rare case
 *   where the icon is the only content and the parent is not a labelled control.
 *
 * They replace glyph characters (`✎ ⚙ ◍ ❖ ‹ ›`) in chrome, which is not cosmetics: a
 * text glyph inherits the font stack, so it renders differently per platform, shifts the
 * line box, and lands at whatever size the type scale gives it rather than at the size
 * the control needs.
 */

/** The paths, on a 24 grid. Add one here rather than inlining an `<svg>` anywhere. */
const PATHS = {
  // ---- navigation & chrome ----
  back: "M15 5l-7 7 7 7",
  forward: "M9 5l7 7-7 7",
  up: "M5 15l7-7 7 7",
  down: "M5 9l7 7 7-7",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6L6 18",
  plus: "M12 5v14M5 12h14",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20.5 20.5L16 16",
  check: "M4 12.5l5 5L20 6.5",

  // ---- the library ----
  // A standing book: the storyline switcher's job is "which world am I in", and a
  // diamond said nothing about that.
  book: "M4 5.5A1.5 1.5 0 0 1 5.5 4H10a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H5.5A1.5 1.5 0 0 1 4 15.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H14a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h4.5a1.5 1.5 0 0 0 1.5-1.5z",
  pencil: "M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17zM15 6l3 3",
  // Sliders, not a gear: Options is a screen of preferences, and the gear is spoken
  // for by the scene's per-turn Config.
  sliders: "M5 7h9M18 7h1M5 12h3M12 12h7M5 17h9M18 17h1M16 5v4M10 10v4M16 15v4",
  trash: "M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12",
  // A page with lines — the storyline's source documents.
  docs: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6",
  // Whether a scene setting sticks past this turn. The only icon with two
  // states, which is why `filled` exists on the component at all.
  pin: "M12 17v5M9 10.8a2 2 0 0 1-1.1 1.8l-1.8.9A2 2 0 0 0 5 15.2V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.8a2 2 0 0 0-1.1-1.8l-1.8-.9a2 2 0 0 1-1.1-1.8V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z",

  // ---- the scene ----
  gear: "M12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6zM12 2.8l1 2.4 2.6-.5 1.1 2.4 2.4 1-.5 2.6 1.7 2-1.7 2 .5 2.6-2.4 1-1.1 2.4-2.6-.5-1 2.4-1-2.4-2.6.5-1.1-2.4-2.4-1 .5-2.6-1.7-2 1.7-2-.5-2.6 2.4-1L8.4 4.7 11 5.2z",
  // A clipboard with a tick — the plan, as a thing you sign off.
  plan: "M9 4h6v2H9zM15 5h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2M9 13l2 2 4-4",
  // Deliberation: a spark, not a brain. A brain at 14px is a grey blob.
  think: "M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5l2.6-1.5M17.2 9l2.6-1.5M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  cast: "M9 11a3.2 3.2 0 1 0 0-6.4A3.2 3.2 0 0 0 9 11zM2.5 19.5a6.5 6.5 0 0 1 13 0M16 5.2a3.2 3.2 0 0 1 0 6.2M18 13.6a6 6 0 0 1 3.5 5.9",
  person: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20.5a7.5 7.5 0 0 1 15 0",
  // A stage: the scene's own state, as distinct from who is standing in it.
  scene: "M3 5h18v11H3zM3 16l-2 3M21 16l2 3M8 16v3M16 16v3M9.5 8.5l4.5 2.5-4.5 2.5z",
  // What the scene remembers and is reading right now.
  knows: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8v4.5l3 2M8 3.5A9 9 0 0 0 3.5 8",
  graph: "M6 7a2.2 2.2 0 1 0 0-4.4A2.2 2.2 0 0 0 6 7zM18 21.4a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4zM18 9.6a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4zM7.6 6.3l8.8 1M7.4 8.9l9.2 8.6",
  chat: "M4.5 5.5h15v11h-9l-4 3.5v-3.5h-2z",
  image: "M4 5h16v14H4zM4 15l4.5-4.5 4 4L16 11l4 4M15.5 8.7a1.1 1.1 0 1 0 0-2.2 1.1 1.1 0 0 0 0 2.2z",

  // ---- the composer ----
  send: "M3.5 12h13M12 6.5l5.5 5.5-5.5 5.5",
  // A quill with a spark — "write this line for me", not "send it".
  write: "M4 20l3.5-.5L19 8a2.1 2.1 0 0 0-3-3L4.5 16.5zM15 5l3 3M19.5 15.5l.6 1.6 1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6z",
  undo: "M4 9h10a5 5 0 0 1 0 10H8M4 9l4-4M4 9l4 4",
} as const;

export type IconName = keyof typeof PATHS;

/** Every name, for the guard test — and so a picker could enumerate them. */
export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export function Icon({
  name,
  size = 16,
  label,
  className,
  filled = false,
  strokeWidth = 1.7,
}: {
  name: IconName;
  /** Edge length in px. The 24 grid scales; the stroke does not (see `strokeWidth`). */
  size?: number;
  /**
   * An accessible name. Omit it — the default — whenever the icon sits beside a visible
   * label or inside a control that carries its own `aria-label`, which is nearly always.
   */
  label?: string;
  className?: string;
  /**
   * Fill the shape with the current colour as well as stroking it. Exists for
   * `pin`, whose on/off state is the fill — the alternative was a second path,
   * and two glyphs for one control is how "pinned" and "not pinned" stop
   * reading as the same object in two states.
   */
  filled?: boolean;
  /**
   * Kept constant across sizes ON PURPOSE. `vectorEffect` is not used and the viewBox
   * scales, so a 24px icon and a 12px icon drawn at the same nominal weight arrive at
   * different apparent weights; the sizes in use here span 12-20px, where that
   * difference is smaller than the difference a per-icon stroke would introduce.
   */
  strokeWidth?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      xmlns="http://www.w3.org/2000/svg"
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
      className={cn("flex-none", className)}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
