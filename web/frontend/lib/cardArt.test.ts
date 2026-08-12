import { describe, it, expect } from "vitest";
import { CARD_SCRIM, PORTRAIT_SCRIM, OVER_ART, TEXT_BAND } from "./cardArt";

/**
 * Contrast of the over-art text against the worst artwork it can ever meet.
 *
 * `check_contrast.py` gates the theme tokens, but it cannot reach this: the
 * background here is not a token, it is a stack of translucent gradients over a
 * photograph. So the guarantee is computed instead — the scrim strings are
 * parsed, composited over **pure white** (the brightest thing generated art can
 * be), and the result measured against `OVER_ART`.
 *
 * Pure white is pessimistic on purpose. Real watercolour scene art sits far
 * below it, so anything that passes here passes everywhere.
 */

interface Stop {
  rgb: [number, number, number];
  alpha: number;
  /** Position along the gradient axis, 0–1. */
  at: number;
}

/** Split a multi-layer `background` value into its comma-separated gradients. */
function splitLayers(value: string): string[] {
  const layers: string[] = [];
  let depth = 0;
  let current = "";
  for (const ch of value) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (ch === "," && depth === 0) {
      layers.push(current.trim());
      current = "";
      continue;
    }
    current += ch;
  }
  if (current.trim()) layers.push(current.trim());
  return layers;
}

function parseStops(layer: string): Stop[] {
  const stops: Stop[] = [];
  const re = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)\s*([\d.]+)%/g;
  for (const m of layer.matchAll(re)) {
    stops.push({
      rgb: [Number(m[1]), Number(m[2]), Number(m[3])],
      alpha: m[4] === undefined ? 1 : Number(m[4]),
      at: Number(m[5]) / 100,
    });
  }
  return stops;
}

/** Linearly interpolate a layer's colour+alpha at `t` along its axis. */
function sampleLayer(stops: Stop[], t: number): { rgb: [number, number, number]; alpha: number } {
  if (t <= stops[0].at) return { rgb: stops[0].rgb, alpha: stops[0].alpha };
  const last = stops[stops.length - 1];
  if (t >= last.at) return { rgb: last.rgb, alpha: last.alpha };
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    if (t >= a.at && t <= b.at) {
      const f = (t - a.at) / (b.at - a.at);
      return {
        rgb: [
          a.rgb[0] + (b.rgb[0] - a.rgb[0]) * f,
          a.rgb[1] + (b.rgb[1] - a.rgb[1]) * f,
          a.rgb[2] + (b.rgb[2] - a.rgb[2]) * f,
        ],
        alpha: a.alpha + (b.alpha - a.alpha) * f,
      };
    }
  }
  return { rgb: last.rgb, alpha: last.alpha };
}

/** `source-over` compositing of one translucent colour onto a backdrop. */
function over(
  src: { rgb: [number, number, number]; alpha: number },
  backdrop: [number, number, number],
): [number, number, number] {
  return [
    src.rgb[0] * src.alpha + backdrop[0] * (1 - src.alpha),
    src.rgb[1] * src.alpha + backdrop[1] * (1 - src.alpha),
    src.rgb[2] * src.alpha + backdrop[2] * (1 - src.alpha),
  ];
}

/**
 * The colour actually behind the text at `t` along the scrim's axis, over white.
 *
 * CSS paints the FIRST listed background layer on top, so the layers are
 * composited back-to-front.
 */
function backdropAt(scrim: string, t: number): [number, number, number] {
  const layers = splitLayers(scrim).map(parseStops).filter((s) => s.length > 0);
  let result: [number, number, number] = [255, 255, 255];
  for (const stops of [...layers].reverse()) {
    result = over(sampleLayer(stops, t), result);
  }
  return result;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function contrast(fg: string, bg: [number, number, number]): number {
  const l1 = luminance(hexToRgb(fg));
  const l2 = luminance(bg);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

describe("card art scrim — contrast over the brightest possible artwork", () => {
  it("parses as the layers it is meant to have", () => {
    // Without this, a typo that made a layer unparseable would be silently
    // skipped by `backdropAt` — and every contrast assertion below would then
    // be measuring a scrim the browser is not actually painting.
    const card = splitLayers(CARD_SCRIM).map(parseStops);
    expect(card, "CARD_SCRIM: directional + bottom + flat wash").toHaveLength(3);
    for (const layer of card) expect(layer.length).toBeGreaterThanOrEqual(2);

    const portrait = splitLayers(PORTRAIT_SCRIM).map(parseStops);
    expect(portrait).toHaveLength(1);
    expect(portrait[0].length).toBeGreaterThanOrEqual(2);
  });

  it("holds AA for capped text across the whole text band", () => {
    // Sampled the length of the band, not just at its ends: the failure this
    // guards against was gradual, strong at the left edge and thinning out.
    for (const t of [0, 0.15, 0.3, 0.45, TEXT_BAND.bodyEnd]) {
      const bg = backdropAt(CARD_SCRIM, t);
      for (const [name, color] of [
        ["body", OVER_ART.body],
        ["eyebrow", OVER_ART.eyebrow],
        ["meta", OVER_ART.meta],
        ["accent", OVER_ART.accent],
      ] as const) {
        const ratio = contrast(color, bg);
        expect(
          ratio,
          `${name} at ${Math.round(t * 100)}% of the card = ${ratio.toFixed(2)}:1`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("holds the large-text bar out to the title's full line box", () => {
    // The title (19px bold) qualifies as large text, so 3:1 applies — but it
    // runs further right than the capped body copy, only reserving room for the
    // top-right control cluster.
    const bg = backdropAt(CARD_SCRIM, TEXT_BAND.titleEnd);
    const ratio = contrast(OVER_ART.title, bg);
    expect(ratio, `title at ${TEXT_BAND.titleEnd * 100}% = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(3);
  });

  it("still lets the artwork read on the right", () => {
    // The other half of the bargain, and the reason this number is asserted
    // rather than left to taste: a contrast problem is trivially "fixed" by
    // darkening everything, which quietly turns the artwork into a texture.
    //
    // The scrim before the flat wash was added left the far-right corner ~28%
    // darkened. The budget below is that, plus a little — the wash is meant to
    // read as a unifying tint, not as a second scrim. A first attempt at this
    // fix used a 0.16 wash and landed at 50%, which is what this caught.
    const [r, g, b] = backdropAt(CARD_SCRIM, 1);
    const darkening = 1 - luminance([r, g, b]) / luminance([255, 255, 255]);
    expect(darkening, `far-right darkening = ${(darkening * 100).toFixed(0)}%`).toBeLessThan(0.35);
  });

  it("holds AA for the portrait footer without washing the portrait", () => {
    // PORTRAIT_SCRIM's axis runs bottom-up, so the footer band is t = 0…0.22.
    for (const t of [0, 0.1, 0.22]) {
      const bg = backdropAt(PORTRAIT_SCRIM, t);
      for (const color of [OVER_ART.title, OVER_ART.body, OVER_ART.meta]) {
        expect(contrast(color, bg)).toBeGreaterThanOrEqual(4.5);
      }
    }
    // And the face — the top two-thirds — stays essentially untouched.
    const top = backdropAt(PORTRAIT_SCRIM, 0.7);
    expect(luminance(top)).toBeCloseTo(luminance([255, 255, 255]), 2);
  });
});
