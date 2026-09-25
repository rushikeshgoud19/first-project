# Scraping a brand with Claude's own tools

The R step often starts from a website: its logo, colours, fonts and headline copy. This skill
reads them itself. There's no Firecrawl, no API key, and nothing leaves the machine except
ordinary page requests.

## The scraper

```bash
python <skill>/scripts/brand_scrape.py https://site.com --out motion/<slug>/brand
python <skill>/scripts/brand_scrape.py a.com b.com c.com --out brands          # several
python <skill>/scripts/brand_scrape.py --file sites.txt --out brands --limit 5 # a list; test 5 first
python <skill>/scripts/brand_scrape.py https://site.com --mode static          # no browser available
```

It merges two passes:

1. **Static**: fetches the HTML and up to 12 stylesheets over plain HTTP. It reads CSS custom
   properties (`--primary`, `--brand-color`, shadcn-style HSL channels, Tailwind v4 `oklch()`),
   colours declared on `html/body`, buttons, links and headings, `@font-face` rules, Google Fonts
   links, `<meta name="theme-color">`, the web manifest, favicons and apple-touch-icons, and inline
   SVGs in the header.
2. **Render**: loads the page in headless Chromium (1440×900), dismisses a cookie banner if there is
   one, and measures what is actually on screen. It samples the painted background on a 32×20 grid,
   weights text colours by how much text uses them, reads the colours of buttons and links, the
   computed fonts of the body and the largest headline, and finds the logo element (in the header,
   linking home, named "logo" or the site). It bakes computed fills into the logo SVG, rasterises it
   to a transparent PNG, and takes a screenshot.

**How the theme is chosen**
- `bg`: the colour painted over the most sample points (≥ 20% of the first screen).
- `ink`: the most-used text colour with contrast ≥ 4.5 against `bg`.
- `accent`: the highest-scoring *chromatic* colour that is distinct from `bg` and `ink`. Evidence
  adds up: prominent buttons, the logo's own colours, canonical CSS variables (`--primary`,
  `--brand`, `--accent`), theme-color, the mask-icon colour, link colour, and large painted areas.
- `accent2`: the next distinct candidate, or a tint of the accent (flagged `accent2_derived`).
- `font` / `fontBody`: the display font of the biggest headline and the body font. When a family
  isn't on Google Fonts (most proprietary brand faces), `use` is the nearest Google family and the
  site's own font files are listed under `fonts.*.files`.
- `monochrome: true` when no chromatic colour exists (black-and-white brands). Design with contrast,
  type and texture, not a borrowed accent.

## brand.json

```jsonc
{
  "schema": "rise-brand/1",
  "url": "https://claude.com", "final_url": "https://claude.com/", "source": "static+render",
  "name": "Claude",
  "copy": { "headline": "…", "subline": "…", "cta": "Try Claude" },
  "theme": { "bg": "#faf9f5", "ink": "#141413", "accent": "#d97757", "accent2": "#9775fa",
             "font": "Newsreader", "fontBody": "Inter" },            // → render(ctx, t, theme, w, h)
  "scheme": "light", "monochrome": false, "accent2_derived": false,
  "palette": [ { "hex": "#d97757", "role": "accent", "score": 31.5,
                 "evidence": ["button “Try Claude”", "logo colour 24%"] } ],
  "fonts": { "heading": { "family": "anthropicSerif", "google": false, "use": "Newsreader",
                          "files": ["https://…woff2"] },
             "body": { … }, "google_css": "https://fonts.googleapis.com/css2?family=…" },
  "logo": { "file": "logo.png", "svg": "logo.svg", "how": "in header, links home, named logo",
            "size": [1200, 262], "colors": ["#101010", "#e07050"] },
  "icon": { "file": "icon.png", "how": "apple-touch-icon" },
  "logo_candidates": [ … ], "screenshot": "screenshot.jpg",
  "warnings": [ "heading font “anthropicSerif” is not on Google Fonts; theme uses Newsreader …" ]
}
```

**Always verify before building**: open `screenshot.jpg` and `logo.png`. The scraper is good, but a
page's first screen can mislead it: a hero photo, a seasonal campaign colour, a cookie wall, or a
dark-mode default. If the logo is wrong, another candidate is listed in `logo_candidates`, or ask
the user for the file. If the colours look off, trust the screenshot and your eyes and edit `theme`,
noting why in the brief.

**Warnings to act on**
- *rendered without its CSS*: the network blocked the site's stylesheet CDN. Browser colours and
  fonts were ignored. Confirm the palette another way (below).
- *not on Google Fonts*: the theme uses a stand-in. Say so in the brief. Use the site's own files
  only if the user has the rights (brand fonts are licensed; fine for a pitch mock-up, not for
  publishing without a licence).
- *no header logo found*: get the real file from the user. Never draw one.

## Fallback: WebFetch (when the script can't reach the site)

Claude's WebFetch tool reads pages through a different path. When `brand_scrape.py` fails (bot wall,
blocked host) and WebFetch is allowed, run two fetches:

1. The homepage, with this prompt:
   > List exactly: the brand/site name; the URL of the main header logo image (prefer SVG) and of
   > the favicon/apple-touch-icon; every stylesheet URL; every font-family name and Google Fonts
   > link; the meta theme-color; the main headline, subheadline and primary button text. Quote URLs
   > and values exactly as they appear.
2. The main stylesheet URL from step 1, with this prompt:
   > List the CSS custom properties that hold colours, with their exact values; the background and
   > text colours of html/body; the background colour of buttons/.btn/CTA classes; the link colour;
   > and the font-family for body and h1/h2. Quote values exactly.

Then write `brand.json` by hand in the schema above with `"source": "webfetch"`, download the logo
with WebFetch or `curl`, and say in the brief that the palette came from CSS, not from the rendered
page.

If nothing can reach the site, say which host is blocked and ask the user for a screenshot, their
logo file and brand colours. In Claude Code cloud sessions, the environment's network settings
decide which hosts are reachable, and the user can allow more. Never route around a blocked
host through a mirror or proxy.

## Logos and fonts: the rules

- Real files only. A logo drawn from memory is the fastest way to lose trust.
- Keep the logo's proportions and colours. Recolour only to the brand's own alternate (e.g. white
  on dark) when contrast demands it, and say so.
- For motion, prefer `logo.svg` (split into parts with `snippets/svg-logo.js`). `logo.png` is the
  safe raster for canvas `drawImage`.
- Fonts: Google Fonts families load freely. Proprietary brand fonts get a named stand-in unless
  the user supplies licensed files.
