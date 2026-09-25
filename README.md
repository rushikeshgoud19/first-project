# rise-motion: motion graphics drawn in code

A Claude skill for making motion graphics with the **RISE method** (References, Idea, Style,
Examine), from Jack Roberts' free guide *Motion, drawn in code*. The guide's workflow used
Firecrawl for brand scraping; this skill scrapes with Claude's own tools instead, so it needs no
API keys.

Every piece is one HTML file with one pure `render(ctx, t, theme, w, h)` function. It previews live
in a browser, re-lays itself for 16:9, 9:16 and 1:1, gets its frames checked automatically, and
exports frame-exact MP4s.

## Use it

In Claude Code, inside this repo, ask for something that moves:

- "make my Q3 bar chart (12, 19, 27, 41) a 5 second loop in the field notes style"
- "logo reveal for claude.com with a 3 second jingle, square mp4"
- "swiss kinetic type loop of the word Motion for reels and youtube"
- "bring our homepage hero to life", "films for every site in sites.txt"

Or invoke it by name: `/rise-motion …`. The skill lives in
[`.claude/skills/rise-motion/`](.claude/skills/rise-motion/SKILL.md), so Claude Code picks it up
automatically in this repo.

**Everywhere else**
- All your projects in Claude Code: `cp -r .claude/skills/rise-motion ~/.claude/skills/`
- claude.ai / the Claude apps: upload [`dist/rise-motion.skill`](dist/rise-motion.skill) under
  Settings → Capabilities → Skills.

**One-time setup** (Claude runs `scripts/doctor.py` and tells you if anything is missing):
```bash
pip install playwright imageio-ffmpeg
# only if there's no Chrome/Chromium on the machine:
python -m playwright install chromium
```

## What's inside

| Path | What it is |
|---|---|
| `SKILL.md` | the workflow: R → I → S → E, the render(t) contract, delivery |
| `scripts/brand_scrape.py` | logo, colours, fonts and headline copy from any URL (static CSS analysis + headless-browser pass), no Firecrawl |
| `scripts/check.py` | the E step: frames at 0/25/50/75/100% in every format, contact sheets, automated checks (loop seam, determinism, fonts, texture, stage fill, text) |
| `scripts/export.py` | MP4/GIF through `render(t)`, audio from `score()`, a clip under the canvas for reels, batch per brand |
| `scripts/wall.py` | tiles many clips into a grid video |
| `scripts/doctor.py` | checks the machine and prints fixes |
| `assets/template.html` | the starting file: settings, helpers (easing, seeded noise, paper, grain, light), player |
| `assets/hero-template.html` | a living website hero: real HTML text over interactive canvas layers |
| `assets/snippets/` | word-timed captions, sound written in code, animating a real SVG logo |
| `assets/examples/` | five finished, checked pieces |
| `references/` | six style specs, seven recipes, the ten tells, brand-scraping notes, canvas techniques |

Motion pieces go in `motion/<slug>/`. Their `checks/` and `exports/` folders are git-ignored because
they're regenerated (and videos are large).
