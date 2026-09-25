# Examples

Finished pieces that passed `check.py`. Read one before your first build to see the idioms in
context: cached layouts, `seg`/`ease` timelines, poster-frame offsets, format re-lays, snippets.

| File | Shows | Runs as is? |
|---|---|---|
| `field-notes-chart.html` | Style 01, recipe 1: an animated bar chart, beam-timed bars (inverse easing), trend line drawn by length, 16:9 + 9:16 re-lay | yes |
| `swiss-kinetic-type.html` | Style 03: variable-font weight wave, baseline mask, grid-snapped disc; the word runs up the long side in 9:16 | yes |
| `brand-card.html` | Recipe 7: one "{Name}, in motion" card for any brand; runtime Google Fonts, logo contrast plate, aspect-aware logo box | yes (`--brand` injects a brand) |
| `logo-reveal-jingle.html` | Recipe 5: real SVG logo split into parts (`svg-logo.js`), mark flight + wordmark trace, `score()` jingle locked to the beats | needs `brand/logo.svg` (scrape first) |
| `reel-captions.html` | Recipe 3: graphic on top, clip under the canvas (`UNDER`), word-timed captions (`captions.js`) | needs `ref/clip.mp4` for the clip |

All of them start from `../template.html` and keep its harness. Frame 0 is always the richest moment
(the poster), via `t = wrap(time + POSTER)`.
