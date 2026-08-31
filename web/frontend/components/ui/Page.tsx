import { cn } from "@/lib/cn";

/**
 * The page frame.
 *
 * Before these, `AppShell` handed every route a bare `flex-col` div: no
 * measure, no gutter, no vertical rhythm. Each of the eight routes therefore
 * invented its own container, and they disagreed — `px-[16px] py-[22px]`
 * (documents), `px-[16px] py-[24px]` + `max-w-[1120px]` (options),
 * `px-[18px] py-[40px]` + `max-w-[1180px]` (creator), `mt-[16px]` and no
 * max-width at all (library). Nothing was wrong with any one of them, which is
 * precisely why the whole read as unstructured: there was nothing for them to
 * agree WITH.
 *
 * These four primitives are that something. They are intentionally boring —
 * they own measure, gutter and rhythm and nothing else, so a surface can be
 * expressive inside a frame that is not.
 */

/** How wide the content column is allowed to get. */
const MEASURE = {
  /** Long-form reading: transcripts, prose, a single document. */
  prose: "max-w-[72ch]",
  /** Forms and settings — wide enough for two columns, narrow enough to scan. */
  form: "max-w-[64rem]",
  /** Card grids and galleries. */
  wide: "max-w-[90rem]",
  /** Opt out: the surface manages its own width (the story player's rails). */
  full: "max-w-none",
} as const;

export type Measure = keyof typeof MEASURE;

/**
 * The `<main>` landmark and the content column.
 *
 * `id="main"` and `tabIndex={-1}` are load-bearing, not decoration: they are
 * what the skip link in `AppShell` targets, and `-1` is what lets focus land
 * here at all without putting the element into the tab order.
 *
 * Horizontal padding is the fluid `--gutter` token, so the frame breathes with
 * the viewport instead of stepping at breakpoints — and, unlike the hand-rolled
 * containers it replaces, it is the SAME breath on every route.
 */
export function Page({
  measure = "wide",
  className,
  children,
  ...rest
}: {
  measure?: Measure;
  className?: string;
  children: React.ReactNode;
} & Omit<React.HTMLAttributes<HTMLElement>, "children">) {
  return (
    <main
      id="main"
      tabIndex={-1}
      className={cn(
        "mx-auto w-full flex-1 px-gutter py-xl focus:outline-none",
        MEASURE[measure],
        className,
      )}
      {...rest}
    >
      {children}
    </main>
  );
}

/**
 * A titled band of related content.
 *
 * The heading is optional but the LEVEL is not: a section that renders a
 * heading must say which level it is, because "no skipped heading levels" is a
 * property of the page and no component can infer it from where it happens to
 * be mounted.
 */
export function Section({
  title,
  level = 2,
  description,
  actions,
  className,
  children,
}: {
  title?: React.ReactNode;
  level?: 2 | 3 | 4;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  const Heading = `h${level}` as "h2" | "h3" | "h4";
  return (
    <section className={cn("flex flex-col gap-lg", className)}>
      {title || actions || description ? (
        <div className="flex flex-wrap items-end justify-between gap-md">
          <div className="flex min-w-0 flex-col gap-2xs">
            {title ? (
              <Heading className="font-display text-step-1 leading-tight font-bold text-ink">
                {title}
              </Heading>
            ) : null}
            {description ? (
              <p className="max-w-[60ch] font-body text-body-sm text-ink-soft">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex items-center gap-sm">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** Vertical rhythm. One gap token, applied once, instead of per-child margins. */
export function Stack({
  gap = "lg",
  as: As = "div",
  className,
  children,
}: {
  gap?: "2xs" | "xs" | "sm" | "md" | "lg" | "xl" | "2xl" | "3xl";
  as?: "div" | "ul" | "ol" | "li" | "form";
  className?: string;
  children: React.ReactNode;
}) {
  return <As className={cn("flex flex-col", GAP[gap], className)}>{children}</As>;
}

/**
 * Horizontal rhythm that wraps.
 *
 * `flex-wrap` is the default rather than an option on purpose: a non-wrapping
 * row of controls is the single most reliable way to produce horizontal
 * overflow at 320px, and the audit's whole point is that the failure happens
 * per-section, not per-page.
 */
export function Cluster({
  gap = "sm",
  align = "center",
  as: As = "div",
  className,
  children,
}: {
  gap?: "2xs" | "xs" | "sm" | "md" | "lg" | "xl" | "2xl" | "3xl";
  align?: "start" | "center" | "end" | "baseline";
  as?: "div" | "ul" | "li";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <As className={cn("flex flex-wrap", GAP[gap], ALIGN[align], className)}>
      {children}
    </As>
  );
}

// Written out rather than interpolated: Tailwind scans source text, so
// `gap-${x}` produces no class at all.
const GAP = {
  "2xs": "gap-2xs",
  xs: "gap-xs",
  sm: "gap-sm",
  md: "gap-md",
  lg: "gap-lg",
  xl: "gap-xl",
  "2xl": "gap-2xl",
  "3xl": "gap-3xl",
} as const;

const ALIGN = {
  start: "items-start",
  center: "items-center",
  end: "items-end",
  baseline: "items-baseline",
} as const;
