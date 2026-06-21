// Placeholder home — replaced by the real Library surface in Phase 4.
// Exists so the scaffold renders something on-brand and verifies fonts + Tailwind.
export default function Home() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <span aria-hidden className="text-3xl text-[#8E2B1C]">
        {"❖"}
      </span>
      <h1 className="font-display text-4xl font-bold tracking-[0.2em]">VELORA</h1>
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-[#8E7A56]">
        A living manuscript — scaffold online
      </p>
    </main>
  );
}
