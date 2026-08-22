#!/usr/bin/env node
/**
 * EXP-2026-08-012 — measure Core Web Vitals against a real production bundle.
 *
 * Serves `web/frontend`'s production build, drives the system Chromium through
 * `puppeteer-core` with 4x CPU throttling (docs/frontend-polish-spec.md §14), and records
 * CLS / INP / LCP for the two routes named in PROTOCOL.md.
 *
 * Writes `data/raw.json` (every load) and `data/metrics.json` (mean/std/n per metric per
 * route). It does NOT write manifest.yaml — that is filled by hand from these numbers, per
 * the research contract.
 *
 * Usage: node utils/scripts/research/run_core_web_vitals.mjs
 */

import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const frontend = path.join(repoRoot, "web", "frontend");
const outDir = path.join(repoRoot, "docs/research/experiments/EXP-2026-08-012-core-web-vitals/data");
const require = createRequire(path.join(frontend, "package.json"));
const puppeteer = require("puppeteer-core");

const CHROME = process.env.CHROME_PATH ?? "/usr/bin/chromium-browser";
const PORT = Number(process.env.VITALS_PORT ?? 3399);
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:3345";
const LOADS = Number(process.env.VITALS_LOADS ?? 5);
const CPU_THROTTLE = 4;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Ask the running backend for a real storyline/scenario, so the player route loads data. */
async function pickRoute() {
  const storylines = await (await fetch(`${BACKEND}/api/storylines`)).json();
  const list = Array.isArray(storylines) ? storylines : storylines.storylines;
  for (const s of list) {
    const res = await fetch(`${BACKEND}/api/storylines/${s.id}/scenarios`);
    const body = await res.json();
    const scenarios = Array.isArray(body) ? body : body.scenarios;
    if (scenarios?.length) return { storylineId: s.id, scenarioId: scenarios[0].id };
  }
  throw new Error("no storyline with a scenario on the backend — cannot measure the player route");
}

/**
 * Build with the flag ON.
 *
 * `NEXT_PUBLIC_*` is inlined at BUILD time, not read at runtime — setting it only when
 * starting the server is too late and yields a probe that never subscribes and a run of
 * zeroes. (It did, on the first attempt.) Building here rather than expecting the caller to
 * have done it keeps the entrypoint self-contained and reproducible.
 *
 * The measured bundle therefore CONTAINS the probe. That is stated in RESULTS.md as an
 * uncontrolled factor rather than hidden: `web-vitals` is ~2KB and subscribes to browser
 * APIs already running, but it is not nothing.
 */
function build() {
  return new Promise((resolve, reject) => {
    const proc = spawn("npx", ["next", "build"], {
      cwd: frontend,
      env: { ...process.env, NEXT_PUBLIC_VITALS: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    proc.stdout.on("data", (d) => process.stdout.write(`[build] ${d}`));
    proc.stderr.on("data", (d) => process.stderr.write(`[build] ${d}`));
    proc.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`next build exited ${code}`)),
    );
  });
}

function startServer() {
  const proc = spawn("npx", ["next", "start", "-p", String(PORT)], {
    cwd: frontend,
    env: { ...process.env, NEXT_PUBLIC_VITALS: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  proc.stdout.on("data", (d) => process.stdout.write(`[next] ${d}`));
  proc.stderr.on("data", (d) => process.stderr.write(`[next] ${d}`));
  return proc;
}

async function waitFor(url, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await sleep(500);
  }
  throw new Error(`${url} never came up`);
}

/**
 * One cold load: fresh context (no cache carried over), 4x CPU throttle, scripted
 * interaction to give INP something to measure, then read the probe's entries.
 *
 * `web-vitals` reports CLS and INP on visibility change, so the page is hidden at the end
 * rather than just closed — closing the tab would lose both.
 */
async function measure(browser, url, interact) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  const client = await page.createCDPSession();
  await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  await client.send("Emulation.setCPUThrottlingRate", { rate: CPU_THROTTLE });

  const started = Date.now();
  await page.goto(url, { waitUntil: "networkidle2", timeout: 120_000 });
  await sleep(1500);
  const clicked = interact ? await interact(page) : [];
  await sleep(1500);

  // Force the library to flush CLS + INP.
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await sleep(600);

  const entries = await page.evaluate(() => window.__mythecaVitals ?? []);
  await context.close();
  return { entries, clicked, wallMs: Date.now() - started };
}

/**
 * Click a few real controls, so INP has interactions to report — and RECORD WHICH ONES.
 *
 * An INP number without the interaction that produced it is not interpretable: "446ms" says
 * nothing about whether the app is slow or whether the script happened to open the heaviest
 * control on the page. The names go into raw.json beside the measurement.
 */
async function clickAround(page) {
  const clicked = [];
  const targets = await page.$$("button");
  for (const button of targets.slice(0, 4)) {
    let label = "<unnamed>";
    try {
      label = await button.evaluate(
        (el) => el.getAttribute("aria-label") || el.textContent?.trim().slice(0, 40) || "<unnamed>",
      );
      await button.click({ delay: 30 });
      clicked.push(label);
      await sleep(350);
    } catch {
      // A control that moved or is disabled. Recorded as skipped rather than dropped —
      // otherwise the clicked list silently misrepresents what the run actually did.
      clicked.push(`${label} (skipped)`);
    }
  }
  return clicked;
}

function summarise(loads) {
  const out = {};
  for (const name of ["CLS", "INP", "LCP"]) {
    // Last entry per load: `web-vitals` refines LCP as the page settles, and the final
    // value is the correct one.
    const values = loads
      .map((load) => load.entries.filter((e) => e.name === name).at(-1)?.value)
      .filter((v) => typeof v === "number");
    if (values.length === 0) {
      out[name] = { mean: null, std: null, n: 0 };
      continue;
    }
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
    out[name] = {
      mean: Number(mean.toFixed(4)),
      std: Number(Math.sqrt(variance).toFixed(4)),
      n: values.length,
      values: values.map((v) => Number(v.toFixed(4))),
    };
  }
  return out;
}

console.log("building with NEXT_PUBLIC_VITALS=1 …");
await build();
const server = startServer();
let exitCode = 0;
try {
  await waitFor(`http://localhost:${PORT}/`);
  // Fail loudly rather than reporting a run of zeroes: a probe that never subscribed is not
  // a measurement of "no layout shift".
  {
    const probe = await fetch(`http://localhost:${PORT}/`).then((r) => r.text());
    if (!probe.includes("__mythecaVitals") && !probe.includes("web-vitals")) {
      console.warn("warning: the served HTML shows no sign of the probe; checking live below.");
    }
  }
  const route = await pickRoute();
  const routes = [
    { key: "library", path: "/", interact: clickAround },
    {
      key: "story-player",
      path: `/${route.storylineId}/${route.scenarioId}`,
      interact: clickAround,
    },
  ];

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });

  const raw = {};
  const metrics = {};
  const failures = [];
  for (const r of routes) {
    const loads = [];
    for (let i = 0; i < LOADS; i++) {
      process.stdout.write(`measuring ${r.key} load ${i + 1}/${LOADS}…\n`);
      try {
        loads.push(await measure(browser, `http://localhost:${PORT}${r.path}`, r.interact));
      } catch (err) {
        failures.push({ route: r.key, load: i + 1, error: String(err.message ?? err) });
      }
    }
    raw[r.key] = { path: r.path, loads };
    metrics[r.key] = summarise(loads);
  }
  await browser.close();

  const collected = Object.values(metrics).flatMap((m) => Object.values(m).map((v) => v.n));
  if (collected.every((n) => n === 0)) {
    throw new Error(
      "every metric came back empty — the probe did not subscribe. Most likely the bundle " +
        "was built without NEXT_PUBLIC_VITALS=1. A run of zeroes is not a measurement.",
    );
  }

  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    path.join(outDir, "raw.json"),
    JSON.stringify({ route, cpuThrottle: CPU_THROTTLE, loads: LOADS, raw, failures }, null, 2),
  );
  writeFileSync(
    path.join(outDir, "metrics.json"),
    JSON.stringify(
      {
        experiment: "EXP-2026-08-012",
        cpu_throttle: CPU_THROTTLE,
        loads_per_route: LOADS,
        target: route,
        thresholds: { CLS: 0.1, INP: 200, LCP: 2500 },
        routes: metrics,
        failures,
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify(metrics, null, 2));
  if (failures.length) {
    console.error(`\n${failures.length} load(s) failed — record them in ISSUES.md.`);
    exitCode = 0; // a partial run is still a run; the contract says record it, not hide it
  }
} catch (err) {
  console.error(err);
  exitCode = 1;
} finally {
  server.kill("SIGTERM");
}
process.exit(exitCode);
