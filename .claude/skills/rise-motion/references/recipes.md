# Seven recipes

The seven jobs people most often bring, in rising order of ambition. They follow the seven levels
in Jack Roberts' *Motion, drawn in code* guide, rebuilt around this skill's scripts. Each has a
brief skeleton (fill in the user's material), build notes, and the commands to run. Every
brief ends with the same **E** line:

> E: every frame from one render(t), real texture so it feels hand-made, frames at 0/25/50/75/100%
> checked in every format and fixed before stopping.

**Contents:** [1 Slide that moves](#1--a-slide-that-moves-on-its-own) ·
[2 Website hero](#2--a-website-hero-that-comes-alive) ·
[3 Reel graphic + captions](#3--a-reel-graphic-with-word-timed-captions) ·
[4 One scene, every size](#4--one-b-roll-scene-in-every-size) ·
[5 Logo reveal + jingle](#5--any-logo-animated-with-its-own-jingle) ·
[6 Style from a reference](#6--borrow-the-style-of-a-reference-image) ·
[7 100 sites → 100 films](#7--a-hundred-websites-in-a-hundred-films-out)

---

## 1 · A slide that moves on its own

**When**: the user has a static slide (a screenshot or deck export) and wants it to explain its point
by itself, as a loop behind a talk or a post.

**Brief skeleton**
- R: the slide screenshot (in `ref/`); its exact text, colours and layout.
- I: 10 s. One change that *is* the slide's point: a beam of light runs along a timeline and lights
  its three milestones, or bars grow in order of the argument. The last frame matches the first.
- S: ivory paper, black ink lines, one clay-orange accent, slow and eased, 1920×1080.

**Build notes**
- Redraw the slide in canvas with its real text rather than animating the screenshot pixels. It
  stays crisp at any size and every element can move. Read the text and positions off the image;
  match fonts as closely as Google Fonts allows (note any substitution in the brief).
- If the slide has a photo or chart you can't redraw, put it in `ASSETS` and animate overlays on top
  (light sweeps, highlights, callouts).
- Style 01 (Field Notes) in styles.md is this recipe done in full.

```bash
cp <skill>/assets/template.html motion/<slug>/index.html
python <skill>/scripts/check.py motion/<slug>/index.html --formats 16:9
python <skill>/scripts/export.py motion/<slug>/index.html --formats 16:9 --loops 2
```

---

## 2 · A website hero that comes alive

**When**: "make our homepage hero feel alive", "animated landing page", a product site redesign.

**Brief skeleton**
- R: `brand_scrape.py` output for the site: colours, fonts, logo and **copy** (headline, subline, CTA).
- I: one image that says what the product does. For a voice-typing app: a voice wave turns into
  birds that fly into a text field and become typed words. In the footer the same birds gather into
  the wordmark behind ordinary links.
- S: the brand's own colours, fonts and paper texture; calm; the birds lean toward the cursor and
  scatter on click. Headline, subline and button stay **real HTML text**.

**Build notes**
- Start from `assets/hero-template.html`: HTML text on top, one canvas layer per scene
  (`data-scene="hero"`, `data-scene="footer"`), each drawn by its own pure function
  `(ctx, t, theme, w, h, input)`. `input` carries the pointer and recent clicks with their ages, so
  frames stay reproducible and the checks can run without a mouse.
- Keep the text readable at every moment: the motion lives mostly below and behind it, with contrast
  in mind. The template already handles devicePixelRatio, offscreen pausing and
  `prefers-reduced-motion` (one calm still frame).
- Put the brand's headline and CTA copy in `PARAMS`, or pass `--brand` and the template reads
  `BRAND.copy`.
- Deliver the HTML (it is the product). Offer a canvas-only video export for social posts.

```bash
python <skill>/scripts/brand_scrape.py https://site.com --out motion/<slug>/brand
cp <skill>/assets/hero-template.html motion/<slug>/index.html
python <skill>/scripts/check.py motion/<slug>/index.html --brand motion/<slug>/brand/<site> --page
python <skill>/scripts/check.py motion/<slug>/index.html --brand motion/<slug>/brand/<site> --param scene=footer --quick
```
Once the brand is right, bake it in (copy `theme` into `THEME` and the logo path into `BRAND.logo`)
so the page works without flags.

---

## 3 · A reel graphic with word-timed captions

**When**: a talking-head short (Reels, Shorts, TikTok) that needs a motion graphic above the speaker
and captions that follow the words.

**Brief skeleton**
- R: frames from the user's existing reels (their look), a ~10 s clip of them talking, and word
  timings.
- I: top half, an animated graphic of the clip's claim (e.g. two product logos pulling together and
  locking); bottom half, the clip itself.
- S: dark, real logos, big type. Captions show at most 3 words, timed to the speech, with the spoken
  word lit. Offer three caption looks (editorial serif, boxed heavy sans, and one premium look you
  design). 1080×1920.

**Build notes**
- Set `FORMATS = ['9:16']` and `UNDER = { src: 'ref/clip.mp4', rect: [0, 960, 1080, 960] }`. The
  player shows the clip under the canvas; `render()` leaves that rect transparent
  (`ctx.clearRect`) and draws the graphic in the top half and the captions over the seam or the
  clip.
- Paste `assets/snippets/captions.js`. Word timings are `[{w, s, e}]` in seconds. Get them from the
  user's editor (CapCut, Descript and Premiere export them), or from Whisper with word timestamps if
  it's installed. Don't invent timings for real speech.
- Real logos only: scrape them (`brand_scrape.py`) or use the files the user gives you.
- Set `DURATION` to the clip length (or the section being used). The export trims and loops the clip
  to match.
- Make one export per caption look (`--param look=boxed` etc.), and let the user pick.

```bash
python <skill>/scripts/check.py motion/<slug>/index.html                # checker shows the clip area as a checkerboard
python <skill>/scripts/export.py motion/<slug>/index.html --param look=boxed --name reel-boxed
```
`export.py` picks up `UNDER` automatically (or pass `--under clip.mp4 --under-rect x,y,w,h`) and keeps
the clip's audio.

---

## 4 · One B-roll scene in every size

**When**: an editor needs the same B-roll moment for YouTube (16:9), Shorts/Reels (9:16) and a square
post (1:1).

**Brief skeleton**
- R: the line from the voiceover it illustrates (e.g. "With enough coffee, anything is possible.").
- I: 10 s. A coffee cup whose steam draws three little living screens (a video player, a photo
  post, a text post), then curls back into the cup. The last frame matches the first.
- S: dark editorial with warm light, smooth. **One scene that re-lays itself** for 16:9, 9:16 and
  1:1, never a crop. A `PARAMS` knob at the top (`drink: 'coffee'`) so the user can change it.

**Build notes**
- Lay out from `stage(w, h)`: in 16:9 the three screens sit in a row beside the cup; in 9:16 they
  stack above it; in 1:1 they fan out in an arc. Everything is sized in `u`, so type and strokes keep
  their weight across formats.
- `check.py` renders all three formats. Read all three contact sheets, because a layout that works
  wide often clips tall.
- The PARAMS knob must genuinely change the scene (label text, colour of the drink, steam
  behaviour), not just a caption.

```bash
python <skill>/scripts/check.py motion/<slug>/index.html                 # all FORMATS
python <skill>/scripts/export.py motion/<slug>/index.html               # one MP4 per format
python <skill>/scripts/export.py motion/<slug>/index.html --param drink=tea --name tea
```

---

## 5 · Any logo animated, with its own jingle

**When**: logo reveals, intros and outros, a set of client logos.

**Brief skeleton**
- R: the real logo files from `brand_scrape.py` (prefer `logo.svg`, which can be split into parts).
- I: 5 s per brand, with a different idea per brand drawn from its character: a blocks-based mark
  assembles from its pieces, a playful mascot bounces, a sound brand's arcs pulse to the beat, an
  athletic mark strikes on like a stroke.
- S: exact logo shapes and colours, motion in each brand's own energy, and a 3 s jingle written in
  code and locked to the motion. The sound starts muted in the player.

**Build notes**
- Paste `assets/snippets/svg-logo.js`. `loadLogoParts('brand/<site>/logo.svg')` in `PRELOAD` gives
  you each shape as a `Path2D` with its fill and box. `drawLogo()` takes a per-part style
  (alpha, offset, scale, draw-on) so you can stagger, assemble or trace the real mark.
- If a brand only ships a PNG, animate the whole image (mask wipes, scale with overshoot, a light
  sweep) rather than faking parts.
- Paste `assets/snippets/sound.js` and write `score()` so its hits land on the same `t` as the
  visual beats (`tone`, `noiseHit`, `kick`). Keep the peak under 1.0.
- One file per brand, or one file with `PARAMS.brand` switching scenes and `--param brand=…` at
  export.

```bash
python <skill>/scripts/brand_scrape.py notion.com duolingo.com spotify.com nike.com --out motion/<slug>/brand
python <skill>/scripts/export.py motion/<slug>/index.html --formats 1:1   # audio comes from score()
```

---

## 6 · Borrow the style of a reference image

**When**: "make it look like this" with a Savee, Pinterest, Are.na or Dribbble image.

**Brief skeleton**
- R: the reference image (download it into `ref/` and look at it).
- I: the user's own subject, e.g. a 10 s explainer of "how a site's brand gets read: URL in;
  logo, colours and fonts out".
- S: the reference's **style, not its picture**: palette, type, texture, composition. Before
  building, write two short paragraphs, how it looks and how it would move, and show them.

**Build notes**
- Sample the palette properly: read the image, name 4–6 colours with hex values, and map them
  to `bg/ink/accent/accent2`.
- Identify the texture (halftone, riso, paper, film, gradient mesh) and pick the matching technique
  from canvas-craft.md.
- Never trace or reproduce the reference's own subject or artwork. The piece must be recognisably
  the user's subject in that style.

---

## 7 · A hundred websites in, a hundred films out

**When**: personalised outreach, a showcase of clients, "make one for every brand on this list".

**Brief skeleton**
- R: `sites.txt` (one URL per line). For each: name, logo, 2–3 colours, font.
- I: one 8 s template, "{Name}, in motion", that looks good for **any** brand.
- S: premium, with automatic contrast for light and dark logos. The logo strikes in, the colours
  sweep, the line lands. 1080×1080 MP4s, then a 10×10 wall video. Test on 5 first.

**Build notes**
- The template reads everything from `THEME` and `BRAND`. Use `readable(bg, …)` for text and
  plates, check the logo's own luminance against the ground, and put it on a plate if the contrast
  is low. Handle `monochrome: true` brands with type and texture instead of colour.
- Run the checker against 3–5 very different brands (light, dark, monochrome, long names) before
  exporting the batch: `check.py --brand brands/<slug> --quick` for each.
- Scraping 100 sites takes a few minutes. Some will fail (bot walls, network policy). Report
  them and continue with the rest.

```bash
python <skill>/scripts/brand_scrape.py --file sites.txt --out motion/<slug>/brands --limit 5
python <skill>/scripts/check.py motion/<slug>/index.html --brand motion/<slug>/brands/<one> --quick
python <skill>/scripts/export.py motion/<slug>/index.html --brands motion/<slug>/brands --formats 1:1 --limit 5
# looks right? run the full list (drop --limit), then:
python <skill>/scripts/wall.py motion/<slug>/exports --cols 10 --stagger 0.08 --out motion/<slug>/wall.mp4
```
`assets/examples/brand-card.html` is a tested version of this template: runtime Google Fonts from
`THEME.font`, a contrast plate for low-contrast logos, and a logo box that follows the logo's aspect.
A centred icon plus caption will sit at 60–70% fill; that's the logo's clear space, so keep the
warning and say why.
