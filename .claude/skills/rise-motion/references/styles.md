# Six styles

Each style is a complete **S** for a RISE brief: what it looks like, how its loop moves, the rules
that keep it honest, the checks to run by eye on top of `check.py`, and notes on building it in
canvas. The looks and timings follow the six styles in Jack Roberts' *Motion, drawn in code* guide,
restated here as specs. Swap in the user's word, numbers and brand colours. The structure is what
matters.

All six are 5-second loops unless the brief says otherwise, built from one
`render(ctx, t, theme, w, h)` with `theme = {bg, ink, accent, accent2, font}`, and must work at
16:9, 9:16 and 1:1.

**Contents:** [01 Field Notes chart](#01--field-notes-chart) · [02 Charcoal Caliper](#02--charcoal-caliper) ·
[03 Swiss kinetic type](#03--swiss-kinetic-type) · [04 Sumi ink bloom](#04--sumi-ink-bloom) ·
[05 Paper-cut layers](#05--paper-cut-layers) · [06 Risograph two-colour](#06--risograph-two-colour)

---

## 01 · Field Notes chart

An editorial chart slide on real paper, floating on a night sky. A warm beam passes over it and the
data wakes up as the light touches it.

**Looks**
| role | value |
|---|---|
| ground (`bg`) | `#07080c` night, with a dawn-coloured rim glowing along the bottom edge |
| slide | ivory paper with tooth, a soft drop shadow and light falling across it |
| `ink` | bars and title in the night colour, drawn on the ivory slide |
| `accent` | `#d97757` clay: the last, tallest bar only, plus a short rule above the title |
| `accent2` | `#e3b23c` ochre: a torn paper scrap in a corner carrying a small ink sketch (a compass) |
| type | Newsreader 500 at optical size 36, for example the title "Numbers that move" |

**Moves** (5 s)
- 0–1.8 s: a soft clay beam sweeps left to right across the slide (1.6 s, ease-in-out). Each bar
  starts rising only when the beam reaches it, easing out over 0.8 s.
- 1.8–3.9 s: an ink trend line draws itself through the bar tops, with a clay nib resting on the
  tallest bar. Round dots land on each top after its bar has risen.
- 3.9–5 s: bars settle back to the baseline one after another (60 ms apart) and the slide waits for
  the next sweep.

**Rules**
1. The slide is paper, never a flat rectangle: texture, shadow, falloff.
2. No bar moves before the beam reaches it.
3. Exactly one clay bar, the tallest and last one. Everything else is ink.
4. The trend line draws after the bars have landed, with round dots on the tops.
5. Grain and a vignette over the whole frame.

**Check by eye**: no bar rises before the beam; the trend line meets every bar top; the title never
clips; the slide never touches the frame edge in any format.

**Build notes**
- Draw the slide into a `cached()` surface (paper via `ground()`, rounded corners) and composite it
  each frame with `shadowBlur`/`shadowOffsetY`. Only the beam, bars and line change.
- Beam: a wide linear gradient band (transparent → clay at ~0.25 alpha → transparent), clipped to
  the slide. Its x is `lerp(left, right, ease.inOut(seg(t, 0.1, 1.7)))`.
- Bar `k` starts at `tk = 0.1 + 1.6 * (barCenterX - left) / (right - left)` and its height is
  `hk * ease.out(seg(t, tk, tk + 0.8))`, multiplied by `1 - ease.inOut(seg(t, 3.9 + k*0.06, 4.5 + k*0.06))` for the settle.
- Trend line: build the polyline through the tops, measure cumulative length, and draw up to
  `L * ease.inOut(seg(t, 1.8, 3.2))` (see canvas-craft.md, "draw a path by length").
- Torn scrap: a polygon whose edge points are jittered with `hash()`, filled ochre, with texture.
- Dawn rim: a wide, flat radial gradient centred below the bottom edge.
- 9:16: stack the title above a taller, narrower slide. 1:1: shrink the gutter, not the bars.

---

## 02 · Charcoal Caliper

The grammar of a documentary explainer: a smudged chalkboard, heavy white type, a yellow measuring
bracket and one handwritten orange flourish. It builds in beats, then holds dead still, then cuts.

**Looks**
| role | value |
|---|---|
| `bg` | `#0d0d0d` charcoal board with chalk smudges and dust: never flat |
| `ink` | `#f4f1ea` chalk white. Heavy grotesque (Plus Jakarta Sans ExtraBold), Title Case |
| bars | translucent chalk-white fills with a 2 px chalk outline |
| `accent` | `#f5e918` yellow caliper (the measuring bracket) |
| `accent2` | `#f0862b` orange, used once as a cursive swash under one title word |

**Moves** (5 s, hard cut at the loop)
- 0–1.4 s: the title (e.g. "Design In Motion") sits on the board. A baseline draws, then three bars
  rise, one per beat.
- 1.4–3.1 s: the caliper draws up the tallest bar (400 ms). 80 ms later the stat ("3×") pops beside
  it: scale 0.85 → 1 with a back-ease and no fade. The orange swash writes itself under one title
  word (450 ms).
- 3.1–5 s: a dead hold of at least 1.5 s, then a single-frame hard cut back to the title alone.
- Throughout: each build takes 300–450 ms with a quint-out ease and then freezes. The whole plate
  pushes in slowly to 1.05.

**Rules**
1. Two type sizes only: a label size and a stat 2.6× bigger.
2. Title Case, white, heavy. Never all caps, never coloured type.
3. The caliper spans exactly the bar's full height: ticks face the bar, the tab faces the stat.
4. Accents are strokes only, tiny in area, two at most. No rings, circles or ellipses anywhere.
5. The board's luminance varies a little everywhere.
6. Dead hold, then a hard cut. No crossfade.
7. Borrow the grammar, never a real network's logos or marks.

**Check by eye**: only two type sizes; the bracket ends exactly at the bar top and the baseline; the
stat sits vertically centred on the tab; the swash sits under one word only. `check.py` will warn
about a jump at the loop point, which is the intended hard cut: keep it and say so.

**Build notes**
- Board: `ground(ctx, w, h, '#0d0d0d', { mottle: 0.12 })`, plus 6–10 large soft white radial blobs
  at 2–4% alpha for smudges and a few hundred `hash`-placed dust specks, all in a `cached()` layer.
- Pops: `s = 0.85 + 0.15 * ease.outBack(seg(t, t0, t0 + 0.3))`. Scale around the element's centre.
- Swash: a cubic Bézier path stroked with round caps and drawn on by dash offset. Taper it by
  stroking twice (a wide low-alpha pass, then a narrow opaque one), or build a filled ribbon.
- Push-in: `ctx.translate(cx, cy); ctx.scale(k, k); ctx.translate(-cx, -cy)` with
  `k = 1 + 0.05 * ease.inOut(seg(t, 0, 3.1))`. It resets at the cut.
- The hard cut means `t` in 4.9–5.0 shows the full build and `t = 5` equals `t = 0` (title only).
  That's still a valid loop, because frame 0 matches frame 5.

---

## 03 · Swiss kinetic type

International Typographic Style: one enormous word on a strict grid, hairline rules, a single red
disc. The motion is in the type's **weight**, a wave rolling through the letters.

**Looks**
| role | value |
|---|---|
| `bg` | `#0f0f0e` near-black |
| `ink` | `#f1eee7` type and hairlines |
| `accent` | `#ff3b1f` one red disc, the only colour |
| type | Inter (variable, 100–900), tracking −2%, flush left on a 12-column grid, generous margins; tiny captions in the same family |

**Moves** (5 s)
- 0–1.3 s: an empty grid and the red disc. The word ("Motion") rises letter by letter out of a mask
  on the baseline, 60 ms apart, quint-out.
- 1.3–3.9 s: the word holds while a sine weight wave (260 → 860) travels through the letters, two
  full waves per loop. The disc steps to a new grid point on each beat (0.7 s moves).
- 3.9–5 s: the letters lift out through the top of the mask, the rule retracts, and the frame is
  back to the empty grid.

**Rules**
1. Everything sits on the grid: columns, baseline, margins.
2. One word, filling about 85% of the grid width.
3. The disc is the only colour.
4. Letters enter from a baseline mask, staggered, and leave the same way, upward.
5. Weight is the motion. Positions change only on entrances and exits.
6. Grain and a soft light falloff, so the ground is never flat.
7. The full word holds for at least 1.2 s.

**Check by eye**: no letter clipped (watch the mask edges at the hold); the disc lands exactly on grid
points; captions never collide with the word; the weight wave reads as one smooth wave, not a
flicker.

**Build notes**
- Load the variable range: `family=Inter:wght@100..900` in the Google Fonts link and a font spec
  per extreme in `FONTS`. Canvas accepts any numeric weight: `ctx.font = \`${wgt} ${px}px "Inter"\``.
- Size the word so that at weight 860 it fills the run (~86% of the grid). Lay the letters out
  cumulatively each frame (`x += measureText(ch).width - 0.02 * px` for −2% tracking) from a fixed
  flush-left edge: the word breathes at its far end as the wave passes, which reads as weight, not
  as sliding. (Fixed slots measured at 860 also work but leave gaps at light weights.)
- Weight of letter i: `560 + 300 * Math.sin(TAU * (2 * t / DURATION) - i * 0.55)`. It completes whole
  cycles, so it loops.
- Don't draw a letter while the mask hides it completely. It saves time and keeps `check.py`'s
  text checks accurate (they can't see clip regions).
- 9:16: run the word up the long side (`ctx.rotate(-Math.PI / 2)` around the bottom-left of the
  grid) rather than shrinking it. Keep captions horizontal.
- Mask: `ctx.save(); ctx.beginPath(); ctx.rect(x, top, w, baseline - top); ctx.clip();` then draw each
  letter at `baseline + (1 - ease.outQuint(seg(t, ti, ti + 0.5))) * px` on the way in.
- Grid: compute 12 columns inside `stage().safe`, with rows on a baseline unit. Snap the disc to
  intersections and move it with `ease.inOut` over 0.7 s.
- 1:1: the word fills the width and the disc takes the top band.
- Frame 0 falls in the empty-grid moment. Offset the phase (`t = wrap(time + 2.2)`) so the poster
  frame shows the full word mid-wave.

---

## 04 · Sumi ink bloom

One ensō (a single brushed circle) in luminous ink on dark wet paper. It bleeds into a soft halo
with a tide-line edge and is sealed with a vermilion stamp. It all happens in one breath.

**Looks**
| role | value |
|---|---|
| `bg` | `#0d0c0b` paper with visible fibres and mottling |
| `ink` | `#ede6d8` luminous ink |
| `accent2` | `#7f93a8` cool bloom colour |
| `accent` | `#d8432f` small vermilion seal with the initial carved out (Newsreader) |
| space | generous emptiness around one circle |

**Moves** (5 s)
- 0–1.9 s: a loaded brush lands, sweeps one circle (slow in, fast through the middle, slow out,
  about 1.6 s), and splits into dry bristles at the tail.
- 1.9–3.9 s: the ink bleeds outward into the paper, and the seal (carrying the word's initial)
  stamps down once, hard.
- 3.9–5 s: the ink dries back to a faint ghost of the circle, which is also the first frame.

**Rules**
1. One stroke, drawn as a filled shape whose width follows brush pressure: a pressed blob at the
   start, a dry split tail.
2. Dry-brush gaps (thin streaks of paper showing through) only in the last third.
3. The bloom is a soft wash plus a brighter tide-line rim at its edge, driven by noise. Never a
   plain blur.
4. More bleed where the brush was wet (the start), less at the dry tail.
5. A few spatter dots flicked out where the brush lands.
6. The seal is the only colour and stamps once.
7. Paper texture, falloff and grain in every frame.

**Check by eye**: the stroke width really tapers; the bloom has a rim; the seal letter is crisp and
unclipped; the ghost at 0% matches the final dried state at 100%.

**Build notes**
- Stroke: sample the circle path at ~240 points. Pressure `p(s)` is high at the start, eases down
  and drops at the tail; width = `p(s) * 38u`. Build left and right offset edges from the path
  normals and fill the polygon up to the current progress `ease.inOut(seg(t, 0.2, 1.8))`.
- Dry brush: in the last third, draw 6–10 thin sub-strokes offset across the width, and skip
  segments where `noise(s * 12, k) < 0.45`.
- Bloom: a cached field. For points along the stroke, stamp radial gradients whose radius grows with
  `ease.out(seg(t, 1.9, 3.5))` and is larger where pressure was high. Draw the rim by stroking a
  noise-perturbed offset of the circle in a lighter tone, with low alpha and a thin line.
- Seal: a rounded square in vermilion. Carve the letter with `globalCompositeOperation =
  'destination-out'` on a small offscreen canvas, then scale it in with 1.2 → 1 over 0.25 s.
- Dry-back: the stroke's alpha eases to about 0.12 over 3.9–5 s. Draw the same 0.12-alpha ghost at
  t = 0, so the seam is invisible.

---

## 05 · Paper-cut layers

A quiet night at sea built from stacked cut paper: six wave layers casting real shadows, a layered
paper moon and a folded paper boat.

**Looks**
| role | value |
|---|---|
| `bg` | `#0e1016` night |
| layers | graded from `#4f7396` (far, lighter and bluer) to near-black (near); each with a soft drop shadow and a thin lit top edge |
| `accent` | `#f2a541` moon with two paper rings, the only accent |
| `accent2` | `#f2e8d8` paper boat and two birds |
| texture | paper fibre on everything |

**Moves** (5 s)
- 0–1.5 s: six layers roll under the moon; the folded boat rides the second wave.
- 1.5–3.5 s: the boat lifts and tips on a swell, two birds glide across, stars wink.
- 3.5–5 s: the swell settles and every layer lands exactly where it began.

**Rules**
1. Every layer casts a shadow onto the layer behind it.
2. Farther layers are lighter and bluer (atmospheric perspective in paper).
3. Scissor-cut edges: slightly irregular, never perfect curves.
4. A thin light catches each layer's top edge.
5. Parallax: layers move at different speeds, in alternating directions.
6. One accent, in the moon.

**Check by eye**: every layer shows a shadow; the boat sits on its wave (never floating or sunk); no
edge looks machine-perfect; the paper texture is visible at full size.

**Build notes**
- Layer k's top edge: `y(x) = base_k + Σ a_j sin(2π (n_j x / w + dir_k * m_k * t / DURATION) + φ_j)`
  with integer `n_j` and `m_k`, so each layer scrolls a whole number of wavelengths per loop.
- Scissor jitter that still loops: add `(hash(floor((x + offset_k) / 18u), k) - 0.5) * 3u`, where
  `offset_k` is the layer's scroll in px, which is a whole wavelength multiple at t = DURATION.
- Shadows: fill each layer with `ctx.shadowColor = 'rgba(0,0,0,0.45)'`, `shadowBlur = 18u`,
  `shadowOffsetY = -6u`, from back to front. Then stroke the top path with a 1.5u light line at
  ~0.35 alpha for the lit edge.
- Paper texture: fill each layer's path, then `ctx.globalCompositeOperation = 'source-atop'` and draw
  a cached fibre texture over it (on an offscreen canvas per layer), or clip to the path and draw
  `ground()` tinted.
- Boat: sample the wave height at the boat's x and its slope from `y(x+1) - y(x-1)`; rotate by
  `atan2(slope, 2)`.
- Stars: `hash`-placed dots whose alpha follows `0.5 + 0.5 * wave(t, 1 + (i % 3), hash(i, 9))`.

---

## 06 · Risograph two-colour

A zine print in motion: two fluorescent spot inks on black stock, a striped sun, a giant condensed
marquee, grain, dropout and misregistration, printed at 12 frames a second.

**Looks**
| role | value |
|---|---|
| `bg` | `#111111` black stock with fibres |
| `accent` | `#ff48b0` fluorescent pink (plate 1) |
| `accent2` | `#1f9bd1` blue (plate 2) |
| type | Anton, set huge and condensed, e.g. the word "Print" |
| details | registration marks in the corners |

**Moves** (5 s, stepped at 12 fps)
- 0–1.5 s: a striped sun sits low in the frame while the giant marquee starts sliding across it.
- 1.5–3.5 s: the sun rises through the marquee; where the inks overlap they screen into a third
  colour; a small second marquee runs the other way.
- 3.5–5 s: the sun sets to where it began, and both marquees land exactly one repeat along.

**Rules**
1. Exactly two inks. Overlaps screen into a third colour.
2. Every ink layer prints imperfectly: dropout speckles and uneven density.
3. One plate sits slightly out of register and jitters each printed frame.
4. Animate on twos: 12 printed frames a second, with fresh grain each frame.
5. Stripes or grain stand in for gradients.

**Check by eye**: exactly two inks plus their overlap; the grain shows at full size; the marquee wraps
without a jump; the misregistration is subtle (a fraction of a percent of the width), not broken.

**Build notes**
- Time: `const ts = stepped(t, 12)`, and use `ts` everywhere instead of `t`. At t = DURATION it
  returns 0.
- Plates: draw each plate's shapes in white on its own cached-size offscreen canvas. Tint it with
  `globalCompositeOperation = 'source-in'` and a fill of the ink colour. Punch dropout with
  `destination-out` specks placed by `hash(i, frameOf(t, 12))`. Composite both plates onto the
  stock with `ctx.globalCompositeOperation = 'screen'`.
- Misregistration: offset plate 2 by `(hash(f, 1) - 0.5) * 0.004 * w` and `(hash(f, 2) - 0.5) *
  0.004 * h`, where `f = frameOf(t, 12)`.
- Marquee: the offset is `(ts / DURATION) * repeatWidth`. Draw the word enough times to cover the
  width plus one repeat, so it wraps seamlessly.
- Striped sun: a circle clipped to horizontal stripes whose thickness grows toward the bottom.
- Grain: `grain(ctx, w, h, t, 0.12, { fps: 12, size: 2 })`, re-rolled per printed frame.
