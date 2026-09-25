"""Shared plumbing for the rise-motion scripts.

- find a Chromium/Chrome binary (Playwright's own, the system's, or $RISE_CHROME)
- serve a folder over http://127.0.0.1 so a page can draw its own files onto a canvas
  without tainting it (file:// pages can't read their canvas back)
- when an HTTPS proxy is configured (corporate networks, Claude Code cloud sessions), fetch the
  page's outside requests through Python, which already trusts the proxy's CA; Chromium on Linux
  ignores SSL_CERT_FILE and would fail with ERR_CERT_AUTHORITY_INVALID
- find ffmpeg (system or the imageio-ffmpeg wheel)
- open a motion file and draw frames through its window.RISE contract
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import functools
import glob
import http.server
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FORMAT_SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


class RiseError(Exception):
    """A problem the user (or Claude) can fix; printed without a traceback."""


# ── dependencies ─────────────────────────────────────────────────────────────

def async_playwright():
    try:
        from playwright.async_api import async_playwright as ap
    except ImportError:
        raise RiseError("Playwright for Python is missing. Install it with:\n"
                        "  pip install playwright\n"
                        "then run  python scripts/doctor.py  to check the rest.")
    return ap


def _playwright_roots():
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers",
             "~/.cache/ms-playwright", "~/Library/Caches/ms-playwright",
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")]
    return [Path(os.path.expanduser(r)) for r in roots if r and r != "0"]


def find_chrome() -> str | None:
    """A Chromium-family browser Playwright can drive, or None to let Playwright pick its own."""
    env = os.environ.get("RISE_CHROME") or os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    patterns = ["chromium-*/chrome-linux*/chrome",
                "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
                "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
                "chromium-*/chrome-win*/chrome.exe"]
    found = []
    for root in _playwright_roots():
        for pat in patterns:
            found += glob.glob(str(root / pat))
    if found:
        def revision(p):
            m = re.search(r"chromium-(\d+)", p)
            return int(m.group(1)) if m else 0
        return max(found, key=revision)
    system = {
        "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                   "/Applications/Chromium.app/Contents/MacOS/Chromium",
                   "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                   "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
        "Windows": [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
    }.get(platform.system(), [])
    for p in system:
        if Path(p).exists():
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "microsoft-edge", "brave-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def find_ffmpeg() -> str | None:
    env = os.environ.get("RISE_FFMPEG")
    if env and Path(env).exists():
        return env
    try:  # a full static build ships inside the imageio-ffmpeg wheel
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    # Playwright's bundled ffmpeg is a cut-down build without libx264, so it is not used.
    return shutil.which("ffmpeg")


def ffmpeg_or_die() -> str:
    exe = find_ffmpeg()
    if not exe:
        raise RiseError("ffmpeg is missing. Install it with:\n  pip install imageio-ffmpeg\n"
                        "(or your system's ffmpeg, e.g. `brew install ffmpeg`)")
    return exe


# ── network ─────────────────────────────────────────────────────────────────

def proxy_url() -> str | None:
    for k in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        if os.environ.get(k):
            return os.environ[k]
    return None


def route_through_python() -> bool:
    mode = os.environ.get("RISE_ROUTE", "auto").lower()
    if mode in ("python", "direct"):
        return mode == "python"
    return proxy_url() is not None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Hand redirects back to Chromium so relative URLs resolve against the final address.
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)
_pool = ThreadPoolExecutor(max_workers=8)
_DROP_REQ = {"host", "connection", "accept-encoding", "content-length", "if-none-match",
             "if-modified-since", "upgrade-insecure-requests", "proxy-connection"}
_DROP_RESP = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length",
              "upgrade", "proxy-authenticate", "proxy-connection", "strict-transport-security",
              "alt-svc"}


def _fetch(url, method, headers, body, timeout):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with _opener.open(req, timeout=timeout) as r:
            return r.status, list(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:  # includes the 3xx we refused to follow
        return e.code, list(e.headers.items()), e.read()


async def _python_route(route, block=()):
    req = route.request
    url = req.url
    if not url.startswith(("http://", "https://")) or url.startswith(("http://127.0.0.1", "http://localhost")):
        return await route.continue_()
    if req.resource_type in block:
        return await route.abort()
    try:
        headers = {k: v for k, v in (await req.all_headers()).items()
                   if not k.startswith(":") and k.lower() not in _DROP_REQ}
        status, hdrs, body = await asyncio.get_running_loop().run_in_executor(
            _pool, _fetch, url, req.method, headers, req.post_data_buffer, 30)
    except Exception:
        return await route.abort("failed")
    out = {}
    for k, v in hdrs:
        if k.lower() in _DROP_RESP or k.lower() == "set-cookie":
            continue
        out[k] = v
    if not any(k.lower() == "access-control-allow-origin" for k in out):
        out["access-control-allow-origin"] = "*"
    await route.fulfill(status=status, headers=out, body=body)


# ── local file server ───────────────────────────────────────────────────────

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
                      ".svg": "image/svg+xml", ".webp": "image/webp", ".woff2": "font/woff2",
                      ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf",
                      ".mp4": "video/mp4", ".webm": "video/webm", ".wav": "audio/wav", ".mp3": "audio/mpeg"}

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


@contextlib.contextmanager
def serve(directory):
    """Serve `directory` on a random localhost port for the duration of the block."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


# ── browser ─────────────────────────────────────────────────────────────────

LAUNCH_ARGS = ["--font-render-hinting=none", "--hide-scrollbars", "--mute-audio",
               "--autoplay-policy=no-user-gesture-required"]


@contextlib.asynccontextmanager
async def browser():
    ap = async_playwright()
    async with ap() as p:
        exe = find_chrome()
        try:
            b = await p.chromium.launch(executable_path=exe, args=LAUNCH_ARGS) if exe \
                else await p.chromium.launch(args=LAUNCH_ARGS)
        except Exception as e:
            first = str(e).strip().splitlines()[0] if str(e).strip() else repr(e)
            raise RiseError(f"Chromium would not start ({first}).\n"
                            "Fix one of: install Google Chrome, set RISE_CHROME=/path/to/chrome, "
                            "or run  python -m playwright install chromium")
        try:
            yield b
        finally:
            await b.close()


async def new_page(b, viewport=(1280, 720), init_script=None, block=(), scale=1):
    """A page in a fresh context, with outside requests routed through Python when needed.
    Returns (page, errors) where errors collects uncaught exceptions and console errors."""
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]},
                              device_scale_factor=scale)
    if route_through_python():
        await ctx.route("**/*", functools.partial(_python_route, block=tuple(block)))
    elif block:
        async def _block(route):
            if route.request.resource_type in block:
                await route.abort()
            else:
                await route.continue_()
        await ctx.route("**/*", _block)
    if init_script:
        await ctx.add_init_script(init_script)
    page = await ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"uncaught: {e}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
    return page, errors


# ── motion files ────────────────────────────────────────────────────────────

# Injected into every motion page by the scripts. Keeps the drawing canvas and the frame
# reset in one place so check.py and export.py see exactly the same pixels.
DRAW_JS = r"""
() => {
  if (window.__rise) return;
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  window.__rise = {
    canvas, ctx,
    draw(t, w, h) {
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      if (ctx.reset) ctx.reset(); else { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, w, h); }
      ctx.save();
      RISE.render(ctx, t, RISE.THEME, w, h);
      ctx.restore();
      return canvas;
    },
    png(t, w, h) { return this.draw(t, w, h).toDataURL('image/png'); },
    jpeg(t, w, h, q) { return this.draw(t, w, h).toDataURL('image/jpeg', q || 0.9); },
  };
}
"""


def motion_url_parts(html_path: Path, root: Path | None = None):
    """(folder to serve, path of the page inside it). The page's own folder by default."""
    html_path = html_path.resolve()
    root = (root or html_path.parent).resolve()
    try:
        rel = html_path.relative_to(root)
    except ValueError:
        raise RiseError(f"{html_path} is not inside --root {root}")
    return root, rel.as_posix()


async def open_motion(b, url, overrides=None, viewport=(1280, 720)):
    """Load a motion page in capture mode and wait for RISE.ready. Returns (page, errors, info)."""
    init = None
    if overrides:
        init = "window.RISE_OVERRIDES = " + json.dumps(overrides) + ";"
    page, errors = await new_page(b, viewport=viewport, init_script=init)
    sep = "&" if "?" in url else "?"
    try:
        await page.goto(url + sep + "capture=1", wait_until="load", timeout=90000)
    except Exception as e:
        raise RiseError(f"could not load {url}: {e}")
    has = await page.evaluate("() => typeof window.RISE === 'object' && window.RISE !== null && typeof RISE.render === 'function'")
    if not has:
        detail = ("\n  " + "\n  ".join(errors[:5])) if errors else ""
        raise RiseError("the page does not expose window.RISE.render. Start from assets/template.html "
                        "(or keep its harness block) so the scripts can draw frames." + detail)
    try:
        await page.evaluate("() => Promise.race([RISE.ready, new Promise((_, no) => setTimeout(() => no(new Error('RISE.ready did not settle in 60s')), 60000))])")
    except Exception as e:
        errors.append(f"RISE.ready failed: {e}")
    await page.evaluate(DRAW_JS)
    info = await page.evaluate("""() => ({
      DURATION: +RISE.DURATION, FPS: +(RISE.FPS || 30),
      FORMATS: RISE.FORMATS || ['16:9'], SIZES: RISE.SIZES || {},
      THEME: RISE.THEME || {}, FONTS: RISE.FONTS || [],
      hasScore: typeof RISE.score === 'function', UNDER: RISE.UNDER || null,
      title: document.title })""")
    if not info["DURATION"] or info["DURATION"] <= 0:
        raise RiseError("RISE.DURATION must be a positive number of seconds")
    return page, errors, info


def size_for(fmt: str, info: dict, override: str | None = None):
    if override:
        m = re.fullmatch(r"(\d+)x(\d+)", override)
        if not m:
            raise RiseError(f"--size must look like 1920x1080, got {override!r}")
        return int(m.group(1)), int(m.group(2))
    sizes = info.get("SIZES") or {}
    if fmt in sizes:
        w, h = sizes[fmt]
        return int(w), int(h)
    if fmt in FORMAT_SIZES:
        return FORMAT_SIZES[fmt]
    m = re.fullmatch(r"(\d+):(\d+)", fmt)
    if m:  # any other ratio: 1080 on the short side
        a, c = int(m.group(1)), int(m.group(2))
        return (round(1080 * a / c), 1080) if a >= c else (1080, round(1080 * c / a))
    raise RiseError(f"unknown format {fmt!r}; use 16:9, 9:16, 1:1, 4:5 or W:H")


def fmt_slug(fmt: str) -> str:
    return fmt.replace(":", "x")


def decode_data_url(data_url: str) -> bytes:
    return base64.b64decode(data_url.split(",", 1)[1])


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
         ".webp": "image/webp", ".gif": "image/gif", ".ico": "image/x-icon", ".avif": "image/avif"}


def data_url(path: Path) -> str:
    mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def parse_params(pairs) -> dict:
    """['title=Hello', 'count=3'] → {'title': 'Hello', 'count': 3} (values parsed as JSON when they can be)."""
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise RiseError(f"--param expects KEY=VALUE, got {pair!r}")
        k, v = pair.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def build_overrides(brand=None, theme=None, params=None):
    """window.RISE_OVERRIDES from a brand.json (theme + name + real logo), a theme JSON and params."""
    o = {}
    if brand:
        p = Path(brand)
        if p.is_dir():
            p = p / "brand.json"
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise RiseError(f"could not read brand file {p}: {e}")
        o["theme"] = {k: v for k, v in (data.get("theme") or {}).items() if v not in (None, "")}
        b = {"name": data.get("name") or "", "copy": data.get("copy") or {}}
        logo = (data.get("logo") or {}).get("file")
        if logo and (p.parent / logo).exists():
            b["logo"] = data_url(p.parent / logo)
        o["brand"] = b
    if theme:
        try:
            o.setdefault("theme", {}).update(json.loads(theme) if isinstance(theme, str) else theme)
        except json.JSONDecodeError as e:
            raise RiseError(f"--theme must be JSON like '{{\"accent\": \"#ff3b1f\"}}': {e}")
    if params:
        o["params"] = params
    return o or None


def run(coro):
    """asyncio.run with RiseError printed cleanly."""
    try:
        return asyncio.run(coro)
    except RiseError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)


def ffmpeg_has(exe: str, encoder: str) -> bool:
    try:
        out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
        return re.search(rf"\b{re.escape(encoder)}\b", out) is not None
    except Exception:
        return False
