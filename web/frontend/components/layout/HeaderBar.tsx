import { cn } from "@/lib/cn";

/**
 * The one top bar chassis.
 *
 * There were two hand-rolled bars sharing a visual language and no code:
 * `h-[52px] px-[16px] sm:px-[26px]` with a shadow (AppHeader) against
 * `h-[50px] px-[12px] sm:px-[24px]` with none (SceneHeader), both repeating
 * `mytheca-header flex flex-none items-center justify-between border-b
 * border-hair-strong`. The bar therefore changed height by 2px and gutter by
 * 2-4px when you navigated from the library into a scene — small enough that
 * nobody could name it, large enough to read as sloppiness.
 *
 * Height now comes from `--header-h`, the same token that drives
 * `scroll-padding-top` and `scroll-margin-block-start`. That is the point of
 * routing it through a token rather than a shared constant: the value that
 * keeps deep links and focused elements clear of the bar is, by construction,
 * the bar's actual height.
 */
export function HeaderBar({
  elevated = false,
  className,
  children,
  ...rest
}: {
  /** Library chrome floats over a scrolling page; scene chrome sits on a frame. */
  elevated?: boolean;
  className?: string;
  children: React.ReactNode;
} & Omit<React.HTMLAttributes<HTMLElement>, "children">) {
  return (
    <header
      className={cn(
        "mytheca-header relative z-[15] flex h-header flex-none items-center justify-between gap-md border-b border-hair-strong px-gutter",
        elevated && "shadow-md",
        className,
      )}
      {...rest}
    >
      {children}
    </header>
  );
}

/** The leading cluster — brand, back link, title. Shrinks; never overflows. */
export function HeaderLead({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 items-center gap-sm sm:gap-md", className)}>
      {children}
    </div>
  );
}

/**
 * The trailing cluster — controls.
 *
 * `flex-none` is deliberate and was arrived at the hard way: letting this
 * shrink pushes its intrinsically-sized children 50-150px past the edge rather
 * than the 7px you would hope for. The fix for a crowded bar is to collapse
 * controls into a menu, not to let the cluster squeeze.
 */
export function HeaderTrail({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-none items-center gap-sm", className)}>
      {children}
    </div>
  );
}
