import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";

// Placeholder home — replaced by the real Library surface in Phase 4.
// For now it demonstrates the themed tokens + the working ThemeSwitcher.
export default function Home() {
  return (
    <main className="relative flex min-h-dvh flex-col items-center justify-center gap-5 px-6 text-center">
      <div className="absolute right-6 top-6">
        <ThemeSwitcher />
      </div>
      <span aria-hidden className="text-3xl text-accent">
        {"❖"}
      </span>
      <h1 className="font-display text-4xl font-bold tracking-[0.2em] text-ink">
        VELORA
      </h1>
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-mute">
        A living manuscript — themed scaffold
      </p>
    </main>
  );
}
