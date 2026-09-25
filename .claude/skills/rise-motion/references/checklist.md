# The ten tells

Ten things that give away rushed or machine-made motion. Check every frame for them before you
ship. `check.py` catches some automatically (marked **auto**). The rest need your eyes on the
contact sheets and full frames. The list follows the one in Jack Roberts' *Motion, drawn in code*
guide, with how to spot and fix each one here.

| # | Tell | How to spot it | Fix |
|---|---|---|---|
| 1 | **Clipped letters** | Descenders (g j p q y) or accents cut off by a mask, a box or the frame edge. **auto** for text leaving the frame and for line height < 1.1; masks need eyes at the hold frames | Line height ≥ 1.1. Give masks room below the baseline (0.3 em). Measure with `actualBoundingBoxDescent` |
| 2 | **A word alone on a line** | The last line of a block holds one word. **auto** | Rewrite the line, or tie the last two words (use `lines()`, which does it) |
| 3 | **Empty stage** | The visual floats small in the frame, or one format has big dead bands. **auto** (warns when content spans < 80% of the long side) | Re-lay the scene for that format and scale in `u`. Don't shrink it into a corner. Exception: a logo needs its clear space, so a centred logo card at 60–70% is right; keep the warning and say why |
| 4 | **Flat colour** | A single flat fill behind everything. **auto** (warns above 12% of one exact colour) | `ground()` paper, `falloff()` light, a vignette. Light should fall off across the frame |
| 5 | **Linear motion** | Things move at one constant speed and stop dead | `ease.inOut` / `outQuint` / `outBack` on every movement. Scrub the HTML slowly to feel it |
| 6 | **Loop seams** | A pop when the loop restarts. **auto** (frame 0 vs last frame, plus a jump check at the loop point) | Every `seg()` window returns to its start value; periodic motion completes whole cycles (`wave`, `loopNoise`) |
| 7 | **Text held too short** | A word appears and leaves before it can be read. **auto** (warns under 1.2 s; captions are exempt) | Hold every word ≥ 1.2 s. Shorten the entrance, not the hold |
| 8 | **Fake logos** | A logo drawn from memory: wrong proportions, wrong glyphs | Use the real file: `brand_scrape.py` output or the user's file. For a PNG-only logo, animate the image as a whole |
| 9 | **Busy backgrounds** | Several competing ideas, or a ground louder than the subject | One idea on a quiet ground. Cut elements until the one change is obvious |
| 10 | **No texture** | Perfectly clean vector fills that look like a default | Real grain (`grain()`), subtle noise, paper fibre, imperfect edges |

## Also check

- **The one change reads.** Watch it once without context: can you say what happened?
- **Phone size.** Look at the 9:16 sheet at thumbnail size: is the main type still readable?
- **The first frame.** It's the poster and the thumbnail, so the scene should already be there.
- **Brand truth.** Colours match `brand.json` (or the user's values), fonts are the real ones or
  named stand-ins, the logo is the real file.
- **The style's own checks.** Each style in styles.md lists extra checks (e.g. "no bar rises
  before the beam reaches it").

## The ten tells as a prompt line

When you write a brief for someone else, or a sub-task, this line carries the whole checklist:

```
Before you stop, check every frame for the ten tells and fix any you find: clipped letters
(line height ≥ 1.1; check g, j, p, q, y), a word alone on a line, an empty stage (fill 80–95%),
flat colour (light falls off), linear motion (ease in and out), loop seams (last frame = first),
text held under 1.2 s, fake logos (real files only), busy backgrounds (one idea on a quiet ground),
and no texture (real grain and subtle noise).
```
