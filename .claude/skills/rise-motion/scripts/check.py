#!/usr/bin/env python3
"""The E in RISE: render the frames at 0%, 25%, 50%, 75% and 100% in every format, run the
checks a machine can do, and lay the frames out on contact sheets for the checks only eyes can do.

  python scripts/check.py motion/my-piece/index.html
  python scripts/check.py motion/my-piece/index.html --formats 9:16 --out /tmp/checks
  python scripts/check.py motion/films/index.html --brand motion/films/brands/acme-com

Writes <out>/contact-<format>.jpg, <out>/frames/<format>-<pct>.jpg, report.md and report.json
(default <out> is a `checks/` folder next to the file). Exit code 1 when a hard check fails.

Hard failures: page errors, missing RISE contract, Math.random/clock reads inside render,
non-deterministic frames, a loop seam (frame 0 ≠ last frame), fonts that did not load,
nothing moving. Warnings: flat colour, stage fill, empty first frame, text outside the frame,
tight line height, one-word last lines, text held < 1.2 s, a jump at the loop point, slow renders.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _rise  # noqa: E402

PCTS = [0, 25, 50, 75, 100]

# Installed once per page, after DRAW_JS. Everything heavy runs in the page so only small
# results cross back to Python.
CHECK_JS = r"""
() => {
  if (window.__riseCheck) return;
  const R = window.__rise, ctx = R.ctx;
  const counts = { random: 0, clock: 0 };
  let inRender = false, texts = null;
  const usedFonts = new Set();

  // Purity: count randomness and clock reads made while render() runs.
  const rnd = Math.random, pnow = performance.now.bind(performance), dnow = Date.now;
  Math.random = function () { if (inRender) counts.random++; return rnd(); };
  performance.now = function () { if (inRender) counts.clock++; return pnow(); };
  Date.now = function () { if (inRender) counts.clock++; return dnow(); };

  // Fonts set on any canvas during render().
  const fontDesc = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, 'font');
  Object.defineProperty(CanvasRenderingContext2D.prototype, 'font', {
    configurable: true,
    get() { return fontDesc.get.call(this); },
    set(v) { if (inRender) usedFonts.add(String(v)); fontDesc.set.call(this, v); },
  });

  // Text drawn on the frame canvas: where it lands and how visible it is.
  for (const fn of ['fillText', 'strokeText']) {
    const orig = CanvasRenderingContext2D.prototype[fn];
    ctx[fn] = function (text, x, y, maxWidth) {
      if (texts && String(text).trim()) {
        const m = this.measureText(String(text));
        let l = -m.actualBoundingBoxLeft, r = m.actualBoundingBoxRight;
        if (maxWidth !== undefined && m.width > maxWidth && m.width > 0) { const k = maxWidth / m.width; l *= k; r *= k; }
        const top = -m.actualBoundingBoxAscent, bot = m.actualBoundingBoxDescent, T = this.getTransform();
        const P = [[x + l, y + top], [x + r, y + top], [x + l, y + bot], [x + r, y + bot]]
          .map(([px, py]) => [T.a * px + T.c * py + T.e, T.b * px + T.d * py + T.f]);
        const xs = P.map(p => p[0]), ys = P.map(p => p[1]);
        const scale = Math.sqrt(Math.abs(T.a * T.d - T.b * T.c)) || 1;
        const px = parseFloat((this.font.match(/([\d.]+)px/) || [0, 0])[1]) * scale;
        texts.push({ text: String(text), font: this.font, px, alpha: this.globalAlpha, role: this.riseRole || '',
          x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys),
          bx: T.a * x + T.c * y + T.e, by: T.b * x + T.d * y + T.f });
      }
      return maxWidth === undefined ? orig.call(this, text, x, y) : orig.call(this, text, x, y, maxWidth);
    };
  }

  const snaps = {};
  let sheet = null;

  window.__riseCheck = {
    counts,
    draw(t, w, h, recordText) {
      texts = recordText ? [] : null;
      inRender = true;
      let err = null;
      const t0 = pnow();
      // Chrome records canvas calls and rasterizes lazily; a 1-pixel read forces the real work.
      try { R.draw(t, w, h); ctx.getImageData(0, 0, 1, 1); } catch (e) { err = String((e && e.stack) || e); }
      const ms = pnow() - t0;
      inRender = false;
      const out = texts; texts = null;
      return { err, ms, texts: out };
    },
    snap(key) { snaps[key] = ctx.getImageData(0, 0, R.canvas.width, R.canvas.height); },
    drop() { for (const k of Object.keys(snaps)) delete snaps[k]; },
    diff(a, b) {
      const A = snaps[a], B = snaps[b];
      if (!A || !B || A.width !== B.width || A.height !== B.height) return null;
      const d1 = A.data, d2 = B.data, w = A.width, h = A.height, bs = 16;
      const bx = Math.ceil(w / bs), by = Math.ceil(h / bs), nb = bx * by;
      const sums = new Float64Array(nb), la = new Float64Array(nb), lb = new Float64Array(nb), ns = new Uint32Array(nb);
      let sum = 0;
      for (let y = 0; y < h; y++) {
        const row = ((y / bs) | 0) * bx;
        for (let x = 0; x < w; x++) {
          const i = (y * w + x) * 4;
          const d = (Math.abs(d1[i] - d2[i]) + Math.abs(d1[i + 1] - d2[i + 1]) + Math.abs(d1[i + 2] - d2[i + 2]) + Math.abs(d1[i + 3] - d2[i + 3])) / 4;
          const k = row + ((x / bs) | 0);
          sum += d; sums[k] += d; ns[k]++;
          la[k] += 0.2126 * d1[i] + 0.7152 * d1[i + 1] + 0.0722 * d1[i + 2];
          lb[k] += 0.2126 * d2[i] + 0.7152 * d2[i + 1] + 0.0722 * d2[i + 2];
        }
      }
      let blockMax = 0;
      const coarse = new Float64Array(nb);
      for (let k = 0; k < nb; k++) if (ns[k]) { blockMax = Math.max(blockMax, sums[k] / ns[k]); coarse[k] = Math.abs(la[k] - lb[k]) / ns[k]; }
      // Block means cancel grain, so this measures real movement: mean of the top 1% of blocks.
      coarse.sort(); const top = Math.max(4, Math.ceil(nb * 0.01));
      let coarseTop = 0; for (let k = nb - top; k < nb; k++) coarseTop += coarse[k];
      return { mean: sum / (w * h), blockMax, identical: sum === 0, coarseTop: coarseTop / top };
    },
    stats() {
      const w = R.canvas.width, h = R.canvas.height, d = ctx.getImageData(0, 0, w, h).data;
      const hist = new Map();
      let n = 0, clear = 0;
      for (let y = 0; y < h; y += 2) for (let x = 0; x < w; x += 2) {
        const i = (y * w + x) * 4;
        if (d[i + 3] < 250) { clear++; continue; }
        const key = (d[i] << 16) | (d[i + 1] << 8) | d[i + 2];
        hist.set(key, (hist.get(key) || 0) + 1); n++;
      }
      let topKey = 0, top = 0;
      for (const [k, v] of hist) if (v > top) { top = v; topKey = k; }
      // Coarse luminance grid (averaging kills grain), then edges → where the content is.
      const gw = 160, gh = Math.max(4, Math.round(160 * h / w)), cw = w / gw, ch = h / gh;
      const lum = new Float32Array(gw * gh);
      let lsum = 0, lsq = 0;
      for (let gy = 0; gy < gh; gy++) for (let gx = 0; gx < gw; gx++) {
        let s = 0, c = 0;
        const xa = Math.floor(gx * cw), xb = Math.max(xa + 1, Math.floor((gx + 1) * cw));
        const ya = Math.floor(gy * ch), yb = Math.max(ya + 1, Math.floor((gy + 1) * ch));
        for (let y = ya; y < yb; y += 2) for (let x = xa; x < xb; x += 2) {
          const i = (y * w + x) * 4, a = d[i + 3] / 255;
          s += a * (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]); c++;
        }
        const v = c ? s / c : 0; lum[gy * gw + gx] = v; lsum += v; lsq += v * v;
      }
      const N = gw * gh, mean = lsum / N, std = Math.sqrt(Math.max(0, lsq / N - mean * mean));
      // A row/column counts as content once it holds ≥ 2 edge cells, so faint strokes count and
      // lone specks don't stretch the box.
      const rowHits = new Uint16Array(gh), colHits = new Uint16Array(gw);
      let edgeCells = 0;
      for (let gy = 2; gy < gh - 2; gy++) for (let gx = 2; gx < gw - 2; gx++) {
        const dx = lum[gy * gw + gx + 1] - lum[gy * gw + gx - 1], dy = lum[(gy + 1) * gw + gx] - lum[(gy - 1) * gw + gx];
        if (Math.hypot(dx, dy) > 10) { rowHits[gy]++; colHits[gx]++; edgeCells++; }
      }
      const span = hits => { let a = -1, b = -1; hits.forEach((v, i) => { if (v >= 2) { if (a < 0) a = i; b = i; } }); return a < 0 ? 0 : (b - a + 1) / hits.length; };
      const fillW = span(colHits), fillH = span(rowHits);
      const xs = { length: edgeCells };
      return { flatShare: n ? top / n : 0, flatColor: '#' + topKey.toString(16).padStart(6, '0'),
               clearShare: (clear / (n + clear)) || 0, lumMean: mean, lumStd: std,
               edgeCells: xs.length, fillW, fillH };
    },
    fonts() {
      const clean = s => s.trim().replace(/^["']|["']$/g, '');
      const generic = /^(serif|sans-serif|monospace|cursive|fantasy|system-ui|emoji|math|fangsong|ui-[\w-]+)$/i;
      const probe = document.createElement('canvas').getContext('2d'), sample = 'mmmmmmmmmmlli WwQq@#0123456789';
      const width = f => { probe.font = f; return probe.measureText(sample).width; };
      const out = [];
      for (const f of usedFonts) {
        const m = f.match(/([\d.]+)px\s+(.+)$/);
        if (!m) continue;
        const fam = clean(m[2].split(',')[0]);
        if (generic.test(fam)) { out.push({ font: f, family: fam, ok: true, how: 'generic family' }); continue; }
        const faces = [...document.fonts].filter(x => clean(x.family) === fam);
        if (faces.length) {
          if (faces.every(x => x.status === 'error')) { out.push({ font: f, family: fam, ok: false, how: 'webfont failed to download' }); continue; }
          const ready = document.fonts.check(f);
          out.push({ font: f, family: fam, ok: ready, how: ready ? 'webfont loaded' : 'declared but not loaded before render (add it to FONTS)' });
          continue;
        }
        let local = false;
        for (const fb of ['monospace', 'serif', 'sans-serif']) if (width(`72px "${fam}", ${fb}`) !== width(`72px ${fb}`)) { local = true; break; }
        out.push({ font: f, family: fam, ok: local, how: local ? 'installed on this machine' : 'not available, drawn in a fallback font' });
      }
      return out;
    },
    sheetStart(cols, rows, tw, th, title) {
      const pad = 16, lab = 30, head = 46;
      const c = document.createElement('canvas');
      c.width = cols * tw + (cols + 1) * pad; c.height = head + rows * (th + lab) + (rows + 1) * pad;
      const g = c.getContext('2d');
      g.fillStyle = '#111113'; g.fillRect(0, 0, c.width, c.height);
      g.fillStyle = '#e8e6e1'; g.font = '600 20px sans-serif'; g.textBaseline = 'middle';
      g.fillText(title, pad, head / 2 + 4);
      sheet = { c, g, cols, tw, th, pad, lab, head };
    },
    sheetAdd(i, label, bad, diffWith) {
      const { c, g, cols, tw, th, pad, lab, head } = sheet;
      const x = pad + (i % cols) * (tw + pad), y = head + pad + Math.floor(i / cols) * (th + lab + pad);
      g.fillStyle = '#2a2a2e'; g.fillRect(x - 1, y - 1, tw + 2, th + 2);
      if (diffWith) {
        // |A − B| × 8 in a small canvas, scaled up: black means the two frames match.
        const A = snaps[diffWith[0]], B = snaps[diffWith[1]], w = A.width, h = A.height;
        const small = document.createElement('canvas'); small.width = tw; small.height = th;
        const sg = small.getContext('2d'), img = sg.createImageData(tw, th);
        for (let yy = 0; yy < th; yy++) for (let xx = 0; xx < tw; xx++) {
          const sx = Math.floor(xx * w / tw), sy = Math.floor(yy * h / th), i = (sy * w + sx) * 4, o = (yy * tw + xx) * 4;
          for (let k = 0; k < 3; k++) img.data[o + k] = Math.min(255, Math.abs(A.data[i + k] - B.data[i + k]) * 8);
          img.data[o + 3] = 255;
        }
        sg.putImageData(img, 0, 0); g.drawImage(small, x, y);
      } else {
        // Checkerboard shows through anywhere the frame is transparent (e.g. a clip goes there).
        g.save(); g.beginPath(); g.rect(x, y, tw, th); g.clip();
        g.fillStyle = '#6b6b70'; for (let yy = 0; yy < th; yy += 12) for (let xx = (yy / 12) % 2 ? 12 : 0; xx < tw; xx += 24) g.fillRect(x + xx, y + yy, 12, 12);
        g.imageSmoothingQuality = 'high'; g.drawImage(R.canvas, x, y, tw, th);
        g.restore();
      }
      g.fillStyle = bad ? '#ff6b5b' : '#bdbab3'; g.font = '500 15px sans-serif'; g.textBaseline = 'middle';
      g.fillText(label, x, y + th + lab / 2 + 2);
    },
    sheetJPEG() { return sheet.c.toDataURL('image/jpeg', 0.9); },
  };
}
"""


class Report:
    def __init__(self):
        self.items = []  # (level, fmt, name, detail)

    def add(self, level, fmt, name, detail=""):
        self.items.append({"level": level, "format": fmt, "check": name, "detail": detail})

    def failures(self):
        return [i for i in self.items if i["level"] == "fail"]

    def warnings(self):
        return [i for i in self.items if i["level"] == "warn"]


def text_findings(texts, w, h):
    """Warnings from one frame's text records: outside the frame, tight leading, orphans."""
    out = []
    items = [t for t in texts if t["alpha"] >= 0.6 and t["px"] > 0]
    for it in items:
        if it["x0"] < -1 or it["y0"] < -1 or it["x1"] > w + 1 or it["y1"] > h + 1:
            out.append(f"text {it['text'][:40]!r} runs outside the frame (clipped); if a mask hides it on "
                       "purpose, skip drawing it while it's fully hidden")
    # Lines: same font, same baseline (letters drawn one by one join up again here).
    lines = []
    for it in sorted(items, key=lambda t: (t["font"], t["by"], t["x0"])):
        for ln in lines:
            if ln["font"] == it["font"] and abs(ln["by"] - it["by"]) < 0.25 * it["px"]:
                ln["items"].append(it)
                break
        else:
            lines.append({"font": it["font"], "by": it["by"], "px": it["px"], "items": [it]})
    for ln in lines:
        parts = sorted(ln["items"], key=lambda t: t["x0"])
        text, prev = "", None
        for p in parts:
            if prev is not None and p["x0"] - prev["x1"] > 0.22 * ln["px"]:
                text += " "
            text += p["text"]
            prev = p
        ln["text"] = " ".join(text.split())
        ln["x0"], ln["x1"] = min(p["x0"] for p in parts), max(p["x1"] for p in parts)
    # Blocks: lines of one font stacked close together and overlapping horizontally.
    by_font = {}
    for ln in lines:
        by_font.setdefault(ln["font"], []).append(ln)
    for font, lns in by_font.items():
        lns.sort(key=lambda l: l["by"])
        block = [lns[0]]
        blocks = []
        for a, b in zip(lns, lns[1:]):
            gap = b["by"] - a["by"]
            overlap = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            if 0.3 * a["px"] < gap < 2.2 * a["px"] and overlap > 0:
                block.append(b)
            else:
                blocks.append(block)
                block = [b]
        blocks.append(block)
        for blk in blocks:
            if len(blk) < 2:
                continue
            for a, b in zip(blk, blk[1:]):
                ratio = (b["by"] - a["by"]) / a["px"]
                if ratio < 1.1:
                    out.append(f"line height {ratio:.2f} between {a['text'][:24]!r} and {b['text'][:24]!r} "
                               "(keep ≥ 1.1 so ascenders and descenders never touch)")
            last = blk[-1]["text"]
            if len(last.split()) == 1 and len(blk[-2]["text"].split()) > 1:
                out.append(f"one word alone on the last line: {last!r} (rewrite or tie the last two words)")
    return out


def hold_findings(samples, step, duration):
    """samples: list of sets of visible text strings, one per step seconds. Returns warnings."""
    out = []
    n = len(samples)
    keys = set().union(*samples) if samples else set()
    for key in sorted(keys):
        vis = [key in s for s in samples]
        if all(vis):
            continue
        runs, run = [], 0
        for v in vis:
            if v:
                run += 1
            elif run:
                runs.append(run)
                run = 0
        if run:
            runs.append(run)
        if vis[0] and vis[-1] and len(runs) > 1:  # the loop joins the last run to the first
            runs[0] += runs.pop()
        shortest = min(runs) * step
        if shortest < 1.2 - 1e-6:
            out.append(f"text {key[:40]!r} is readable for only {shortest:.1f}s (hold words ≥ 1.2s)")
    return out


async def check_format(page, fmt, w, h, info, out_dir, report, title, quick=False):
    D, fps = info["DURATION"], info["FPS"]
    chk = "window.__riseCheck"
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    slug = _rise.fmt_slug(fmt)

    # Warm-up render builds cached textures so timings reflect steady state.
    warm = await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, false)", [D * 0.5, w, h])
    if warm["err"]:
        report.add("fail", fmt, "render throws", warm["err"].splitlines()[0])
        return
    await page.evaluate(f"() => {chk}.drop()")

    aspect = w / h
    tw = 512 if aspect >= 1.25 else (400 if aspect >= 0.8 else 250)
    th = round(tw / aspect)
    cols = 3 if aspect >= 0.8 else 6
    rows = 2 if cols == 3 else 1
    await page.evaluate(f"([c, r, tw, th, title]) => {chk}.sheetStart(c, r, tw, th, title)",
                        [cols, rows, tw, th, f"{title} · {fmt} · {w}×{h} · {D:.2f}s loop"])

    stats, times, frame_texts = {}, [], {}
    for i, pct in enumerate(PCTS):
        t = D * pct / 100
        r = await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, true)", [t, w, h])
        if r["err"]:
            report.add("fail", fmt, f"render throws at {pct}%", r["err"].splitlines()[0])
            return
        times.append(r["ms"])
        frame_texts[pct] = r["texts"] or []
        await page.evaluate(f"(k) => {chk}.snap(k)", f"p{pct}")
        stats[pct] = await page.evaluate(f"() => {chk}.stats()")
        jpeg = await page.evaluate(f"([w, h]) => window.__rise.canvas.toDataURL('image/jpeg', 0.9)", [w, h])
        (frames_dir / f"{slug}-{pct:03d}.jpg").write_bytes(_rise.decode_data_url(jpeg))
        await page.evaluate(f"([i, label]) => {chk}.sheetAdd(i, label, false, null)",
                            [i, f"{pct}% · {t:.2f}s"])

    # Loop seam: the last frame must be the first frame.
    seam = await page.evaluate(f"() => {chk}.diff('p0', 'p100')")
    seam_bad = seam["mean"] > 0.35 or seam["blockMax"] > 3
    await page.evaluate(f"([i, label, bad]) => {chk}.sheetAdd(i, label, bad, ['p0', 'p100'])",
                        [5, f"seam |0% − 100%| ×8 · mean Δ {seam['mean']:.2f}", seam_bad])
    (out_dir / f"contact-{slug}.jpg").write_bytes(_rise.decode_data_url(await page.evaluate(f"() => {chk}.sheetJPEG()")))
    if seam_bad:
        report.add("fail", fmt, "loop seam", f"frame 0 and frame {D:.2f}s differ (mean Δ {seam['mean']:.2f}, "
                   f"worst block Δ {seam['blockMax']:.1f}); make every motion return to its start at t = DURATION")
    else:
        report.add("pass", fmt, "loop seam", f"frame 0 = frame {D:.2f}s (mean Δ {seam['mean']:.2f})")

    # Motion: something has to change between the quarter frames.
    moves = [await page.evaluate(f"([a, b]) => {chk}.diff(a, b)", [f"p{a}", f"p{b}"])
             for a, b in [(0, 25), (0, 50), (0, 75), (25, 50), (50, 75)]]
    most = max(m["coarseTop"] for m in moves)
    if most < 4:
        report.add("fail", fmt, "motion", "the 0/25/50/75% frames are practically identical (only grain changes): "
                   "nothing visibly moves")
    else:
        report.add("pass", fmt, "motion", f"frames differ (largest block change {most:.0f})")

    # Determinism: same t → same pixels, even after drawing other frames.
    tA = round(D * 0.37, 4)
    await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, false)", [tA, w, h])
    await page.evaluate(f"(k) => {chk}.snap(k)", "detA")
    await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, false)", [round(D * 0.81, 4), w, h])
    await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, false)", [tA, w, h])
    await page.evaluate(f"(k) => {chk}.snap(k)", "detB")
    det = await page.evaluate(f"() => {chk}.diff('detA', 'detB')")
    if det["identical"]:
        report.add("pass", fmt, "deterministic", "same t gives identical pixels")
    elif det["mean"] <= 0.02 and det["blockMax"] <= 1:
        report.add("warn", fmt, "deterministic", f"tiny differences for the same t (mean Δ {det['mean']:.3f})")
    else:
        report.add("fail", fmt, "deterministic", f"t = {tA}s drew different pixels the second time (mean Δ {det['mean']:.2f}); "
                   "render must depend only on t: no state kept between frames, no Math.random")

    # Jump at the loop point: compare the seam step with ordinary frame-to-frame steps, measured on
    # block means so grain re-rolls don't count as movement.
    dt = 1 / fps
    steps = []
    for k, frac in enumerate([0.137, 0.389, 0.613, 0.871]):
        t0 = round(D * frac, 4)
        for key, tt in ((f"s{k}a", t0), (f"s{k}b", t0 + dt)):
            await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, false)", [tt, w, h])
            await page.evaluate(f"(k) => {chk}.snap(k)", key)
        steps.append((await page.evaluate(f"([a, b]) => {chk}.diff(a, b)", [f"s{k}a", f"s{k}b"]))["coarseTop"])
    await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, false)", [D - dt, w, h])
    await page.evaluate(f"(k) => {chk}.snap(k)", "end1")
    seam_step = (await page.evaluate(f"() => {chk}.diff('end1', 'p100')"))["coarseTop"]
    typical = statistics.median(steps)
    if seam_step > max(3 * typical, typical + 6.0):
        report.add("warn", fmt, "loop point", f"the step from {D - dt:.2f}s to {D:.2f}s (Δ {seam_step:.1f}) is much bigger than a "
                   f"normal frame step (Δ {typical:.1f}): a visible jump when the loop restarts. Fine only if the "
                   "brief calls for a hard cut.")
    else:
        report.add("pass", fmt, "loop point", f"no jump when the loop restarts (Δ {seam_step:.1f} vs typical {typical:.1f})")
    await page.evaluate(f"() => {chk}.drop()")

    # Texture / flat colour.
    flat = max(stats.values(), key=lambda s: s["flatShare"])
    if flat["flatShare"] > 0.12:
        report.add("warn", fmt, "flat colour", f"{flat['flatShare'] * 100:.0f}% of the frame is one exact colour "
                   f"({flat['flatColor']}): add grain, paper or a light falloff so the ground is never flat")
    else:
        report.add("pass", fmt, "texture", f"largest single-colour area {flat['flatShare'] * 100:.1f}% of the frame")

    # Stage fill: the content box across the frames.
    # The best frame on each axis counts: a wide lockup fills the width, a burst fills the height.
    along = (lambda s: s["fillW"]) if w >= h else (lambda s: s["fillH"])
    across = (lambda s: s["fillH"]) if w >= h else (lambda s: s["fillW"])
    long_best = max(stats.values(), key=along)
    short_best = max(stats.values(), key=across)
    long_fill, short_fill = along(long_best), across(short_best)
    fw, fh = long_best["fillW"], long_best["fillH"]
    if max(s["edgeCells"] for s in stats.values()) < 8:
        report.add("warn", fmt, "stage fill", "no clear content found in any frame")
    elif long_fill < 0.8 and short_fill < 0.9:
        side = "width" if w >= h else "height"
        report.add("warn", fmt, "stage fill", f"content spans at most {long_fill * 100:.0f}% of the {side} and "
                   f"{short_fill * 100:.0f}% across it; let the visual fill 80–95% of the {side}: re-lay the scene "
                   "for this format, don't shrink it")
    else:
        report.add("pass", fmt, "stage fill", f"content spans up to {fw * 100:.0f}% × {fh * 100:.0f}% of the stage")
    first = stats[0]
    if first["edgeCells"] < 8 and best["edgeCells"] >= 8:
        report.add("warn", fmt, "first frame", "the 0% frame is nearly empty. It is the poster/thumbnail on most "
                   "platforms and the moment the loop restarts; show the scene in it")

    # Text in the five frames.
    tfind = []
    for pct in PCTS:
        for msg in text_findings(frame_texts[pct], w, h):
            tfind.append(f"{pct}%: {msg}")
    seen, uniq = set(), []
    for m in tfind:
        core = m.split(": ", 1)[1]
        if core not in seen:
            seen.add(core)
            uniq.append(m)
    if uniq:
        for m in uniq[:8]:
            report.add("warn", fmt, "text", m)
    elif any(frame_texts[p] for p in PCTS):
        report.add("pass", fmt, "text", "inside the frame, line height ≥ 1.1, no one-word last lines")

    if not quick and any(frame_texts[p] for p in PCTS):
        step = 0.1
        sw, sh = max(160, w // 4), max(160, h // 4)
        samples = []
        for k in range(int(round(D / step))):
            r = await page.evaluate(f"([t, w, h]) => {chk}.draw(t, w, h, true)", [k * step, sw, sh])
            samples.append({x["text"].strip() for x in (r["texts"] or [])
                            if x["alpha"] >= 0.6 and x["role"] != "caption" and x["text"].strip()})
        for m in hold_findings(samples, step, D)[:6]:
            report.add("warn", fmt, "text hold", m)

    avg = statistics.mean(times)
    if avg > 40:
        report.add("warn", fmt, "render speed", f"{avg:.0f} ms per frame at {w}×{h}: the live preview may stutter "
                   "(exports are unaffected). Cache static layers with cached()")
    else:
        report.add("pass", fmt, "render speed", f"{avg:.0f} ms per frame at {w}×{h}")


SHEET_HTML = """<!doctype html><html><body style="margin:0;background:#111113;color:#bdbab3;font:15px sans-serif">
<div style="padding:14px 16px;font:600 20px sans-serif;color:#e8e6e1">{title}</div>
<div style="display:flex;gap:16px;padding:0 16px 16px;align-items:flex-start">{cells}</div></body></html>"""


async def page_shots(b, url, out_dir: Path, D: float, overrides, report):
    """--page: screenshot the real page (HTML text + live layers) at the five moments, desktop and phone."""
    import base64
    init = ("window.RISE_OVERRIDES = " + json.dumps(overrides) + ";") if overrides else None
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for name, vp, scale, thumb in (("desktop", (1440, 900), 1, 300), ("mobile", (390, 844), 2, 150)):
        page, errors = await _rise.new_page(b, viewport=vp, init_script=init, scale=scale)
        cells = []
        try:
            for pct in PCTS:
                t = D * pct / 100
                sep = "&" if "?" in url else "?"
                await page.goto(f"{url}{sep}t={t:.3f}", wait_until="load", timeout=90000)
                await page.evaluate("() => window.RISE && RISE.ready")
                await page.wait_for_timeout(250)
                shot = await page.screenshot(full_page=True, type="jpeg", quality=85)
                (frames_dir / f"page-{name}-{pct:03d}.jpg").write_bytes(shot)
                src = "data:image/jpeg;base64," + base64.b64encode(shot).decode()
                cells.append(f'<figure style="margin:0"><img src="{src}" style="width:{thumb}px;display:block;'
                             f'outline:1px solid #2a2a2e"><figcaption style="padding-top:6px">{pct}% · {t:.2f}s</figcaption></figure>')
            for e in dict.fromkeys(errors):
                report.add("fail" if e.startswith("uncaught") else "warn", f"page-{name}", "page", e[:300])
        finally:
            await page.context.close()
        sheet, _ = await _rise.new_page(b, viewport=(5 * thumb + 96, 400))
        try:
            await sheet.set_content(SHEET_HTML.format(title=f"Real page · {name} {vp[0]}×{vp[1]} · text over motion",
                                                      cells="".join(cells)))
            await sheet.wait_for_timeout(200)
            (out_dir / f"contact-page-{name}.jpg").write_bytes(await sheet.screenshot(full_page=True, type="jpeg", quality=88))
        finally:
            await sheet.context.close()
        report.add("pass", f"page-{name}", "page screenshots",
                   f"contact-page-{name}.jpg — judge the HTML text over the motion: contrast, overlap, "
                   "readable at every moment, nothing covers the button")


BY_EYE = """## By eye: open every contact sheet, then any full frame that looks off
1. Clipped letters: every g, j, p, q, y whole; line height ≥ 1.1
2. A word alone on a line: rewrite the line or tie the last two words
3. Empty stage: the visual fills 80–95% of the stage
4. Flat colour: light falls off across the frame
5. Linear motion: everything eases in and out (scrub the HTML to feel it)
6. Loop seams: last frame = first frame (the seam tile should be black)
7. Text held too short: every word readable ≥ 1.2 s
8. Fake logos: the real file, never a logo drawn from memory
9. Busy backgrounds: one idea on a quiet ground
10. No texture: real grain and subtle noise
Plus the style's own checks from references/styles.md, and the brief: does it show the one change?
"""


async def main_async(args):
    html = Path(args.file).resolve()
    if not html.exists():
        raise _rise.RiseError(f"no such file: {html}")
    root, rel = _rise.motion_url_parts(html, Path(args.root) if args.root else None)
    out_dir = Path(args.out).resolve() if args.out else html.parent / "checks"
    out_dir.mkdir(parents=True, exist_ok=True)
    overrides = _rise.build_overrides(args.brand, args.theme, _rise.parse_params(args.param))
    report = Report()
    started = time.time()

    with _rise.serve(root) as base:
        async with _rise.browser() as b:
            page, errors, info = await _rise.open_motion(b, f"{base}/{rel}", overrides)
            await page.evaluate(CHECK_JS)
            formats = [f.strip() for f in args.formats.split(",")] if args.formats else list(info["FORMATS"])
            if args.quick:
                formats = formats[:1]
            title = info.get("title") or html.parent.name
            report.add("pass", "all", "contract", f"RISE.render found · {info['DURATION']:.2f}s loop · {info['FPS']} fps · "
                       f"formats {', '.join(formats)}")
            sizes = {}
            for fmt in formats:
                w, h = _rise.size_for(fmt, info, args.size if len(formats) == 1 else None)
                sizes[fmt] = [w, h]
                await check_format(page, fmt, w, h, info, out_dir, report, title, quick=args.quick)

            counts = await page.evaluate("() => window.__riseCheck.counts")
            if counts["random"]:
                report.add("fail", "all", "purity", f"render called Math.random() {counts['random']}× — use hash(i, seed) "
                           "so every frame is reproducible")
            if counts["clock"]:
                report.add("fail", "all", "purity", f"render read the clock {counts['clock']}× (Date.now/performance.now) "
                           "— derive everything from t")
            if not counts["random"] and not counts["clock"]:
                report.add("pass", "all", "purity", "no Math.random or clock reads inside render")

            fonts = await page.evaluate("() => window.__riseCheck.fonts()")
            bad = [f for f in fonts if not f["ok"]]
            for f in bad:
                report.add("fail", "all", "fonts", f"{f['font']}: {f['how']}")
            good = sorted({f["family"] for f in fonts if f["ok"] and f["how"] != "generic family"})
            if not bad:
                report.add("pass", "all", "fonts", ("loaded: " + ", ".join(good)) if good else "no webfonts used")
            for e in dict.fromkeys(errors):
                report.add("fail" if e.startswith("uncaught") else "warn", "all", "page", e[:300])
            if args.page:
                await page_shots(b, f"{base}/{rel}", out_dir, info["DURATION"], overrides, report)

    fails, warns = report.failures(), report.warnings()
    verdict = "FAIL" if fails else "PASS"
    summary = f"{verdict}: {len(fails)} failure(s), {len(warns)} warning(s)"
    icon = {"pass": "✔", "warn": "⚠", "fail": "✘"}
    md = [f"# Frame check · {html.name}", "",
          f"{datetime.now():%Y-%m-%d %H:%M} · {html} · {info['DURATION']:.2f}s loop · {info['FPS']} fps · "
          f"{time.time() - started:.1f}s to check", "", f"**{summary}**", ""]
    groups = ["all"] + list(sizes) + (["page-desktop", "page-mobile"] if args.page else [])
    for fmt in groups:
        rows = [i for i in report.items if i["format"] == fmt]
        if not rows:
            continue
        if fmt == "all":
            md.append("## Whole piece")
        elif fmt.startswith("page-"):
            md.append(f"## Real page · {fmt[5:]}")
        else:
            w, h = sizes[fmt]
            md.append(f"## {fmt} · {w}×{h} · contact-{_rise.fmt_slug(fmt)}.jpg")
        md += [f"- {icon[i['level']]} {i['check']}: {i['detail']}" for i in rows]
        md.append("")
    md.append(BY_EYE)
    (out_dir / "report.md").write_text("\n".join(md))
    (out_dir / "report.json").write_text(json.dumps({"verdict": verdict, "file": str(html), "formats": sizes,
                                                     "duration": info["DURATION"], "items": report.items}, indent=2))

    print(summary)
    for fmt in groups:
        rows = [i for i in report.items if i["format"] == fmt and i["level"] != "pass"]
        for i in rows:
            print(f"  {icon[i['level']]} [{fmt}] {i['check']}: {i['detail']}")
    sheets = [str(out_dir / f"contact-{_rise.fmt_slug(f)}.jpg") for f in sizes]
    if args.page:
        sheets += [str(out_dir / f"contact-page-{n}.jpg") for n in ("desktop", "mobile")]
    print("contact sheets: " + ", ".join(sheets))
    print(f"full frames:    {out_dir / 'frames'}")
    print(f"report:         {out_dir / 'report.md'}")
    print("next: open each contact sheet and walk the ten tells (report.md lists them).")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="the motion HTML file")
    ap.add_argument("--formats", help="comma list, e.g. 16:9,9:16 (default: the file's FORMATS)")
    ap.add_argument("--size", help="WxH override (only with a single format)")
    ap.add_argument("--out", help="output folder (default: checks/ next to the file)")
    ap.add_argument("--root", help="folder to serve (default: the file's folder)")
    ap.add_argument("--brand", help="brand.json (or its folder) to inject: theme, name, logo")
    ap.add_argument("--theme", help='JSON merged into THEME, e.g. \'{"accent": "#ff3b1f"}\'')
    ap.add_argument("--param", action="append", help="KEY=VALUE merged into PARAMS (repeatable)")
    ap.add_argument("--quick", action="store_true", help="first format only, skip the text-hold sampling")
    ap.add_argument("--page", action="store_true",
                    help="also screenshot the real page (HTML text over the live layers) on desktop and phone; "
                         "use for website heroes built from hero-template.html")
    args = ap.parse_args()
    sys.exit(_rise.run(main_async(args)))


if __name__ == "__main__":
    main()
