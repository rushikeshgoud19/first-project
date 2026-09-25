#!/usr/bin/env python3
"""Pull a website's brand (name, real logo, colours, fonts, headline copy) with Claude's own
tools. No Firecrawl, no API keys.

Two passes, merged:
  static  the HTML and its stylesheets over plain HTTP (standard library only): CSS custom
          properties, declared colours, @font-face and Google Fonts, meta theme-color,
          manifest, favicons, inline SVG logos
  render  the page in headless Chromium (when Playwright is installed): the colours actually
          painted on screen, button colours, computed fonts, the logo element in the header,
          a screenshot, and a transparent PNG of the logo

  python scripts/brand_scrape.py https://example.com
  python scripts/brand_scrape.py https://a.com https://b.com --out motion/films/brands
  python scripts/brand_scrape.py --file sites.txt --out brands --limit 5

Writes <out>/<site-slug>/brand.json plus logo.png (transparent raster for canvas), logo.svg
(vector, when the site has one), icon.png, screenshot.jpg. The `theme` block drops straight into
render(ctx, t, theme, w, h): {bg, ink, accent, accent2, font, fontBody}.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import html as htmllib
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _rise  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")

# ── colour ───────────────────────────────────────────────────────────────────

NAMED = {"white": (255, 255, 255, 1.0), "black": (0, 0, 0, 1.0), "transparent": (0, 0, 0, 0.0),
         "red": (255, 0, 0, 1.0), "green": (0, 128, 0, 1.0), "blue": (0, 0, 255, 1.0),
         "yellow": (255, 255, 0, 1.0), "orange": (255, 165, 0, 1.0), "purple": (128, 0, 128, 1.0),
         "gray": (128, 128, 128, 1.0), "grey": (128, 128, 128, 1.0), "silver": (192, 192, 192, 1.0),
         "navy": (0, 0, 128, 1.0), "teal": (0, 128, 128, 1.0), "maroon": (128, 0, 0, 1.0),
         "olive": (128, 128, 0, 1.0), "lime": (0, 255, 0, 1.0), "aqua": (0, 255, 255, 1.0),
         "fuchsia": (255, 0, 255, 1.0), "gold": (255, 215, 0, 1.0), "crimson": (220, 20, 60, 1.0),
         "tomato": (255, 99, 71, 1.0), "coral": (255, 127, 80, 1.0), "hotpink": (255, 105, 180, 1.0),
         "rebeccapurple": (102, 51, 153, 1.0), "whitesmoke": (245, 245, 245, 1.0),
         "ghostwhite": (248, 248, 255, 1.0), "ivory": (255, 255, 240, 1.0), "beige": (245, 245, 220, 1.0)}


def _to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_lin(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _oklab_to_lin(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def _lin_to_oklab(r, g, b):
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def _xyz65_to_lin(X, Y, Z):
    return (3.2409699419 * X - 1.5373831776 * Y - 0.4986107603 * Z,
            -0.9692436363 * X + 1.8759675015 * Y + 0.0415550574 * Z,
            0.0556300797 * X - 0.2039769589 * Y + 1.0569715142 * Z)


def _lab_to_lin(L, a, b):  # CIE Lab (D50), as CSS lab()/lch() use
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    e, k = 216 / 24389, 24389 / 27
    xr = fx ** 3 if fx ** 3 > e else (116 * fx - 16) / k
    yr = fy ** 3 if L > k * e else L / k
    zr = fz ** 3 if fz ** 3 > e else (116 * fz - 16) / k
    X, Y, Z = xr * 0.96422, yr, zr * 0.82521
    X2 = 0.9554734527 * X - 0.0230985369 * Y + 0.0632593087 * Z  # Bradford D50 → D65
    Y2 = -0.0283697070 * X + 1.0099954580 * Y + 0.0210413990 * Z
    Z2 = 0.0123140017 * X - 0.0205076964 * Y + 1.3303659366 * Z
    return _xyz65_to_lin(X2, Y2, Z2)


def _p3_to_lin(r, g, b):
    r, g, b = _to_lin(r), _to_lin(g), _to_lin(b)
    X = 0.4865709486 * r + 0.2656676932 * g + 0.1982172852 * b
    Y = 0.2289745641 * r + 0.6917385218 * g + 0.0792869141 * b
    Z = 0.0000000000 * r + 0.0451133819 * g + 1.0439443689 * b
    return _xyz65_to_lin(X, Y, Z)


def _num(tok, pct=1.0):
    tok = tok.strip()
    if tok in ("none", ""):
        return 0.0
    if tok.endswith("%"):
        return float(tok[:-1]) / 100 * pct
    for unit, mul in (("deg", 1.0), ("grad", 0.9), ("rad", 180 / math.pi), ("turn", 360.0)):
        if tok.endswith(unit):
            return float(tok[: -len(unit)]) * mul
    return float(tok)


def _hsl(h, s, l):
    h = (h % 360) / 360

    def f(n):
        k = (n + h * 12) % 12
        return l - s * min(l, 1 - l) * max(-1, min(k - 3, 9 - k, 1))
    return f(0), f(8), f(4)


def parse_color(value: str):
    """Any CSS colour → (r, g, b, a) with 0–255 ints, or None."""
    s = value.strip().lower()
    if not s:
        return None
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8) or not re.fullmatch(r"[0-9a-f]+", h):
            return None
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a
    m = re.fullmatch(r"([a-z-]+)\((.*)\)", s, re.S)
    if not m:
        return NAMED.get(s)
    fn, inner = m.group(1), m.group(2)
    if "var(" in inner or "calc(" in inner or "from " in inner:
        return None
    parts = inner.replace(",", " ").replace("/", " / ").split()
    alpha = None
    if "/" in parts:
        i = parts.index("/")
        alpha = parts[i + 1] if i + 1 < len(parts) else None
        parts = parts[:i]
    try:
        if fn in ("rgb", "rgba", "hsl", "hsla", "hwb") and len(parts) == 4 and alpha is None:
            alpha = parts.pop()
        a = 1.0 if alpha is None else _num(alpha)
        if fn in ("rgb", "rgba"):
            r, g, b = (_num(p, 255) / 255 for p in parts[:3])
        elif fn in ("hsl", "hsla", "hwb"):
            h = _num(parts[0])
            x = _num(parts[1]) if parts[1].endswith("%") else _num(parts[1]) / 100
            y = _num(parts[2]) if parts[2].endswith("%") else _num(parts[2]) / 100
            if fn == "hwb":
                if x + y >= 1:
                    gray = x / (x + y)
                    r = g = b = gray
                else:
                    r, g, b = (c * (1 - x - y) + x for c in _hsl(h, 1, 0.5))
            else:
                r, g, b = _hsl(h, x, y)
        elif fn == "oklch":
            L = _num(parts[0], 1.0)
            C = _num(parts[1], 0.4)
            H = math.radians(_num(parts[2]))
            r, g, b = (_from_lin(c) for c in _oklab_to_lin(L, C * math.cos(H), C * math.sin(H)))
        elif fn == "oklab":
            r, g, b = (_from_lin(c) for c in _oklab_to_lin(_num(parts[0], 1.0), _num(parts[1], 0.4), _num(parts[2], 0.4)))
        elif fn == "lab":
            r, g, b = (_from_lin(c) for c in _lab_to_lin(_num(parts[0], 100), _num(parts[1], 125), _num(parts[2], 125)))
        elif fn == "lch":
            L, C, H = _num(parts[0], 100), _num(parts[1], 150), math.radians(_num(parts[2]))
            r, g, b = (_from_lin(c) for c in _lab_to_lin(L, C * math.cos(H), C * math.sin(H)))
        elif fn == "color":
            space, vals = parts[0], [_num(p) for p in parts[1:4]]
            if space == "srgb":
                r, g, b = vals
            elif space == "srgb-linear":
                r, g, b = (_from_lin(c) for c in vals)
            elif space == "display-p3":
                r, g, b = (_from_lin(c) for c in _p3_to_lin(*vals))
            else:
                return None
        else:
            return None
    except (ValueError, IndexError):
        return None
    clamp = lambda v: max(0, min(255, round(v * 255)))  # noqa: E731
    return clamp(r), clamp(g), clamp(b), max(0.0, min(1.0, a))


COLOR_TOKEN = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch|color)\([^()]*\)"
                         r"|\b(?:white|black|red|green|blue|yellow|orange|purple|gold|crimson|tomato|coral|hotpink|navy|teal|ivory|beige)\b")


def hexof(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb[:3])


def lab_of(hexs):
    r, g, b = (int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return _lin_to_oklab(_to_lin(r), _to_lin(g), _to_lin(b))


def chroma(hexs):
    _, a, b = lab_of(hexs)
    return math.hypot(a, b)


def dist(h1, h2):
    p, q = lab_of(h1), lab_of(h2)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(p, q)))


def rel_lum(hexs):
    r, g, b = (_to_lin(int(hexs[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(h1, h2):
    a, b = sorted((rel_lum(h1), rel_lum(h2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def mixhex(h1, h2, k):
    c1 = [int(h1[i:i + 2], 16) for i in (1, 3, 5)]
    c2 = [int(h2[i:i + 2], 16) for i in (1, 3, 5)]
    return hexof([round(a + (b - a) * k) for a, b in zip(c1, c2)])


# ── fonts ────────────────────────────────────────────────────────────────────

GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif",
           "ui-serif", "ui-monospace", "ui-rounded", "emoji", "math", "inherit", "initial", "unset"}
SYSTEM = {"-apple-system", "blinkmacsystemfont", "segoe ui", "helvetica", "helvetica neue", "arial",
          "apple color emoji", "segoe ui emoji", "segoe ui symbol", "noto color emoji", "sf pro",
          "sf pro text", "sf pro display", "system-ui", "roboto"}
# Closest Google Fonts for common proprietary brand faces (used when the real one can't be loaded).
NEAREST = {"helvetica": "Inter", "helvetica neue": "Inter", "arial": "Inter", "sf pro": "Inter",
           "sf pro display": "Inter", "sf pro text": "Inter", "-apple-system": "Inter", "segoe ui": "Inter",
           "söhne": "Inter", "sohne": "Inter", "graphik": "Inter", "circular": "DM Sans",
           "circular std": "DM Sans", "gt america": "Inter Tight", "gt walsheim": "DM Sans",
           "proxima nova": "Montserrat", "gotham": "Montserrat", "avenir": "Nunito Sans",
           "avenir next": "Nunito Sans", "futura": "Jost", "futura pt": "Jost", "brandon grotesque": "Josefin Sans",
           "tiempos": "Newsreader", "tiempos headline": "Newsreader", "tiempos text": "Newsreader",
           "copernicus": "Newsreader", "styrene": "Inter", "styrene a": "Inter", "styrene b": "Inter",
           "anthropic sans": "Inter", "anthropic serif": "Newsreader", "anthropic mono": "JetBrains Mono",
           "georgia": "Newsreader", "times new roman": "Newsreader", "times": "Newsreader",
           "garamond": "EB Garamond", "canela": "Newsreader", "gt sectra": "Newsreader",
           "founders grotesk": "Inter Tight", "neue haas grotesk": "Inter", "neue haas unica": "Inter",
           "aktiv grotesk": "Inter", "apercu": "Work Sans", "calibre": "Inter", "sharp grotesk": "Space Grotesk",
           "roobert": "Inter", "suisse int'l": "Inter", "suisse intl": "Inter", "abc diatype": "Inter",
           "diatype": "Inter", "matter": "Inter", "euclid circular a": "DM Sans", "euclid circular b": "DM Sans",
           "trade gothic": "Oswald", "din": "Barlow", "din pro": "Barlow", "d-din": "Barlow",
           "sf mono": "JetBrains Mono", "menlo": "JetBrains Mono", "monaco": "JetBrains Mono",
           "consolas": "JetBrains Mono", "courier new": "Courier Prime", "mona sans": "Mona Sans",
           "hubot sans": "Hubot Sans", "source sans pro": "Source Sans 3", "source serif pro": "Source Serif 4"}
BY_CLASS = {"serif": "Newsreader", "sans-serif": "Inter", "monospace": "JetBrains Mono", "cursive": "Caveat"}


NOT_BRAND_FONT = re.compile(r"icon|awesome|material|glyph|emoji|symbol|dashicons|\bnoto\b.*\b(jp|kr|sc|tc|hk|cjk|arabic|hebrew|thai)\b|"
                            r"\b(jp|kr|sc|tc|cjk)\b|arabic|hebrew|thai|devanagari|fallback", re.I)


def clean_family(name: str) -> str:
    n = name.strip().strip("\"'").strip()
    n = re.sub(r"\\([0-9a-fA-F]{1,6})\s?", lambda m: chr(int(m.group(1), 16)), n)  # CSS escapes: \31 → 1
    n = re.sub(r"\\(.)", r"\1", n)                                                  # Source Sans\ 3 → Source Sans 3
    m = re.fullmatch(r"__(.+?)_(?:Fallback_)?[0-9a-f]{5,}", n)  # next/font: __Inter_abc123
    if m:
        n = m.group(1).replace("_", " ")
    n = re.sub(r"\s+(Variable|VF|Web|Webfont|Regular)$", "", n, flags=re.I)
    return n


def first_family(stack: str):
    """'"Foo", Arial, sans-serif' → ('Foo', 'sans-serif' class)."""
    fams = [f.strip() for f in stack.split(",") if f.strip()]
    klass = next((f.lower() for f in reversed(fams) if f.lower() in BY_CLASS), "sans-serif")
    for f in fams:
        c = clean_family(f)
        if c.lower() in GENERIC or c.lower().startswith("var(") or NOT_BRAND_FONT.search(c):
            continue
        return c, klass
    return None, klass


_gf_cache = {}


def on_google_fonts(family: str) -> bool:
    if family in _gf_cache:
        return _gf_cache[family]
    url = "https://fonts.googleapis.com/css2?family=" + urllib.parse.quote_plus(family)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            # Real families are served from gstatic.com/s/…; the API also answers for some system
            # families (Times New Roman, Arial…) with metric-compatible stand-ins under /l/.
            ok = r.status == 200 and b"fonts.gstatic.com/s/" in r.read(200_000)
    except Exception:
        ok = False
    _gf_cache[family] = ok
    return ok


# ── fetching ─────────────────────────────────────────────────────────────────

def fetch(url, timeout=20, max_bytes=8_000_000, accept="text/html,application/xhtml+xml,*/*;q=0.8"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Language": "en-US,en;q=0.9",
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(max_bytes)
        enc = (r.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            data = gzip.decompress(data)
        elif enc == "deflate":
            try:
                data = zlib.decompress(data)
            except zlib.error:
                data = zlib.decompress(data, -zlib.MAX_WBITS)
        return r.geturl(), r.status, r.headers, data


def decode(data: bytes, headers) -> str:
    ct = headers.get("Content-Type", "") if headers else ""
    m = re.search(r"charset=([\w-]+)", ct) or re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', data[:4096])
    cs = m.group(1) if m else "utf-8"
    if isinstance(cs, bytes):
        cs = cs.decode("ascii", "ignore")
    try:
        return data.decode(cs, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


# ── HTML ─────────────────────────────────────────────────────────────────────

SVG_TAGS = {t.lower(): t for t in [
    "linearGradient", "radialGradient", "clipPath", "foreignObject", "textPath", "feGaussianBlur",
    "feColorMatrix", "feOffset", "feBlend", "feComposite", "feFlood", "feMerge", "feMergeNode",
    "feMorphology", "feTurbulence", "feDisplacementMap", "feImage", "feTile", "feComponentTransfer",
    "feFuncA", "feFuncR", "feFuncG", "feFuncB", "feDropShadow", "animateTransform", "animateMotion"]}
SVG_ATTRS = {a.lower(): a for a in [
    "viewBox", "preserveAspectRatio", "gradientUnits", "gradientTransform", "patternUnits",
    "patternContentUnits", "patternTransform", "clipPathUnits", "maskUnits", "maskContentUnits",
    "markerWidth", "markerHeight", "refX", "refY", "stdDeviation", "textLength", "lengthAdjust",
    "startOffset", "baseFrequency", "numOctaves", "filterUnits", "primitiveUnits", "pathLength",
    "spreadMethod", "stitchTiles", "attributeName", "repeatCount", "keyTimes", "keySplines", "calcMode"]}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
        "track", "wbr"}
LOGO_HINT = re.compile(r"logo|brand|wordmark|logotype|site-title|navbar-brand", re.I)


class PageParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.host = urllib.parse.urlsplit(base_url).hostname or ""
        self.stack = []
        self.title, self._title = "", False
        self.metas, self.links, self.styles = {}, [], []
        self._style = None
        self.inline = []
        self.imgs, self.svgs = [], []
        self._svg = None
        self.h1, self._h1 = [], None
        self.buttons, self._btn = [], None
        self.paras, self._p = [], None
        self.order = 0

    # context from the open elements
    def _ctx(self):
        header = nav = footer = home = False
        for tag, a in self.stack:
            idc = f"{a.get('id', '')} {a.get('class', '')}".lower()
            if tag == "header" or a.get("role") == "banner" or re.search(r"\b(site-)?header\b|navbar|masthead|topbar", idc):
                header = True
            if tag == "nav" or a.get("role") == "navigation":
                nav = True
            if tag == "footer" or a.get("role") == "contentinfo" or "footer" in idc:
                footer = True
            if tag == "a" and self._is_home(a.get("href", ""), a.get("rel", "")):
                home = True
        return {"header": header, "nav": nav, "footer": footer, "home": home,
                "hint": any(LOGO_HINT.search(f"{a.get('id', '')} {a.get('class', '')} {a.get('aria-label', '')}")
                            for _, a in self.stack[-3:])}

    def _is_home(self, href, rel=""):
        if "home" in rel.split():
            return True
        if not href:
            return False
        u = urllib.parse.urlsplit(urllib.parse.urljoin(self.base, href))
        same = (u.hostname or "").removeprefix("www.") == self.host.removeprefix("www.")
        return same and not u.query and re.fullmatch(r"/?(index\.html?)?|/[a-z]{2}(-[a-z]{2})?/?", u.path or "/") is not None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.order += 1
        if self._svg is not None:
            self._svg_open(tag, attrs, selfclose=False)
            return
        if tag == "svg":
            self._svg = {"parts": [], "depth": 0, "ctx": self._ctx(), "attrs": a, "order": self.order}
            self._svg_open(tag, attrs, selfclose=False)
            return
        self._element(tag, a)
        if tag not in VOID:
            self.stack.append((tag, a))

    def handle_startendtag(self, tag, attrs):
        if self._svg is not None:
            self._svg_open(tag, attrs, selfclose=True)
            return
        self._element(tag, {k: (v or "") for k, v in attrs})

    def _element(self, tag, a):
        if a.get("style") and len(self.inline) < 400:
            self.inline.append((tag, a.get("class", ""), a["style"], self._ctx()))
        if tag == "title":
            self._title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("itemprop") or "").lower()
            if key and "content" in a:
                self.metas.setdefault(key, a["content"])
        elif tag == "link":
            self.links.append({"rel": a.get("rel", "").lower().split(), "href": a.get("href", ""),
                               "sizes": a.get("sizes", ""), "type": a.get("type", ""),
                               "color": a.get("color", ""), "as": a.get("as", "")})
        elif tag == "style":
            self._style = []
        elif tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split(",")[0].split()[0]
            self.imgs.append({"src": src, "alt": a.get("alt", ""), "cls": a.get("class", ""), "id": a.get("id", ""),
                              "w": a.get("width", ""), "h": a.get("height", ""), "ctx": self._ctx(), "order": self.order})
        elif tag == "h1" and self._h1 is None:
            self._h1 = []
        elif tag in ("button", "a") and self._btn is None:
            if tag == "button" or re.search(r"\b(btn|button|cta)\b", a.get("class", ""), re.I):
                self._btn = []
        elif tag == "p" and self._p is None and len(self.paras) < 6:
            self._p = []

    def handle_endtag(self, tag):
        if self._svg is not None:
            self._svg_close(tag)
            return
        if tag == "title":
            self._title = False
        elif tag == "style" and self._style is not None:
            self.styles.append("".join(self._style))
            self._style = None
        elif tag == "h1" and self._h1 is not None:
            text = " ".join("".join(self._h1).split())
            if text:
                self.h1.append(text)
            self._h1 = None
        elif tag in ("button", "a") and self._btn is not None:
            text = " ".join("".join(self._btn).split())
            if 1 < len(text) < 40:
                self.buttons.append(text)
            self._btn = None
        elif tag == "p" and self._p is not None:
            text = " ".join("".join(self._p).split())
            if len(text) > 24:
                self.paras.append(text)
            self._p = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._svg is not None:
            self._svg["parts"].append(htmllib.escape(data, quote=False))
            return
        if self._title:
            self.title += data
        if self._style is not None:
            self._style.append(data)
        for buf in (self._h1, self._btn, self._p):
            if buf is not None:
                buf.append(data)

    # inline SVG capture, restoring the camelCase html.parser lowercases
    def _svg_open(self, tag, attrs, selfclose):
        name = SVG_TAGS.get(tag, tag)
        out = []
        for k, v in attrs:
            k2 = SVG_ATTRS.get(k, k)
            out.append(f' {k2}="{htmllib.escape(v or "", quote=True)}"')
        self._svg["parts"].append(f"<{name}{''.join(out)}{'/' if selfclose else ''}>")
        if not selfclose:
            self._svg["depth"] += 1

    def _svg_close(self, tag):
        self._svg["parts"].append(f"</{SVG_TAGS.get(tag, tag)}>")
        self._svg["depth"] -= 1
        if self._svg["depth"] <= 0:
            markup = "".join(self._svg["parts"])
            if "xmlns=" not in markup[:300]:
                markup = markup.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
            if "xlink:" in markup and "xmlns:xlink" not in markup[:400]:
                markup = markup.replace("<svg", '<svg xmlns:xlink="http://www.w3.org/1999/xlink"', 1)
            self.svgs.append({"markup": markup, "ctx": self._svg["ctx"], "attrs": self._svg["attrs"],
                              "order": self._svg["order"]})
            self._svg = None


# ── CSS ──────────────────────────────────────────────────────────────────────

DARK_SELECTOR = re.compile(r"\.dark\b|\[data-(?:theme|mode|color-scheme)=[\"']?dark|\.theme-dark|dark-mode|:root\.dark", re.I)
DECL = re.compile(r"(--[\w-]+|[a-zA-Z-]+)\s*:\s*((?:[^;{}\"'()]|\"[^\"]*\"|'[^']*'|\((?:[^()]|\([^()]*\))*\))+)")


def iter_rules(css: str, ctx: str = ""):
    """Yield (selector, body, ctx) for style rules, flattening @media/@supports/@layer;
    ctx is 'dark' inside prefers-color-scheme: dark. @font-face comes back as selector '@font-face'."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            return
        head = re.split(r"[;}]", css[i:j])[-1].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            c = css[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        low = head.lower()
        if low.startswith("@media"):
            if "print" in low and "screen" not in low:
                pass
            else:
                sub = "dark" if ("prefers-color-scheme" in low and "dark" in low) else ctx
                yield from iter_rules(body, sub)
        elif low.startswith(("@supports", "@layer", "@container", "@document", "@scope", "@-moz-document")):
            yield from iter_rules(body, ctx)
        elif low.startswith("@font-face"):
            yield "@font-face", body, ctx
        elif low.startswith("@"):
            pass  # keyframes, page, property …
        elif head:
            yield head, body, ("dark" if DARK_SELECTOR.search(head) else ctx)
        i = k


def resolve_vars(value: str, vars_: dict, depth=0) -> str:
    if "var(" not in value or depth > 8:
        return value
    out, i = [], 0
    while True:
        j = value.find("var(", i)
        if j < 0:
            out.append(value[i:])
            break
        out.append(value[i:j])
        k, level = j + 4, 1
        while k < len(value) and level:
            level += {"(": 1, ")": -1}.get(value[k], 0)
            k += 1
        inner = value[j + 4:k - 1]
        name, _, fallback = inner.partition(",")
        rep = vars_.get(name.strip())
        out.append(resolve_vars(rep if rep is not None else fallback.strip(), vars_, depth + 1))
        i = k
    return "".join(out)


BARE_HSL = re.compile(r"^\s*(-?[\d.]+)(?:deg)?\s+([\d.]+)%\s+([\d.]+)%\s*$")
BARE_OKLCH = re.compile(r"^\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)(?:deg)?\s*$")


def colors_in(value: str):
    """Colours in a resolved declaration value, including shadcn-style bare HSL channels."""
    m = BARE_HSL.match(value)
    if m:
        c = parse_color(f"hsl({m.group(1)} {m.group(2)}% {m.group(3)}%)")
        return [c] if c else []
    out = []
    for tok in COLOR_TOKEN.findall(value):
        c = parse_color(tok)
        if c:
            out.append(c)
    return out


CANON_ACCENT = re.compile(r"^--(?:color-|clr-|c-|colors-)?(?:brand|primary|accent|main|theme|key)"
                          r"(?:-(?:color|colour|base|default|main|500|600|700|1|100))?$")
PREFIX_ACCENT = re.compile(r"^--(?:color-|clr-|c-|colors-)?(?:brand|primary|accent)-")


def accent_weight(name: str) -> float:
    """--primary / --brand-color are strong evidence; --attestation-accent is a component detail."""
    n = name.lower()
    if CANON_ACCENT.match(n):
        return 6.0
    if PREFIX_ACCENT.match(n):
        return 3.0
    return 1.5


def role_of_var(name: str) -> str:
    n = name.lower()
    if n.startswith("--tw-"):
        return "skip"
    if re.search(r"brand|primary|accent|highlight|cta|main-color|theme-color|key-color", n):
        return "accent"
    if re.search(r"background|(^|-)bg($|-)|surface|canvas|page", n):
        return "bg"
    if re.search(r"foreground|(^|-)fg($|-)|text|ink|body-color", n):
        return "ink"
    if re.search(r"link", n):
        return "link"
    if re.search(r"secondary|tertiary", n):
        return "accent2"
    return "other"


class CssFacts:
    def __init__(self):
        self.vars = {}          # name → value (light / default scheme, :root first)
        self.var_roles = {}     # name → role
        self.obs = []           # (hex, alpha, role, selector-kind, evidence)
        self.font_decls = []    # (selector-kind, stack)
        self.font_faces = []    # {family, src, weight, style}
        self.dark_seen = False

    def feed(self, css: str, base_url: str):
        rules = list(iter_rules(css))
        for sel, body, ctx in rules:  # custom properties first so every rule can resolve them
            if sel == "@font-face" or ctx == "dark":
                if ctx == "dark":
                    self.dark_seen = True
                continue
            for prop, val in DECL.findall(body):
                if prop.startswith("--"):
                    rootish = re.fullmatch(r"\s*(:root|html|body|\*|:host)(\s*,\s*(:root|html|body|:host))*\s*", sel) is not None
                    if prop not in self.vars or rootish:
                        self.vars[prop] = val.strip()
        for sel, body, ctx in rules:
            if sel == "@font-face":
                face = dict((p.lower(), v.strip()) for p, v in DECL.findall(body))
                fam = clean_family(face.get("font-family", ""))
                srcs = [urllib.parse.urljoin(base_url, u.strip("\"' "))
                        for u in re.findall(r"url\(([^)]+)\)", face.get("src", ""))]
                if fam:
                    self.font_faces.append({"family": fam, "src": srcs[:3], "weight": face.get("font-weight", ""),
                                            "style": face.get("font-style", "")})
                continue
            if ctx == "dark":
                continue
            kind = selector_kind(sel)
            for prop, val in DECL.findall(body):
                p = prop.lower()
                if p.startswith("--"):
                    role = role_of_var(p)
                    if role == "skip":
                        continue
                    for c in colors_in(resolve_vars(val, self.vars)):
                        if c[3] >= 0.5:
                            self.obs.append((hexof(c), c[3], role, "var", p))
                    continue
                if p in ("font-family", "font"):
                    stack = resolve_vars(val, self.vars)
                    if p == "font":
                        m = re.search(r"\d+(?:\.\d+)?(?:px|rem|em|pt|%)(?:\s*/\s*\S+)?\s+(.+)$", stack)
                        if not m:
                            continue
                        stack = m.group(1)
                    self.font_decls.append((kind, stack))
                    continue
                role = {"background": "bg", "background-color": "bg", "color": "text", "fill": "fill",
                        "stroke": "fill", "border-color": "line", "border": "line", "border-bottom": "line",
                        "border-top": "line", "outline-color": "line", "accent-color": "accent",
                        "text-decoration-color": "line", "caret-color": "line"}.get(p)
                if not role:
                    continue
                for c in colors_in(resolve_vars(val, self.vars)):
                    if c[3] >= 0.5:
                        self.obs.append((hexof(c), c[3], role, kind, sel[:60]))


def selector_kind(sel: str) -> str:
    s = sel.lower()
    parts = [p.strip() for p in s.split(",")]
    if any(re.fullmatch(r"(:root|html|body|html\s+body|main|#__next|#root)", p) for p in parts):
        return "base"
    if re.search(r"\bbutton\b|\.btn|button|\bcta\b|\[type=.?submit|primary", s):
        return "button"
    if re.search(r"(^|[\s,>+~])a(\b|:|\[)|\blink\b", s):
        return "link"
    if re.search(r"\bh[1-3]\b|title|heading|display|hero", s):
        return "heading"
    if re.search(r"header|navbar|\bnav\b|logo|brand", s):
        return "header"
    return "other"


# ── static pass ──────────────────────────────────────────────────────────────

def static_scrape(url: str, timeout: int, warnings: list):
    final, status, headers, data = fetch(url, timeout=timeout)
    ctype = (headers.get("Content-Type") or "").lower()
    if ctype and "html" not in ctype:
        raise RuntimeError(f"the site answered with {ctype.split(';')[0]} instead of a web page")
    text = decode(data, headers)
    page = PageParser(final)
    try:
        page.feed(text)
        page.close()
    except Exception as e:  # malformed markup: keep what was parsed
        warnings.append(f"HTML parse stopped early: {e}")
    facts = CssFacts()
    sheets, gfonts = [], []
    for link in page.links:
        href = urllib.parse.urljoin(final, link["href"]) if link["href"] else ""
        if not href:
            continue
        if "fonts.googleapis.com" in href:
            gfonts.append(href)
            continue
        if "stylesheet" in link["rel"] or (link["as"] == "style" and "preload" in link["rel"]):
            sheets.append(href)
    css_texts = list(page.styles)
    fetched = 0
    for href in dict.fromkeys(sheets):
        if fetched >= 12:
            break
        try:
            _, _, h, body = fetch(href, timeout=timeout, max_bytes=4_000_000, accept="text/css,*/*;q=0.1")
            css = decode(body, h)
            fetched += 1
            css_texts.append((css, href))
            for imp in re.findall(r"@import\s+(?:url\()?[\"']?([^\"')\s;]+)", css)[:4]:
                iu = urllib.parse.urljoin(href, imp)
                if "fonts.googleapis.com" in iu:
                    gfonts.append(iu)
                    continue
                try:
                    _, _, h2, b2 = fetch(iu, timeout=timeout, max_bytes=2_000_000, accept="text/css")
                    css_texts.append((decode(b2, h2), iu))
                except Exception:
                    pass
        except Exception as e:
            warnings.append(f"stylesheet {href[:80]} not fetched ({e.__class__.__name__})")
    for item in css_texts:
        css, base = (item, final) if isinstance(item, str) else item
        for imp in re.findall(r"@import\s+(?:url\()?[\"']?(https://fonts\.googleapis\.com[^\"')\s;]+)", css):
            gfonts.append(imp)
        facts.feed(css, base)
    for tag, cls, style, ctx in page.inline:
        kind = "header" if (ctx["header"] or ctx["nav"]) else ("button" if re.search(r"btn|button|cta", cls, re.I) else "other")
        facts.feed(f"{tag}.{cls.split()[0] if cls.split() else 'x'} {{{style}}}", final)
        if kind != "other" and facts.obs:
            pass
    manifest = {}
    for link in page.links:
        if "manifest" in link["rel"] and link["href"]:
            try:
                _, _, _, body = fetch(urllib.parse.urljoin(final, link["href"]), timeout=timeout,
                                      max_bytes=500_000, accept="application/manifest+json,application/json")
                manifest = json.loads(body.decode("utf-8", "replace"))
            except Exception:
                pass
            break
    google_families = []
    for g in gfonts:
        for fam in re.findall(r"family=([^&:]+)", urllib.parse.unquote(g)):
            google_families.append(fam.replace("+", " ").split(":")[0].strip())
    return {"final_url": final, "status": status, "page": page, "facts": facts, "manifest": manifest,
            "google_families": list(dict.fromkeys(google_families)), "google_css": list(dict.fromkeys(gfonts))}


def static_logo_candidates(st):
    page, final = st["page"], st["final_url"]
    host_token = re.sub(r"[^a-z0-9]", "", (urllib.parse.urlsplit(final).hostname or "").removeprefix("www.").split(".")[0])
    cands = []
    for s in page.svgs[:60]:
        c, a = s["ctx"], s["attrs"]
        label = f"{a.get('id', '')} {a.get('class', '')} {a.get('aria-label', '')} {s['markup'][:400]}"
        score = (40 if c["home"] else 0) + (25 if (c["header"] or c["nav"]) else 0) + (30 if (c["hint"] or LOGO_HINT.search(label)) else 0)
        if host_token and len(host_token) > 2 and host_token in re.sub(r"[^a-z0-9]", "", label.lower()):
            score += 20
        if c["footer"]:
            score -= 15
        if len(s["markup"]) < 300:
            score -= 10
        if score >= 30:
            cands.append({"kind": "svg-inline", "markup": s["markup"], "score": score + 5, "how": "inline svg" +
                          (" in home link" if c["home"] else "") + (" in header" if c["header"] or c["nav"] else "")})
    for im in page.imgs[:120]:
        if not im["src"] or im["src"].startswith("data:image/gif"):
            continue
        c = im["ctx"]
        label = f"{im['alt']} {im['cls']} {im['id']} {im['src']}"
        score = (40 if c["home"] else 0) + (25 if (c["header"] or c["nav"]) else 0) + (30 if LOGO_HINT.search(label) else 0)
        if host_token and len(host_token) > 2 and host_token in re.sub(r"[^a-z0-9]", "", label.lower()):
            score += 20
        if c["footer"]:
            score -= 15
        if score >= 30:
            src = urllib.parse.urljoin(final, im["src"])
            cands.append({"kind": "svg-url" if re.search(r"\.svg(\?|$)", src) else "img-url", "url": src,
                          "score": score + (5 if src.endswith(".svg") else 0),
                          "how": "img" + (" in home link" if c["home"] else "") + (" in header" if c["header"] or c["nav"] else "")})
    icons = []
    for link in page.links:
        rel, href = link["rel"], link["href"]
        if not href:
            continue
        u = urllib.parse.urljoin(final, href)
        size = max([int(x) for x in re.findall(r"(\d+)x\d+", link["sizes"])] or [0])
        if "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel:
            icons.append({"url": u, "score": 50 + min(size, 512) / 50, "how": "apple-touch-icon"})
        elif "mask-icon" in rel:
            icons.append({"url": u, "score": 40, "how": "mask-icon (monochrome svg)", "color": link["color"]})
        elif "icon" in rel:
            svg = link["type"] == "image/svg+xml" or u.split("?")[0].endswith(".svg")
            icons.append({"url": u, "score": (45 if svg else 30) + min(size, 512) / 50, "how": "favicon" + (" svg" if svg else "")})
    for ic in (st["manifest"].get("icons") or [])[:10]:
        if ic.get("src"):
            size = max([int(x) for x in re.findall(r"(\d+)x\d+", ic.get("sizes", ""))] or [0])
            icons.append({"url": urllib.parse.urljoin(final, ic["src"]), "score": 42 + min(size, 512) / 50, "how": "manifest icon"})
    icons.append({"url": urllib.parse.urljoin(final, "/favicon.ico"), "score": 10, "how": "favicon.ico"})
    og = page.metas.get("og:image")
    if og:
        cands.append({"kind": "img-url", "url": urllib.parse.urljoin(final, og), "score": 5, "how": "og:image (usually a banner)"})
    cands.sort(key=lambda c: -c["score"])
    icons.sort(key=lambda c: -c["score"])
    return cands, icons


# ── render pass ─────────────────────────────────────────────────────────────

COLLECT_JS = r"""
async () => {
  const W = innerWidth, H = innerHeight;
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const g = cv.getContext('2d', { willReadFrequently: true });
  const rgba = css => {
    if (!css || css === 'transparent' || css === 'none') return null;
    g.clearRect(0, 0, 1, 1); g.fillStyle = 'rgba(0,0,0,0)'; g.fillStyle = css; g.fillRect(0, 0, 1, 1);
    const d = g.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255];
  };
  const hex = c => '#' + c.slice(0, 3).map(v => v.toString(16).padStart(2, '0')).join('');
  const vis = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false;
    if (el.checkVisibility) return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true, opacityProperty: true, visibilityProperty: true });
    const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0.05;
  };
  const paintedBg = el => {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e), c = rgba(cs.backgroundColor);
      if (c && c[3] >= 0.6) return hex(c);
      const bi = cs.backgroundImage || '';
      if (/gradient/.test(bi)) { const m = bi.match(/(rgba?\([^)]*\)|#[0-9a-f]{3,8}\b|oklch\([^)]*\)|hsla?\([^)]*\)|color\([^)]*\))/i); const c2 = m && rgba(m[1]); if (c2 && c2[3] >= 0.6) return hex(c2); }
      if (/url\(/.test(bi)) { const r = e.getBoundingClientRect(); if (r.width * r.height > W * H * 0.25) return 'image'; }
    }
    const root = rgba(getComputedStyle(document.documentElement).backgroundColor);
    return root && root[3] >= 0.6 ? hex(root) : '#ffffff';
  };

  // 1. What is actually painted behind the page, sampled on a grid over the first screen.
  const bg = {}; let n = 0;
  for (let gy = 0; gy < 20; gy++) for (let gx = 0; gx < 32; gx++) {
    const el = document.elementFromPoint((gx + 0.5) * W / 32, (gy + 0.5) * H / 20);
    let k = el ? paintedBg(el) : '#ffffff';
    if (el && /^(IMG|VIDEO|CANVAS|PICTURE|IFRAME)$/.test(el.tagName)) k = 'image';
    bg[k] = (bg[k] || 0) + 1; n++;
  }

  // 2. Text colours and fonts, weighted by how much text uses them.
  const text = {}, fonts = {};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node, seen = 0;
  while ((node = walker.nextNode()) && seen < 5000) {
    const s = node.textContent.trim(); if (s.length < 2) continue;
    const el = node.parentElement; if (!el || !vis(el)) continue;
    const r = el.getBoundingClientRect(); if (r.top > H * 1.6 || r.bottom < 0) continue;
    const cs = getComputedStyle(el), c = rgba(cs.color); if (!c || c[3] < 0.5) continue;
    const wgt = Math.min(s.length, 200) * (parseFloat(cs.fontSize) || 16) / 16;
    text[hex(c)] = (text[hex(c)] || 0) + wgt; fonts[cs.fontFamily] = (fonts[cs.fontFamily] || 0) + wgt; seen++;
  }

  // 3. Buttons and links: where brands put their accent.
  const ctas = [], links = {};
  for (const el of document.querySelectorAll('a, button, [role=button], input[type=submit], input[type=button]')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect(); if (r.top > H * 1.5 || r.bottom < 0) continue;
    const cs = getComputedStyle(el), b = rgba(cs.backgroundColor), fg = rgba(cs.color);
    const label = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    const buttonish = r.height >= 24 && r.height <= 96 && r.width >= 44 && r.width <= 560;
    const around = paintedBg(el.parentElement || document.body);
    if (buttonish && b && b[3] >= 0.6 && hex(b) !== around) {
      ctas.push({ bg: hex(b), color: fg ? hex(fg) : null, text: label, area: Math.round(r.width * r.height), top: Math.round(r.top), font: cs.fontFamily });
    } else if (el.tagName === 'A' && fg && fg[3] >= 0.6 && label) {
      links[hex(fg)] = (links[hex(fg)] || 0) + 1;
    }
  }

  // 4. Headline copy and the display font.
  let display = null, dsize = 0;
  for (const el of document.querySelectorAll('h1, h2, [class*=title], [class*=heading], [class*=hero] p, [class*=hero] span')) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect(); if (r.top > H * 1.2 || r.bottom < 0) continue;
    const sz = parseFloat(getComputedStyle(el).fontSize) || 0, t = el.innerText.trim();
    if (sz > dsize && t.length > 2 && t.length < 160) { dsize = sz; display = el; }
  }
  const h1 = [...document.querySelectorAll('h1')].find(vis) || display;
  let sub = '';
  if (h1) {
    const all = [...document.querySelectorAll('p, h2, [class*=sub], [class*=lead]')].filter(vis);
    const hr = h1.getBoundingClientRect();
    const next = all.find(p => p.getBoundingClientRect().top >= hr.bottom - 4 && p.getBoundingClientRect().top < hr.bottom + H * 0.5 && p.innerText.trim().length > 20);
    if (next) sub = next.innerText.trim().replace(/\s+/g, ' ').slice(0, 240);
  }
  const faces = [];
  for (const sheet of document.styleSheets) {
    let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
    for (const rule of rules || []) if (rule.type === CSSRule.FONT_FACE_RULE) {
      const fam = rule.style.getPropertyValue('font-family').replace(/["']/g, '').trim();
      const src = (rule.style.getPropertyValue('src').match(/url\(([^)]+)\)/g) || []).map(u => new URL(u.slice(4, -1).replace(/["']/g, ''), sheet.href || location.href).href);
      faces.push({ family: fam, src: src.slice(0, 3), weight: rule.style.getPropertyValue('font-weight'), style: rule.style.getPropertyValue('font-style') });
    }
  }

  // 5. The logo: the image or svg in the header that links home and says "logo".
  const host = location.hostname.replace(/^www\./, ''), token = host.split('.')[0].toLowerCase().replace(/[^a-z0-9]/g, '');
  const isHome = a => { try { const u = new URL(a.getAttribute('href') || '', location.href);
    return u.hostname.replace(/^www\./, '') === host && !u.search && /^(\/|\/index\.html?|\/[a-z]{2}(-[a-z]{2})?\/?)?$/i.test(u.pathname); } catch (e) { return false; } };
  const lab = el => !el || !el.getAttribute ? '' : [el.id, typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal),
    el.getAttribute('alt'), el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('data-testid'),
    el.querySelector && el.querySelector('title') ? el.querySelector('title').textContent : ''].filter(Boolean).join(' ');
  const cands = [];
  const pool = [...document.querySelectorAll('svg, img, [class*=logo], [id*=logo]')];
  for (const el of pool) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'svg' && el.parentElement && el.parentElement.closest('svg')) continue;
    let kind = tag === 'svg' ? 'svg-inline' : tag === 'img' ? 'img' : null, bgUrl = null;
    if (!kind) { const bi = getComputedStyle(el).backgroundImage; const m = bi && bi.match(/url\(["']?([^"')]+)/); if (!m) continue; kind = 'bg-image'; bgUrl = new URL(m[1], location.href).href; }
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.top > 280 || r.bottom < 0 || r.width < 16 || r.height < 10 || r.width > 720 || r.height > 240) continue;
    const a = el.closest('a'); let score = 0; const why = [];
    if (el.closest('header, [role=banner], nav, [class*=header], [class*=Header], [class*=navbar], [id*=header]')) { score += 25; why.push('in header'); }
    if (a && isHome(a)) { score += 40; why.push('links home'); }
    const txt = `${lab(el)} ${lab(a)} ${lab(el.parentElement)}`;
    if (/logo|brand|wordmark|logotype/i.test(txt)) { score += 30; why.push('named logo'); }
    if (token.length > 2 && txt.toLowerCase().replace(/[^a-z0-9]/g, '').includes(token)) { score += 20; why.push('names the site'); }
    if (/avatar|flag|badge|menu|hamburger|search|close|chevron|arrow|icon-/i.test(txt)) score -= 25;
    score += Math.max(0, 15 - r.left / 60) + (r.top < 140 ? 8 : 0) + (r.width / r.height > 1.6 ? 8 : 0);
    if (r.width < 26 && r.height < 26) score -= 25;
    if (tag === 'svg' && el.querySelectorAll('path, polygon, circle, rect, ellipse, text, use, g').length <= 1 && r.width < 30) score -= 15;
    cands.push({ el, kind, score, why: why.join(', '), rect: { x: r.left, y: r.top, w: r.width, h: r.height }, bgUrl });
  }
  cands.sort((p, q) => q.score - p.score);
  const bake = svg => {
    const clone = svg.cloneNode(true), src = [svg, ...svg.querySelectorAll('*')], dst = [clone, ...clone.querySelectorAll('*')];
    src.forEach((s, i) => {
      const d = dst[i]; if (!d || !d.style) return;
      const cs = getComputedStyle(s);
      for (const p of ['fill', 'stroke', 'stroke-width', 'opacity', 'fill-opacity', 'stroke-opacity', 'fill-rule', 'clip-rule', 'stop-color', 'stop-opacity'])
        { const v = cs.getPropertyValue(p); if (v) d.style.setProperty(p, v); }
      if (cs.display === 'none') d.setAttribute('display', 'none');
    });
    const r = svg.getBoundingClientRect();
    if (!clone.getAttribute('viewBox')) clone.setAttribute('viewBox', `0 0 ${r.width} ${r.height}`);
    clone.setAttribute('width', Math.round(r.width)); clone.setAttribute('height', Math.round(r.height));
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    for (const u of clone.querySelectorAll('use')) {
      const ref = u.getAttribute('href') || u.getAttribute('xlink:href');
      const target = ref && ref.startsWith('#') ? document.getElementById(ref.slice(1)) : null;
      if (target) { const grp = document.createElementNS('http://www.w3.org/2000/svg', 'g'); const tc = target.cloneNode(true);
        if (target.tagName.toLowerCase() === 'symbol') [...tc.childNodes].forEach(nd => grp.appendChild(nd)); else grp.appendChild(tc); u.replaceWith(grp); }
    }
    const xml = new XMLSerializer().serializeToString(clone);
    const missing = [...new Set([...xml.matchAll(/url\(["']?#([^"')]+)/g)].map(m => m[1]))].filter(id => !clone.querySelector('#' + CSS.escape(id)));
    if (missing.length) { const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
      for (const id of missing) { const d = document.getElementById(id); if (d) defs.appendChild(d.cloneNode(true)); } clone.prepend(defs); }
    return new XMLSerializer().serializeToString(clone);
  };
  const logos = cands.slice(0, 5).map(c => {
    const o = { kind: c.kind, score: Math.round(c.score), how: c.why, rect: c.rect };
    if (c.kind === 'svg-inline') o.markup = bake(c.el);
    else if (c.kind === 'img') o.url = c.el.currentSrc || c.el.src;
    else o.url = c.bgUrl;
    if (o.url && /\.svg(\?|#|$)|^data:image\/svg/i.test(o.url)) o.kind = 'svg-url';
    else if (o.url) o.kind = 'img-url';
    return o;
  });

  return {
    title: document.title, lang: document.documentElement.lang,
    themeColor: (document.querySelector('meta[name=theme-color]') || {}).content || null,
    colorScheme: getComputedStyle(document.documentElement).colorScheme,
    bg, bgTotal: n, text, fonts, ctas: ctas.slice(0, 40), links,
    bodyFont: getComputedStyle(document.body).fontFamily,
    displayFont: display ? getComputedStyle(display).fontFamily : null,
    h1: h1 ? h1.innerText.trim().replace(/\s+/g, ' ').slice(0, 200) : '', sub,
    loadedFaces: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/["']/g, '')),
    faces, logos,
  };
}
"""

DISMISS_JS = r"""
() => {
  const words = /^(accept|accept all|accept all cookies|allow all|allow cookies|agree|i agree|got it|ok|okay|accept cookies|continue)$/i;
  for (const b of document.querySelectorAll('button, a[role=button], [role=button]')) {
    const t = (b.innerText || '').trim();
    if (words.test(t)) { try { b.click(); return t; } catch (e) {} }
  }
  return null;
}
"""


async def render_scrape(b, url, out_dir: Path, timeout: int, warnings: list):
    page, errors = await _rise.new_page(b, viewport=(1440, 900))
    failed_css = []
    page.on("requestfailed", lambda r: failed_css.append(r.url) if r.resource_type == "stylesheet" else None)
    page.on("response", lambda r: failed_css.append(r.url)
            if r.request.resource_type == "stylesheet" and r.status >= 400 else None)
    try:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception as e:
            raise RuntimeError(f"page did not load in the browser: {str(e).splitlines()[0]}")
        ctype = ((resp.headers.get("content-type") if resp else "") or "").lower()
        if resp is not None and (resp.status >= 400 or ("html" not in ctype and ctype)):
            raise RuntimeError(f"the site answered HTTP {resp.status} ({ctype.split(';')[0] or 'no type'}) instead "
                               "of a web page; a proxy or bot wall is probably in the way")
        try:
            await page.wait_for_load_state("load", timeout=timeout * 1000)
        except Exception:
            warnings.append("page kept loading; used what had rendered")
        await page.wait_for_timeout(1200)
        try:
            if await page.evaluate(DISMISS_JS):
                await page.wait_for_timeout(600)
        except Exception:
            pass
        await page.evaluate("() => window.scrollTo(0, 0)")
        data = await page.evaluate(COLLECT_JS)
        try:
            await page.screenshot(path=str(out_dir / "screenshot.jpg"), type="jpeg", quality=82)
            data["screenshot"] = "screenshot.jpg"
        except Exception as e:
            warnings.append(f"no screenshot ({e.__class__.__name__})")
        data["final_url"] = page.url
        data["failed_css"] = list(dict.fromkeys(failed_css))
        data["trusted"] = not looks_unstyled(data)
        if data["failed_css"]:
            warnings.append(f"{len(data['failed_css'])} stylesheet(s) did not load in the browser "
                            f"(blocked or failing), e.g. {data['failed_css'][0][:90]}")
        if not data["trusted"]:
            warnings.append("the page rendered without its CSS, so the browser's colours and fonts were "
                            "ignored (static CSS used instead) and screenshot.jpg shows an unstyled page; "
                            "confirm the palette with the WebFetch fallback or a screenshot from the user")
        return data
    finally:
        await page.context.close()


def looks_unstyled(rd) -> bool:
    fam, _ = first_family(rd.get("bodyFont") or "")
    default_font = (fam or "").lower() in ("times new roman", "times", "")
    default_links = any(k in (rd.get("links") or {}) for k in ("#0000ee", "#551a8b"))
    return default_font and (default_links or bool(rd.get("failed_css")))


UTILITY = re.compile(r"^(skip|switch to|menu|search|close|cookie|accept|language|log ?in|sign ?in|english|"
                     r"toggle|open menu|dismiss|back to top)", re.I)


def ranked_ctas(rd):
    """Buttons on the first screen first, biggest first; utility buttons (menu, log in…) last."""
    ctas = list((rd or {}).get("ctas") or [])
    return sorted(ctas, key=lambda c: (bool(UTILITY.match(c.get("text") or "")), c.get("top", 0) > 900, -c.get("area", 0)))


def headline_cta(rd):
    """The call to action next to the headline: a non-utility button on the first screen, or ''."""
    for c in ranked_ctas(rd):
        if c.get("text") and not UTILITY.match(c["text"]) and c.get("top", 0) < 990:
            return c["text"]
    return ""


RASTER_HTML = """<!doctype html><html><head><style>html,body{margin:0;background:transparent}
#box{display:inline-block;padding:0}img{display:block}</style></head><body><div id=box><img id=l></div>
<script>
window.go = async (src, maxW, maxH) => {
  const im = document.getElementById('l');
  im.src = src; await im.decode();
  let w = im.naturalWidth || 0, h = im.naturalHeight || 0;
  if (!w || !h) { w = 1200; h = 360; }
  const s = Math.min(maxW / w, maxH / h);
  im.style.width = Math.round(w * s) + 'px'; im.style.height = Math.round(h * s) + 'px';
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const c = document.createElement('canvas'); c.width = Math.round(w * s); c.height = Math.round(h * s);
  const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(im, 0, 0, c.width, c.height);
  const d = g.getImageData(0, 0, c.width, c.height).data, hist = {};
  let opaque = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i + 3] < 200) continue; opaque++;
    const k = [d[i], d[i + 1], d[i + 2]].map(v => Math.min(255, Math.round(v / 16) * 16).toString(16).padStart(2, '0')).join('');
    hist[k] = (hist[k] || 0) + 1;
  }
  const colors = Object.entries(hist).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, v]) => ['#' + k, v / Math.max(1, opaque)]);
  return { w: c.width, h: c.height, colors, opaqueShare: opaque / (c.width * c.height), png: c.toDataURL('image/png') };
};
</script></body></html>"""


async def rasterize(b, src_bytes: bytes, mime: str, max_w=1200, max_h=360):
    """Any logo file → transparent PNG bytes + its dominant colours (browser does the decoding)."""
    page, _ = await _rise.new_page(b, viewport=(1300, 500))
    try:
        await page.set_content(RASTER_HTML)
        import base64
        src = f"data:{mime};base64," + base64.b64encode(src_bytes).decode()
        out = await page.evaluate("([s, w, h]) => window.go(s, w, h)", [src, max_w, max_h])
        return _rise.decode_data_url(out["png"]), out
    finally:
        await page.context.close()


# ── merge ────────────────────────────────────────────────────────────────────

def pick_theme(st, rd, logo_colors, warnings):
    """Choose bg / ink / accent / accent2 from both passes. Returns (theme, palette)."""
    facts = st["facts"] if st else None
    scores = {}
    evidence = {}

    def add(hexs, pts, why):
        if not hexs or not re.fullmatch(r"#[0-9a-f]{6}", hexs):
            return
        for k in list(scores):  # merge near-identical colours
            if dist(k, hexs) < 0.035:
                hexs = k
                break
        scores[hexs] = scores.get(hexs, 0) + pts
        evidence.setdefault(hexs, [])
        if why not in evidence[hexs] and len(evidence[hexs]) < 6:
            evidence[hexs].append(why)

    # Background
    bg = None
    if rd and rd.get("bg"):
        ranked = sorted(((k, v) for k, v in rd["bg"].items() if k != "image"), key=lambda kv: -kv[1])
        if ranked and ranked[0][1] / max(1, rd["bgTotal"]) >= 0.2:
            bg = ranked[0][0]
    if not bg and facts:
        for hexs, a, role, kind, ev in facts.obs:
            if kind == "base" and role == "bg":
                bg = hexs
                break
        if not bg:
            for hexs, a, role, kind, ev in facts.obs:
                if kind == "var" and role == "bg" and re.search(r"^--(color-)?(background|bg)$", ev):
                    bg = hexs
                    break
    if not bg and st and st["manifest"].get("background_color"):
        c = parse_color(st["manifest"]["background_color"])
        bg = hexof(c) if c else None
    bg = bg or "#ffffff"

    # Ink
    ink = None
    if rd and rd.get("text"):
        for k, v in sorted(rd["text"].items(), key=lambda kv: -kv[1]):
            if contrast(k, bg) >= 4.5:
                ink = k
                break
    if not ink and facts:
        for hexs, a, role, kind, ev in facts.obs:
            if kind == "base" and role == "text" and contrast(hexs, bg) >= 3:
                ink = hexs
                break
    ink = ink or ("#111111" if rel_lum(bg) > 0.4 else "#f5f5f5")

    # Accent candidates
    if rd:
        total_bg = max(1, rd.get("bgTotal", 1))
        for k, v in rd.get("bg", {}).items():
            if k != "image" and k != bg and v / total_bg >= 0.03:
                add(k, 3 + 12 * v / total_bg, f"painted area {v * 100 // total_bg}%")
        for i, c in enumerate(ranked_ctas(rd)):
            utility = bool(UTILITY.match(c.get("text") or ""))
            add(c["bg"], 1 if utility else 5 + (3 if i < 3 else 0) + min(3, c["area"] / 8000), f"button “{c['text'][:24]}”")
        for k, v in rd.get("links", {}).items():
            add(k, min(4, 1 + v * 0.4), "link colour")
        for k, v in rd.get("text", {}).items():
            if chroma(k) > 0.06:
                add(k, min(3, v / 400), "coloured text")
        if rd.get("themeColor"):
            c = parse_color(rd["themeColor"])
            if c:
                add(hexof(c), 3, "meta theme-color")
    if facts:
        counts = {}
        for hexs, a, role, kind, ev in facts.obs:
            if kind == "var" and role in ("accent", "link", "accent2"):
                add(hexs, accent_weight(ev) if role == "accent" else {"link": 2.5, "accent2": 2}[role], f"CSS {ev}")
            elif kind == "button" and role in ("bg", "line"):
                add(hexs, 1.5, "button CSS")
            else:
                counts[hexs] = counts.get(hexs, 0) + 1
        for hexs, n in counts.items():
            add(hexs, min(2.5, math.log1p(n) * 0.6), "used in CSS")
        mc = st["page"].metas.get("theme-color") or st["page"].metas.get("msapplication-tilecolor")
        if mc and (c := parse_color(mc)):
            add(hexof(c), 3, "meta theme-color")
        for link in st["page"].links:
            if "mask-icon" in link["rel"] and (c := parse_color(link["color"] or "")):
                add(hexof(c), 4, "mask-icon colour")
        if (c := parse_color(st["manifest"].get("theme_color", "") or "")):
            add(hexof(c), 3, "manifest theme_color")
    for hexs, share in logo_colors or []:  # the logo is the brand's own statement of colour
        if share >= 0.05 and chroma(hexs) >= 0.05:
            add(hexs, 6 + 10 * share, f"logo colour {share * 100:.0f}%")

    def usable(k):
        return dist(k, bg) > 0.09 and dist(k, ink) > 0.06

    chromatic = sorted(((k, v) for k, v in scores.items() if usable(k) and chroma(k) >= 0.05), key=lambda kv: -kv[1])
    neutral = sorted(((k, v) for k, v in scores.items() if usable(k) and chroma(k) < 0.05), key=lambda kv: -kv[1])
    monochrome = not chromatic
    if chromatic:
        accent = chromatic[0][0]
    elif neutral:
        accent = neutral[0][0]
        warnings.append("no brand colour found beyond neutrals: this looks like a monochrome brand, so "
                        "let contrast, type and texture carry the piece")
    else:
        accent = ink
        warnings.append("no accent colour found; accent falls back to the ink colour")
    accent2, derived = None, False
    for k, _ in chromatic[1:] + neutral:
        if dist(k, accent) > 0.1:
            accent2 = k
            break
    if not accent2:
        accent2 = mixhex(accent, bg, 0.45)
        derived = True
    palette = []
    for k, v in sorted(scores.items(), key=lambda kv: -kv[1])[:10]:
        role = "accent" if k == accent else "accent2" if k == accent2 else "other"
        palette.append({"hex": k, "role": role, "score": round(v, 1), "evidence": evidence.get(k, [])})
    palette = [{"hex": bg, "role": "bg", "score": None, "evidence": ["painted background" if rd else "CSS background"]},
               {"hex": ink, "role": "ink", "score": None, "evidence": ["most-used readable text colour" if rd else "CSS text colour"]}] + \
              [p for p in palette if p["hex"] not in (bg, ink)]
    theme = {"bg": bg, "ink": ink, "accent": accent, "accent2": accent2,
             "scheme": "dark" if rel_lum(bg) < 0.2 else "light", "monochrome": monochrome,
             "accent2_derived": derived}
    return theme, palette


def pick_fonts(st, rd):
    facts = st["facts"] if st else None
    heading = body = None
    klass_h = klass_b = "sans-serif"
    if rd:
        if rd.get("displayFont"):
            heading, klass_h = first_family(rd["displayFont"])
        if rd.get("bodyFont"):
            body, klass_b = first_family(rd["bodyFont"])
        if not body and rd.get("fonts"):
            body, klass_b = first_family(max(rd["fonts"].items(), key=lambda kv: kv[1])[0])
    if facts:
        # Without a browser, the most-declared family per role wins (a single odd rule shouldn't).
        tally = {}
        for kind, stack in facts.font_decls:
            fam, k = first_family(stack)
            if fam:
                tally.setdefault(kind, {}).setdefault(fam, [0, k])[0] += 1
                tally.setdefault("any", {}).setdefault(fam, [0, k])[0] += 1

        def top(kind):
            pool = tally.get(kind) or {}
            if not pool:
                return None, "sans-serif"
            fam, (n, k) = max(pool.items(), key=lambda kv: kv[1][0])
            return fam, k
        if not body:
            body, klass_b = top("base")
            if not body:
                body, klass_b = top("any")
        if not heading:
            fam, k = top("heading")
            if fam and (tally["heading"][fam][0] >= 2 or fam == body):
                heading, klass_h = fam, k
    heading = heading or body
    klass_h = klass_h if heading != body else klass_b
    faces = (st["facts"].font_faces if st else []) + ((rd or {}).get("faces") or [])
    google = set(st["google_families"]) if st else set()

    def describe(fam, klass):
        if not fam:
            return None
        files = []
        for f in faces:
            if clean_family(f["family"]).lower() == fam.lower():
                files += [s for s in f["src"] if s not in files]
        system = fam.lower() in SYSTEM
        on_google = fam in google or (not system and on_google_fonts(fam))
        fallback = None if on_google else (NEAREST.get(fam.lower()) or BY_CLASS.get(klass, "Inter"))
        if fallback and not on_google_fonts(fallback):
            fallback = BY_CLASS.get(klass, "Inter")
        return {"family": fam, "class": klass, "google": on_google, "system": system,
                "use": fam if on_google else fallback, "fallback": fallback, "files": files[:4]}
    h, b = describe(heading, klass_h), describe(body, klass_b)
    fams = [x["use"] for x in (h, b) if x and x.get("use")]
    css = None
    if fams:
        css = "https://fonts.googleapis.com/css2?" + "&".join(
            "family=" + urllib.parse.quote_plus(f) + ":wght@400;500;600;700" for f in dict.fromkeys(fams)) + "&display=block"
    return {"heading": h, "body": b, "google_css": css}


def slugify(url: str) -> str:
    host = urllib.parse.urlsplit(url).hostname or url
    return re.sub(r"[^a-z0-9]+", "-", host.lower().removeprefix("www.")).strip("-") or "site"


def site_name(st, rd, url):
    host = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.")
    token = host.split(".")[0]
    metas = st["page"].metas if st else {}
    for key in ("og:site_name", "application-name", "apple-mobile-web-app-title"):
        if metas.get(key):
            return metas[key].strip()
    if st and (st["manifest"].get("short_name") or st["manifest"].get("name")):
        return (st["manifest"].get("short_name") or st["manifest"]["name"]).strip()
    title = ((rd or {}).get("title") or (st["page"].title if st else "")).strip()
    parts = [p.strip() for p in re.split(r"\s[|–—\-·:•\\/»›]\s", title) if p.strip()]
    for p in parts:
        if re.sub(r"[^a-z0-9]", "", p.lower()) == re.sub(r"[^a-z0-9]", "", token.lower()):
            return p
    if parts:
        short = min(parts, key=len)
        if len(short) <= 24:
            return short
    return token.capitalize()


# ── one site ────────────────────────────────────────────────────────────────

async def scrape_site(url, out_root: Path, b, args):
    if not re.match(r"^https?://", url):
        url = "https://" + url
    slug = slugify(url)
    out = out_root / slug
    out.mkdir(parents=True, exist_ok=True)
    warnings = []
    loop = asyncio.get_running_loop()

    st = rd = None
    if args.mode in ("auto", "static"):
        try:
            st = await loop.run_in_executor(None, static_scrape, url, args.timeout, warnings)
        except urllib.error.HTTPError as e:
            warnings.append(f"static fetch: HTTP {e.code} (often a bot wall; the browser pass may still work)")
        except Exception as e:
            warnings.append(f"static fetch failed: {str(e)[:160]}")
    if args.mode in ("auto", "render") and b is not None:
        try:
            rd = await render_scrape(b, url, out, args.timeout, warnings)
        except Exception as e:
            warnings.append(f"browser pass failed: {str(e)[:200]}")
    if not st and not rd:
        for f in out.iterdir():  # leave no half-written brand folder behind
            f.unlink()
        out.rmdir()
        raise RuntimeError("could not read the site at all. If the network blocks it, use the WebFetch "
                           "fallback in references/brand-scraping.md; " + "; ".join(warnings))

    final = (rd or {}).get("final_url") or (st or {}).get("final_url") or url

    # Logo: prefer what the browser saw in the header, then the static candidates.
    cands = list((rd or {}).get("logos") or [])
    icons = []
    if st:
        scands, icons = static_logo_candidates(st)
        cands += scands
    logo_info, logo_colors = None, []
    for c in cands[:6]:
        try:
            if c.get("markup"):
                raw, mime = c["markup"].encode(), "image/svg+xml"
            else:
                _, _, h, raw = await loop.run_in_executor(None, lambda u=c["url"]: fetch(u, timeout=args.timeout, max_bytes=5_000_000, accept="image/*,*/*;q=0.5"))
                mime = (h.get("Content-Type") or "").split(";")[0] or ("image/svg+xml" if c["kind"] == "svg-url" else "image/png")
                if "svg" in mime or raw.lstrip()[:5] in (b"<svg ", b"<?xml"):
                    mime = "image/svg+xml"
            if b is not None:
                png, meta = await rasterize(b, raw, mime)
                if meta["opaqueShare"] < 0.005:
                    warnings.append(f"logo candidate ({c.get('how')}) rendered empty; skipped")
                    continue
                (out / "logo.png").write_bytes(png)
                logo_colors = meta["colors"]
                size = [meta["w"], meta["h"]]
            else:
                size = None
                (out / ("logo.svg" if mime == "image/svg+xml" else "logo-source" + (Path(urllib.parse.urlsplit(c.get("url", "")).path).suffix or ".png"))).write_bytes(raw)
            if mime == "image/svg+xml":
                (out / "logo.svg").write_bytes(raw)
            logo_info = {"file": "logo.png" if b is not None else None, "svg": "logo.svg" if mime == "image/svg+xml" else None,
                         "source": c.get("url") or "inline svg", "how": c.get("how") or c.get("kind"),
                         "size": size, "colors": [k for k, s in logo_colors if s >= 0.05]}
            break
        except Exception as e:
            warnings.append(f"logo candidate ({c.get('how') or c.get('kind')}) failed: {str(e)[:120]}")
    if not logo_info:
        warnings.append("no header logo found; check screenshot.jpg and add the real file by hand")
    icon_info = None
    for ic in icons[:4]:
        try:
            _, _, h, raw = await loop.run_in_executor(None, lambda u=ic["url"]: fetch(u, timeout=args.timeout, max_bytes=2_000_000, accept="image/*"))
            mime = (h.get("Content-Type") or "image/png").split(";")[0]
            if "svg" in mime or raw.lstrip()[:5] in (b"<svg ", b"<?xml"):
                mime = "image/svg+xml"
            if b is not None:
                png, _meta = await rasterize(b, raw, mime, 512, 512)
                (out / "icon.png").write_bytes(png)
                icon_info = {"file": "icon.png", "source": ic["url"], "how": ic["how"]}
            else:
                ext = ".svg" if mime == "image/svg+xml" else ".ico" if "icon" in mime else ".png"
                (out / f"icon{ext}").write_bytes(raw)
                icon_info = {"file": f"icon{ext}", "source": ic["url"], "how": ic["how"]}
            break
        except Exception:
            continue

    styled = rd if rd and rd.get("trusted", True) else None  # an unstyled render says nothing about the brand
    theme, palette = pick_theme(st, styled, logo_colors, warnings)
    fonts = await loop.run_in_executor(None, pick_fonts, st, styled)
    theme["font"] = (fonts["heading"] or {}).get("use") or "Inter"
    theme["fontBody"] = (fonts["body"] or {}).get("use") or theme["font"]
    for which in ("heading", "body"):
        f = fonts[which]
        if f and not f["google"] and not f["system"]:
            warnings.append(f"{which} font “{f['family']}” is not on Google Fonts; theme uses {f['use']} "
                            "(the site's own files are listed under fonts; check the licence before using them)")

    page = st["page"] if st else None
    metas = page.metas if page else {}
    static_cta = next((t for t in (page.buttons if page else []) if not UTILITY.match(t)), "")
    copy = {"headline": (styled or {}).get("h1") or (page.h1[0] if page and page.h1 else "") or (rd or {}).get("h1", ""),
            "subline": (styled or {}).get("sub") or metas.get("og:description") or metas.get("description") or "",
            "cta": headline_cta(styled) or ("" if styled else static_cta)}
    brand = {
        "schema": "rise-brand/1",
        "url": url, "final_url": final, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "+".join(x for x, ok in (("static", st), ("render", rd)) if ok),
        "name": site_name(st, rd, final),
        "description": metas.get("og:description") or metas.get("description") or "",
        "copy": copy,
        "theme": {k: theme[k] for k in ("bg", "ink", "accent", "accent2", "font", "fontBody")},
        "scheme": theme["scheme"], "monochrome": theme["monochrome"], "accent2_derived": theme["accent2_derived"],
        "palette": palette,
        "fonts": fonts,
        "logo": logo_info, "icon": icon_info,
        "logo_candidates": [{k: v for k, v in c.items() if k != "markup"} for c in cands[:6]],
        "screenshot": (rd or {}).get("screenshot"),
        "warnings": warnings,
    }
    (out / "brand.json").write_text(json.dumps(brand, indent=2, ensure_ascii=False), encoding="utf-8")
    return out, brand


def summary(out, brand):
    t = brand["theme"]
    f = brand["fonts"]
    lines = [f"{brand['url']} → {out / 'brand.json'}",
             f"  name     {brand['name']}",
             f"  theme    bg {t['bg']} · ink {t['ink']} · accent {t['accent']} · accent2 {t['accent2']}"
             + (" (derived)" if brand["accent2_derived"] else "") + (" · monochrome" if brand["monochrome"] else "")]
    for which in ("heading", "body"):
        x = f[which]
        if x:
            note = "Google Fonts" if x["google"] else ("system font" if x["system"] else f"not on Google Fonts → {x['use']}")
            lines.append(f"  {which:<8} {x['family']} ({note})")
    if brand["logo"]:
        lines.append(f"  logo     {brand['logo']['file'] or brand['logo'].get('svg')} ← {brand['logo']['how']}"
                     + (f" · colours {', '.join(brand['logo']['colors'])}" if brand['logo'].get('colors') else ""))
    if brand["icon"]:
        lines.append(f"  icon     {brand['icon']['file']} ← {brand['icon']['how']}")
    c = brand["copy"]
    if c.get("headline"):
        lines.append(f"  copy     “{c['headline'][:90]}”" + (f" · CTA “{c['cta'][:30]}”" if c.get("cta") else ""))
    if brand["screenshot"]:
        lines.append(f"  look at  {out / brand['screenshot']} and {out / 'logo.png'} before using them")
    for w in brand["warnings"]:
        lines.append(f"  note     {w}")
    return "\n".join(lines)


async def main_async(args):
    urls = list(args.urls)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                urls.append(line)
    urls = list(dict.fromkeys(urls))
    if args.limit:
        urls = urls[: args.limit]
    if not urls:
        raise _rise.RiseError("give at least one URL (or --file sites.txt)")
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    results, failures = [], []

    async def run_all(b):
        sem = asyncio.Semaphore(args.jobs)

        async def one(u):
            async with sem:
                try:
                    out, brand = await scrape_site(u, out_root, b, args)
                    results.append((out, brand))
                    print(summary(out, brand) + "\n", flush=True)
                except Exception as e:
                    failures.append((u, str(e)))
                    print(f"{u} ✘ {e}\n", flush=True)
        await asyncio.gather(*(one(u) for u in urls))

    if args.mode == "static":
        await run_all(None)
    else:
        try:
            async with _rise.browser() as b:
                await run_all(b)
        except _rise.RiseError as e:
            if args.mode == "render":
                raise
            print(f"(no browser: {str(e).splitlines()[0]} — running the static pass only)\n")
            await run_all(None)
    if len(urls) > 1:
        index = [{"url": br["url"], "slug": out.name, "name": br["name"], "theme": br["theme"]} for out, br in results]
        (out_root / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{len(results)} of {len(urls)} sites scraped → {out_root / 'index.json'}")
    if failures:
        print("failed:\n" + "\n".join(f"  {u}: {e[:200]}" for u, e in failures))
    if args.json and results:
        print(json.dumps(results[0][1], indent=2, ensure_ascii=False))
    return 0 if results else 1


def main():
    ap = argparse.ArgumentParser(description="Scrape a site's brand (logo, colours, fonts, copy) without Firecrawl.")
    ap.add_argument("urls", nargs="*", help="site URLs (https:// optional)")
    ap.add_argument("--file", help="text file with one URL per line")
    ap.add_argument("--out", default="brands", help="output folder; each site gets <out>/<slug>/ (default: brands)")
    ap.add_argument("--mode", choices=["auto", "static", "render"], default="auto",
                    help="auto = static + browser when available (default)")
    ap.add_argument("--limit", type=int, help="only the first N sites (test on 5 before running 100)")
    ap.add_argument("--jobs", type=int, default=3, help="sites in parallel (default 3)")
    ap.add_argument("--timeout", type=int, default=25, help="seconds per request (default 25)")
    ap.add_argument("--json", action="store_true", help="also print the first brand.json")
    args = ap.parse_args()
    sys.exit(_rise.run(main_async(args)))


if __name__ == "__main__":
    main()
