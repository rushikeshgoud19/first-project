---
name: rise-motion
description: Make motion graphics drawn in code (animated slides and charts, logo reveals with jingles, kinetic type, looping backgrounds, living website heroes, reel graphics with word-timed captions, B-roll in 16:9/9:16/1:1, batches of branded films) as one HTML canvas file driven by a single render(t) function, using the RISE method (References, Idea, Style, Examine). Pulls a site's real logo, colours and fonts with Claude's own web scraping (no Firecrawl, no API keys), checks frames at 0/25/50/75/100% automatically and by eye, and exports MP4/GIF. Use it whenever someone wants something to move or animate, e.g. a motion graphic, animated logo, intro, loop, explainer, animated chart, reel graphic, captions, "make this slide move", "bring our homepage hero to life", films for a list of sites, or mentions RISE, render(t), Claude Design animations or Jack Roberts' motion method, even if they never say "motion graphics".
compatibility: Python 3.9+. Checks and exports need Chrome/Chromium plus `pip install playwright imageio-ffmpeg` (scripts/doctor.py verifies the machine). Brand scraping runs on the standard library; a browser adds computed styles, a logo raster and a screenshot.
---

# RISE motion: motion graphics drawn in code

A piece is one HTML file with one pure function, `render(ctx, t, theme, w, h)`, that paints any
moment `t` of a seamless loop. Because every frame is a function of `t`, the piece previews live in
a browser, scrubs exactly, re-lays itself for any format, and exports frame-perfect video.
RISE is how you write it well: **References, Idea, Style, Examine**. The method comes from Jack
Roberts' free guide *Motion, drawn in code*; this skill runs it in Claude Code, with Claude's
own scraping in place of Firecrawl and scripts that do the checking and exporting.

`<skill>` below means this skill's folder (the directory holding this SKILL.md). Run commands from
the user's project so the output lands there.

## What you deliver

```
motion/<slug>/
  index.html   the piece: opens in any browser; scrub bar, format buttons (keys 1–3), space pauses
  brief.md     the RISE brief it was built from
  brand/       scraped brand files, when a website was involved
  checks/      contact sheets per format, full frames, report.md
  exports/     <slug>-16x9.mp4 … plus poster PNGs (only when video is wanted)
```

## Once per machine or cloud session

```bash
python <skill>/scripts/doctor.py
```

It checks Python, Playwright, a Chrome/Chromium, Google Fonts reachability and ffmpeg with H.264,
and prints the exact fix for anything missing (usually `pip install playwright imageio-ffmpeg`).
HTTPS proxies (corporate networks, Claude Code cloud sessions) are handled for you.

## The workflow

### R · References: start from something real

Motion invented from nothing looks generic. Motion built from the user's real material looks like
theirs. Gather these before inventing anything:

- **Files the user gave** (slide screenshot, reference image, clip, logo): look at them with your
  image viewer and note exact colours, type and composition. Copy them into `motion/<slug>/ref/`
  so the piece can load them.
- **A website or brand**: scrape it with Claude's own tools, with no Firecrawl and no key:
  ```bash
  python <skill>/scripts/brand_scrape.py https://site.com --out motion/<slug>/brand
  ```
  You get `brand/<site>/brand.json` (name, headline copy, a `theme` of bg/ink/accent/accent2/font,
  the palette with evidence, fonts with Google Fonts stand-ins for proprietary faces) plus the real
  logo as `logo.png` (transparent) and `logo.svg` when the site has one, `icon.png` and
  `screenshot.jpg`. Open the screenshot and logo before trusting the numbers, and read the
  `warnings`. If the script can't reach the site (network policy, bot wall), use the WebFetch
  fallback in [references/brand-scraping.md](references/brand-scraping.md).
- **A style reference** (a Savee/Pinterest/Dribbble image): take its style, not its picture. Write
  down its palette, type, texture and composition, and how it would move, then build from that.
- **Logos**: only ever the real file, from the scrape or the user. Never draw a logo from memory.
  An almost-right logo is worse than none.

### I · Idea: one image, one change

A good loop is one image with a beginning, a middle and an end: what we see first, the one thing
that changes, and how it lands. The last frame equals the first. Write it as a timeline in seconds, e.g.
`0–1.8 s beam sweeps and bars rise as it passes · 1.8–3.9 s trend line inks through the tops ·
3.9–5 s bars settle; frame 5 = frame 0`. Keep to one idea per piece. If the user lists five things,
pick the one that carries the message, or ask. Show the scene in the first frame, because it
becomes the thumbnail everywhere. When the timeline naturally starts empty, keep the timeline and
offset the phase: `const t = wrap(time + POSTER)` at the top of render, with `POSTER` set to the
richest moment. The loop is unchanged and still seamless.

### S · Style: how it looks, how it moves

Name both halves in concrete terms:
- **Looks**: ground, ink, one accent (two at most), font(s), texture, with exact hex values and
  real font names.
- **Moves**: pace (slow and eased, or snappy and stepped), what moves first, what holds, the easing.

Pick one of the six specs in [references/styles.md](references/styles.md) (Field Notes chart,
Charcoal Caliper, Swiss kinetic type, Sumi ink bloom, Paper-cut layers, Risograph two-colour), or
derive a style from the brand. Settle the formats (16:9 1920×1080, 9:16 1080×1920, 1:1 1080×1080)
and the length (5–10 s).

Write `motion/<slug>/brief.md` in this shape and show the user its four lines before you build.
Only wait for an answer if something is genuinely ambiguous.

```
R: <the references, and what must stay faithful to them>
I: <length>. Beginning: … Middle (the one change): … End: … The last frame matches the first.
S: Looks like <ground, ink, accent, font, texture>. Moves <pace, easing, what moves first>. <formats>
E: Every frame from one render(t), real texture, frames at 0/25/50/75/100% checked and fixed.
```

### Build

1. `cp <skill>/assets/template.html motion/<slug>/index.html` (for a website hero, use
   `hero-template.html`).
2. Fill section 1, the settings: `DURATION`, `FORMATS`, `THEME` (a brand.json `theme` drops
   straight in), `PARAMS` for knobs the user may change (a title, `drink: 'coffee'`), `FONTS` with
   every font render sets, the matching Google Fonts `<link>` in `<head>`, `ASSETS` and
   `BRAND.logo` for real files, `PRELOAD` for anything async, the `<title>` and the brief comment.
3. Replace the demo inside `render()` with the piece. Leave section 4 (the harness) alone, because
   the scripts talk to it.
4. For captions, sound or animating an SVG logo, paste the matching file from
   `<skill>/assets/snippets/` (`captions.js`, `sound.js`, `svg-logo.js`).

Briefs and build notes for the seven common jobs are in [references/recipes.md](references/recipes.md).
Techniques (easing and staggers, masks, blend modes, text, texture, particles, brush strokes, paper
shadows, riso plates, variable-font weight waves, performance) are in
[references/canvas-craft.md](references/canvas-craft.md). Finished, checked pieces live in
`assets/examples/` (an animated chart, Swiss kinetic type, a brand card for batches, a logo reveal
with a jingle, a reel with captions); its README says what each one shows. Read the closest one
before you build.

**The render(t) contract, and why each rule exists:**
- **Pure.** Output depends only on `(t, theme, w, h)`: same `t`, same pixels, in any order. That is
  what makes scrubbing, format switching, the checks and exact exports possible.
- **Seeded randomness.** Use `hash(i, seed)`, `noise()`, `fbm()` and `loopNoise()`, never
  `Math.random()`, and don't read the clock (`Date.now`, `performance.now`) inside render.
- **Loops.** At `t = DURATION` everything is back where it was at `t = 0`. Build motion from
  `seg(t, a, b)` windows that come back down, or from `wave(t, cycles)` and `loopNoise(t)`, which
  complete whole cycles.
- **Ease everything** (`ease.inOut`, `ease.outQuint`, `ease.outBack`…). Linear motion reads as
  machine-made.
- **Measure in `u`** (1 u = 1 px at 1080 on the short side) and lay out from `stage(w, h)`. The same
  scene re-lays itself for each format and is never cropped.
- **Texture every frame**: `ground()` for paper, `falloff()`/`vignette()` for light, `grain()`. A
  flat fill is the first thing that gives away machine-made motion.
- **Cache static layers** with `cached(key, make)`: built once per size, deterministic and fast.
  A big blurred shadow that never moves belongs in the cache, not in every frame.
- **Don't draw what a mask fully hides.** It saves time, and `check.py` can't see clip regions, so
  hidden text would be flagged as clipped.
- **Load before the first frame**: fonts in `FONTS`, images in `ASSETS`/`BRAND.logo`, async work in
  `PRELOAD` (e.g. `loadLogoParts`, or a Google Fonts link built from a brand's `THEME.font`).

### E · Examine: five frames, every format, fix, repeat

```bash
python <skill>/scripts/check.py motion/<slug>/index.html
```

The script renders 0/25/50/75/100% in every format and checks what a machine can check. Hard
failures: page errors, the RISE contract, `Math.random` or clock reads in render,
non-determinism, a loop seam (frame 0 ≠ last frame), fonts that didn't load, and nothing visibly
moving. Warnings: flat colour, stage fill, an empty first frame, text outside the frame, line
height under 1.1, one-word last lines, text readable for under 1.2 s, a jump at the loop point,
and slow renders.

Then **look**. Open `checks/contact-<format>.jpg` for every format with your image viewer, and a
full frame from `checks/frames/` wherever something looks off. Walk the ten tells in
[references/checklist.md](references/checklist.md) and the style's own checks. The script can't
judge taste: is the one change clear, does it feel hand-made, does it read at phone size?

Fix, rerun and look again. It usually takes 2–4 rounds. Stop when it passes and looks right. If
something can't be fixed, say what and why. Warnings are judgment calls: a deliberate hard cut
keeps its loop-point warning, and you tell the user it's intended.
For website heroes, add `--page` to also screenshot the real page (HTML text over the motion) on
desktop and phone.

### Deliver

- **Video**, when wanted:
  `python <skill>/scripts/export.py motion/<slug>/index.html [--formats 9:16] [--loops 2] [--gif]`.
  Frames come from `render(t)`, not a screen recording, so nothing drops. `score()` audio is muxed
  in, and `--under clip.mp4` puts footage beneath the canvas for reels.
- **Batches** (recipe 7): `brand_scrape.py --file sites.txt`, then `export.py --brands`, then
  `wall.py --stagger 0.08` (so the tiles don't all blank at once). Always try 5 first with
  `--limit 5`.
- **Tell the user** where the files are, how to preview (open `index.html` in a browser: 1/2/3 switch
  formats, space pauses, arrows step frames), and what the checks found. If you can send files,
  send a contact sheet.

## Script reference

| Script | What it does | Useful flags |
|---|---|---|
| `doctor.py` | checks the machine, prints fixes | |
| `brand_scrape.py URL…` | brand.json, logo, icon, screenshot per site | `--out`, `--file`, `--limit`, `--mode static` |
| `check.py FILE` | 5 frames × formats, checks, contact sheets | `--formats`, `--brand`, `--param k=v`, `--page`, `--quick` |
| `export.py FILE` | MP4 (+GIF, poster), audio from `score()` | `--formats`, `--loops`, `--seconds`, `--gif`, `--brands`, `--under`, `--crf` |
| `wall.py CLIPS…` | tiles clips into one grid video | `--cols`, `--tile`, `--gap`, `--stagger`, `--seconds` |

`check.py` and `export.py` take `--brand path/brand.json` (or `--theme '{"accent":"#ff3b1f"}'` and
`--param title=Hello`) to inject a theme, name, logo and knobs without editing the file. The
template reads them from `window.RISE_OVERRIDES`.

## When things go wrong

- **A site can't be scraped**: the network may block it (Claude Code cloud environments allow a
  limited set of hosts). Use the WebFetch fallback, or ask the user for a screenshot and their
  brand colours. Say which host was blocked; don't route around a network policy.
- **Fonts fall back**: `check.py` fails on this. Google Fonts must be reachable, or put `.woff2`
  files next to the piece and declare them with `@font-face`.
- **Chromium won't start**: `python -m playwright install chromium`, or point `RISE_CHROME` at an
  installed Chrome.
- **The export is huge**: grain is what H.264 can't compress. The template's 2 px grain re-rolls at
  15 fps to keep files small; raise `--crf` (22–23) for previews.

## Reference files

- [references/styles.md](references/styles.md): the six styles as specs (look, timeline, palette,
  rules, checks, build notes). Read the one you're using.
- [references/recipes.md](references/recipes.md): the seven jobs (slide loop, website hero, reel with
  captions, one scene in three formats, logo reveal with a jingle, style from a reference image,
  100 sites into 100 films and a wall).
- [references/checklist.md](references/checklist.md): the ten tells, how to spot and fix each.
- [references/brand-scraping.md](references/brand-scraping.md): how the scraper decides, brand.json
  fields, the WebFetch fallback, font and logo rules.
- [references/canvas-craft.md](references/canvas-craft.md): techniques for the common effects.
