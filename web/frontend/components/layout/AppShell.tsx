import { MotionProvider } from "@/components/layout/MotionProvider";

/**
 * App chrome wrapper: paints the themed page background + glow and sets the
 * base ink color. The active theme class lives on <html> (set pre-paint by the
 * no-flash script in app/layout.tsx); this wrapper just reads the tokens, so it
 * can stay a server component.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="velora-themed velora-page flex min-h-dvh flex-col text-ink">
      <MotionProvider>{children}</MotionProvider>
    </div>
  );
}
