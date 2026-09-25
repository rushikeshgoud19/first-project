#!/usr/bin/env python3
"""Check that this machine can run the rise-motion pipeline, and say how to fix what's missing.

  python scripts/doctor.py

Checks Python, Playwright, a Chromium/Chrome binary, a real render of assets/template.html
(including its Google Fonts), and ffmpeg with H.264. Exit code 0 means everything works.
"""
from __future__ import annotations

import asyncio
import importlib.metadata
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _rise  # noqa: E402

OK, WARN, BAD = "ok  ", "warn", "FAIL"


def line(status, what, detail=""):
    print(f"[{status}] {what}" + (f" — {detail}" if detail else ""))


async def smoke_test():
    """Open the template, wait for its fonts, draw one frame. Returns (ok, detail)."""
    template = _rise.SKILL_DIR / "assets" / "template.html"
    root, rel = _rise.motion_url_parts(template)
    with _rise.serve(root) as base:
        async with _rise.browser() as b:
            page, errors, info = await _rise.open_motion(b, f"{base}/{rel}")
            t0 = time.time()
            await page.evaluate("() => { __rise.draw(1.0, 640, 360); }")
            ms = (time.time() - t0) * 1000
            fonts = await page.evaluate("""() => RISE.FONTS.map(f => {
                const fam = f.match(/(?:"([^"]+)"|'([^']+)'|([\\w -]+))\\s*$/);
                const name = fam ? (fam[1] || fam[2] || fam[3]).trim() : f;
                const faces = [...document.fonts].filter(x => x.family.replace(/["']/g, '') === name);
                return { font: f, name, loaded: faces.some(x => x.status === 'loaded') };
            })""")
            return errors, fonts, ms, b.version


def main():
    problems = 0
    print("rise-motion doctor\n")

    v = sys.version_info
    if v >= (3, 9):
        line(OK, f"python {v.major}.{v.minor}.{v.micro}")
    else:
        line(BAD, f"python {v.major}.{v.minor}", "needs 3.9 or newer")
        problems += 1

    try:
        pw = importlib.metadata.version("playwright")
        line(OK, f"playwright {pw}")
        have_pw = True
    except importlib.metadata.PackageNotFoundError:
        line(BAD, "playwright is not installed", "pip install playwright")
        problems += 1
        have_pw = False

    chrome = _rise.find_chrome()
    if chrome:
        line(OK, "browser", chrome)
    else:
        line(WARN, "no Chrome/Chromium found on disk",
             "Playwright will try its own; if that fails: python -m playwright install chromium "
             "(or install Google Chrome, or set RISE_CHROME=/path/to/chrome)")

    if _rise.route_through_python():
        line(OK, "network", f"HTTPS proxy {_rise.proxy_url()} — browser requests are fetched through Python "
                            "so the proxy's certificate is trusted")

    if have_pw:
        try:
            errors, fonts, ms, version = asyncio.run(smoke_test())
            line(OK, f"render test: Chromium {version} drew a frame in {ms:.0f} ms")
            for f in fonts:
                if f["loaded"]:
                    line(OK, f"font {f['name']!r} loaded")
                else:
                    line(WARN, f"font {f['name']!r} did not load",
                         "Google Fonts may be blocked on this network. Pieces will fall back to system "
                         "fonts until fonts.googleapis.com and fonts.gstatic.com are reachable "
                         "(or put .woff2 files next to the motion file and load them with @font-face).")
            for e in errors:
                line(WARN, "page reported", e)
        except _rise.RiseError as e:
            line(BAD, "render test failed", str(e))
            problems += 1
        except Exception as e:
            line(BAD, "render test crashed", repr(e))
            problems += 1

    ff = _rise.find_ffmpeg()
    if not ff:
        line(BAD, "ffmpeg not found", "pip install imageio-ffmpeg  (needed for MP4/GIF export and walls)")
        problems += 1
    else:
        try:
            ver = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, encoding="utf-8", errors="replace",
                                 timeout=30).stdout.split("\n")[0]
        except Exception:
            ver = "ffmpeg"
        if _rise.ffmpeg_has(ff, "libx264"):
            line(OK, "ffmpeg with libx264", f"{ver.split(' Copyright')[0]} ({ff})")
        else:
            line(BAD, "ffmpeg has no libx264 encoder", "pip install imageio-ffmpeg  (ships a full build)")
            problems += 1

    print()
    if problems:
        print(f"{problems} problem(s) to fix before rendering. Install everything in one go with:\n"
              "  pip install playwright imageio-ffmpeg\n"
              "and, only if no Chrome/Chromium is installed:\n"
              "  python -m playwright install chromium")
        sys.exit(1)
    print("all good: brand scraping, frame checks and exports will work here.")


if __name__ == "__main__":
    main()
