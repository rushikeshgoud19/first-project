# Canvas craft

Techniques for the effects that come up again and again, written for the template's helpers
(`seg`, `ease`, `wave`, `hash`, `noise`, `fbm`, `loopNoise`, `stage`, `cached`, `surface`, `ground`,
`grain`, `falloff`, `vignette`, `fontOf`, `fitSize`, `lines`, `readable`, `mix`, `rgba`).
Everything here keeps `render(t)` pure.

**Contents:** [Timing](#timing) · [Paths](#paths) · [Masks and reveals](#masks-and-reveals) ·
[Type](#type) · [Texture and light](#texture-and-light) · [Blend modes](#blend-modes) ·
[Particles](#particles) · [Brush strokes](#brush-strokes) · [Paper, shadows, depth](#paper-shadows-depth) ·
[Print looks](#print-looks) · [Images and logos](#images-and-logos) · [Layout across formats](#layout-across-formats) ·
[Performance](#performance)

---

## Timing

- **Windows**: `seg(t, a, b)` gives 0→1 progress over [a, b] seconds. Ease it:
  `ease.outQuint(seg(t, 1.2, 1.9))`.
- **In, hold, out** (returns to 0, so it loops): `ease.out(seg(t, a, b)) * (1 - ease.inOut(seg(t, c, d)))`.
- **Up then back**: `ease.inOut(seg(t, a, b)) - ease.inOut(seg(t, c, d))`.
- **Stagger**: element `i` starts at `t0 + i * 0.06`. Sort indices by position (left to right,
  centre out) for an ordered wave.
- **Periodic**: `wave(t, n, offset)` completes `n` whole cycles per loop. Use integer `n`, or the
  seam pops.
- **Organic drift that loops**: `loopNoise(t, seed)` walks a circle through noise space.
- **Beats**: pick a tempo, e.g. `beat = 60 / 96`, and put events at `k * beat`. Snappy styles move
  in 300–450 ms, then freeze.
- **Stepped / on twos**: `stepped(t, 12)` quantises time to 12 fps for print or stop-motion looks.
- **Overshoot**: `ease.outBack` for pops (scale 0.85 → 1). Keep it for small elements; big planes
  overshooting look cheap.

## Paths

- **Draw a path by length** (a line inking on):
  ```js
  const pts = [...];                                   // polyline
  const lens = [0]; for (let i = 1; i < pts.length; i++) lens.push(lens[i-1] + Math.hypot(pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1]));
  const L = lens[lens.length - 1] * k;                 // k = eased progress
  ctx.beginPath(); ctx.moveTo(...pts[0]);
  for (let i = 1; i < pts.length; i++) {
    if (lens[i] <= L) ctx.lineTo(...pts[i]);
    else { const f = (L - lens[i-1]) / (lens[i] - lens[i-1]); ctx.lineTo(lerp(pts[i-1][0], pts[i][0], f), lerp(pts[i-1][1], pts[i][1], f)); break; }
  }
  ctx.stroke();
  ```
- **Any shape by dash**: `ctx.setLineDash([len, len]); ctx.lineDashOffset = len * (1 - k)`. For
  `Path2D` you need the length, which the SVG snippet gets from `getTotalLength()` during PRELOAD.
- **Smooth curves through points**: Catmull–Rom converted to `bezierCurveTo`, or `quadraticCurveTo`
  through midpoints.

## Masks and reveals

- **Rise out of a baseline**: `ctx.save(); ctx.beginPath(); ctx.rect(x, y - size * 1.3, w, size * 1.6); ctx.clip();`
  then draw at `y + (1 - k) * size * 1.2`. Leave ~0.3 em below the baseline for descenders.
- **Wipe**: clip to a rect whose width is `w * k`, or to a rotated rect for a diagonal wipe.
- **Circle reveal**: clip to `arc(cx, cy, R * k, 0, TAU)`.
- **Knockout text** (carved, stamped): draw on an offscreen canvas, then
  `globalCompositeOperation = 'destination-out'` and `fillText`.
- **Reveal by light**: draw the dark version, then clip to a moving band and draw the lit version.

## Type

- Load every face you set: add it to `FONTS` (e.g. `'800 120px "Inter"'`) and to the Google Fonts
  `<link>`. `check.py` fails pieces that fall back.
- **Size to fit**: `fitSize(ctx, text, maxWidth, maxPx, weight, family)`.
- **Wrap without orphans**: `lines(ctx, text, maxWidth)`. Line height ≥ 1.1 × size (1.2 is safe).
- **Tracking**: `ctx.letterSpacing = (-0.02 * px) + 'px'` (−2%). Reset it to `'0px'` afterwards.
- **Per-letter animation**: measure each glyph (`measureText(ch).width`) once per size in a cached
  layout, then draw letter by letter. Kerning is lost per glyph; that's acceptable at display sizes.
- **Variable weight**: `ctx.font = \`${Math.round(w)} ${px}px "Inter"\``. Any 1–1000 value works with
  a variable font loaded as `family=Inter:wght@100..900`.
- **Optical sizes**: Newsreader and other opsz fonts pick the optical size from the pixel size.
- **Readable colour**: `readable(bg, ink, '#ffffff', '#111111')` picks the highest contrast.
- **Real text in heroes**: on web pages, headline, subline and buttons are HTML. Canvas is the layer
  behind them.

## Texture and light

- **Ground**: `ground(ctx, w, h, theme.bg, { seed, mottle, fibres })` gives cached paper (base fill,
  soft mottling, fibres).
- **Light**: `falloff(ctx, w, h, angleDeg, strength)` for light falling across the frame;
  `vignette(ctx, w, h, 0.2–0.35)` for the edges.
- **Grain**: `grain(ctx, w, h, t, amount, { fps: 15, size: 2 })` is last in the frame. Around 0.06
  on light grounds and 0.08–0.12 on dark ones. 2 px grain re-rolling at 15 fps looks like film and
  keeps MP4s small; 1 px grain at 30 fps triples the file size.
- **Halftone**: a dot grid whose radius follows the tone. Sample a cached offscreen tone map and draw
  circles.
- **Chalk / smudge**: large radial gradients at 2–5% alpha, plus `hash`-placed dust specks.
- **Glow**: draw the element blurred (`ctx.filter = 'blur(20px)'`) at low alpha under the sharp
  version. Set `filter = 'none'` afterwards (save/restore also does).

## Blend modes

`ctx.globalCompositeOperation`:
- `screen`: inks on dark stock, light leaks, glows (overlaps get lighter).
- `multiply`: ink on paper, shadows, riso on white (overlaps get darker).
- `overlay` / `soft-light`: texture that keeps the underlying colour.
- `source-atop`: texture or gradient only where something is already drawn (paper grain on a shape).
- `source-in`: tint a white plate to an ink colour.
- `destination-out`: carve holes (knockouts, dropout specks).
Always wrap mode changes in `save()`/`restore()`.

## Particles

- A particle is an index `i`. Everything about it comes from `hash(i, k)` and `t`:
  `life = (phase(t) * n + hash(i, 1)) % 1` gives `n` staggered lives per loop that wrap seamlessly.
- Position = spawn + a function of `life` (rise, sway with `Math.sin(TAU * (life * c + hash(i, 2)))`).
  Fade with `Math.sin(Math.PI * life)`.
- **Flocks and letters**: sample target points from text or a logo drawn on a cached offscreen
  canvas (every Nth opaque pixel). Particles ease from a scattered state to the targets and breathe
  with `loopNoise`.
- **Interactive layers** (heroes) take `input = { x, y, clicks: [{ x, y, age }] }` as an argument, so
  pointer effects stay pure. See `interact()` in hero-template.html.

## Brush strokes

- Sample the stroke's centreline (a circle, a Bézier) at 150–300 points.
- Pressure profile `p(s)`: fast rise, a slow decline, a drop at the tail. Width = `p(s) * W`.
- Offset left and right edges along the normals, then fill the polygon up to the progress point.
- Dry brush: in the last third, split into bristle sub-strokes and skip segments where
  `noise(s * 12, k) < 0.45`.
- Speed: slow at both ends and fast in the middle (`ease.inOut` on progress). Where the brush moves
  fast the ink is thinner, so drop alpha slightly there.
- Bleed and bloom: stamp soft radial gradients along the stroke, larger where it was wet. Draw the
  tide line as a thin, lighter noisy outline at the bloom's edge.

## Paper, shadows, depth

- Cut-paper layers: fill back to front with `shadowColor`, `shadowBlur`, `shadowOffsetY`. Stroke a
  thin light line along each top edge.
- Atmospheric perspective: `mix(nearColour, skyColour, depth)`, lighter and bluer with distance.
- Parallax: layer speed ∝ 1/depth; alternate directions for a paper-theatre feel; whole wavelengths
  per loop.
- Irregular edges: jitter points with `hash` indexed by world position, so the jitter scrolls with
  the layer and still loops.

## Print looks

- **Risograph**: each ink is its own plate (white shapes, then tinted with `source-in`). Punch
  dropout specks with `destination-out`, composite plates with `screen` on dark stock or `multiply`
  on paper, jitter one plate's offset each printed frame (`stepped(t, 12)`).
- **Halftone**: see Texture. Rotate each plate's grid (15°, 45°, 75°).
- **Registration marks**: a crosshair circle in each corner, in every ink, slightly offset.

## Images and logos

- Put real files next to the piece and list them in `ASSETS` (or `BRAND.logo`), which loads them
  before the first frame into `IMAGES.name`.
- `drawContain(ctx, img, x, y, w, h)` fits an image into a box, keeping its aspect.
- Logo parts for animation: `snippets/svg-logo.js` (`loadLogoParts` in `PRELOAD`, then `drawLogo`).
- Contrast plates: if `contrast(logoMainColour, bg) < 3`, put the logo on a rounded plate in
  `readable(bg, '#ffffff', '#111111')`.

## Layout across formats

- `const S = stage(w, h)` gives `S.u`, `S.portrait`, `S.square`, `S.landscape`, `S.safe` and the
  centre.
- Decide the arrangement per format, don't scale one layout: rows in 16:9, stacks in 9:16, arcs or
  grids in 1:1.
- Size everything in `u`: strokes (`3 * u`), type (`96 * u`), offsets. Clamp type with `fitSize` to
  the safe width.
- Keep critical content inside `S.safe`. Social apps overlay UI on the bottom ~15% of a 9:16 frame
  and the right edge.

## Performance

- Target < 30 ms per frame at 1080p for a smooth preview (`check.py` reports it). Exports are not
  affected by speed.
- Cache anything that doesn't change with `t`: paper, text layouts, glyph widths, sampled points,
  static layers.
- Avoid `ctx.filter` blur on large areas every frame. Blur once into a cached layer.
- Batch same-coloured particles into one path (`moveTo`/`arc` per particle, then a single `fill()`).
