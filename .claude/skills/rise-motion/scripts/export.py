#!/usr/bin/env python3
"""Render a motion file frame by frame through its render(t) and encode MP4 (and GIF).

  python scripts/export.py motion/my-piece/index.html                     # every format in FORMATS
  python scripts/export.py motion/my-piece/index.html --formats 9:16 --loops 3 --gif
  python scripts/export.py motion/films/index.html --brands motion/films/brands --formats 1:1 --limit 5
  python scripts/export.py motion/reel/index.html --under clip.mp4 --under-rect 0,960,1080,960

Frames come from the same pure render(t) the preview uses, so the export is exact: no screen
recording, no dropped frames. When the page defines score(), its audio is rendered offline and
muxed in. --under puts a video (e.g. a talking-head clip) beneath the canvas; leave that area
transparent in render(). Writes <out>/<name>-<format>.mp4 plus a poster PNG of the first frame.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _rise  # noqa: E402

AUDIO_JS = r"""
async (seconds) => {
  const sr = 48000, len = Math.max(1, Math.ceil(seconds * sr));
  const oac = new OfflineAudioContext(2, len, sr);
  const out = oac.createGain(); out.connect(oac.destination);
  for (let k = 0; k * RISE.DURATION < seconds - 1e-6; k++) RISE.score(oac, k * RISE.DURATION, out);
  const buf = await oac.startRendering();
  const L = buf.getChannelData(0), R = buf.numberOfChannels > 1 ? buf.getChannelData(1) : L;
  const n = buf.length, bytes = new Uint8Array(44 + n * 4), v = new DataView(bytes.buffer);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + n * 4, true); str(8, 'WAVE'); str(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 2, true); v.setUint32(24, sr, true);
  v.setUint32(28, sr * 4, true); v.setUint16(32, 4, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, n * 4, true);
  let peak = 0;
  for (let i = 0; i < n; i++) for (const [c, ch] of [[0, L], [1, R]]) {
    const s = Math.max(-1, Math.min(1, ch[i])); peak = Math.max(peak, Math.abs(ch[i]));
    v.setInt16(44 + (i * 2 + c) * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return { wav: btoa(bin), peak };
}
"""


def has_audio(ffmpeg: str, path: Path) -> bool:
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    return re.search(r"Stream #\S+.*Audio:", r.stderr) is not None


def probe_duration(ffmpeg: str, path: Path) -> float | None:
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def ffmpeg_cmd(ffmpeg, out, w, h, fps, seconds, crf, audio=None, under=None, under_rect=None, under_audio=False,
               codec="mjpeg"):
    """Frames on stdin (input 0, JPEG or PNG) → H.264 MP4. Optional: a clip beneath the canvas, score audio."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "image2pipe", "-framerate", str(fps), "-c:v", codec, "-i", "-"]
    filters, vmap, alabels, idx = [], "0:v", [], 1
    if under:
        cmd += ["-stream_loop", "-1", "-i", str(under)]  # loops a short clip; -t cuts the output
        rx, ry, rw, rh = under_rect or (0, 0, w, h)
        filters += [f"[{idx}:v]fps={fps},scale={rw}:{rh}:force_original_aspect_ratio=increase,"
                    f"crop={rw}:{rh},setsar=1,setpts=PTS-STARTPTS[clip]",
                    f"color=c=black:s={w}x{h}:r={fps}[base]",
                    f"[base][clip]overlay={rx}:{ry}[bg]",
                    "[bg][0:v]overlay=0:0:format=auto:shortest=1,format=yuv420p[v]"]
        vmap = "[v]"
        if under_audio:
            alabels.append(f"{idx}:a")
        idx += 1
    if audio:
        cmd += ["-i", str(audio)]
        alabels.append(f"{idx}:a")
        idx += 1
    amap = alabels[0] if len(alabels) == 1 else None
    if len(alabels) > 1:
        filters.append("".join(f"[{a}]" for a in alabels) + f"amix=inputs={len(alabels)}:duration=longest:normalize=0[aout]")
        amap = "[aout]"
    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    cmd += ["-map", vmap]
    if amap:
        cmd += ["-map", amap, "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(fps),
            "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(out)]
    return cmd


def make_gif(ffmpeg, mp4: Path, gif: Path, width: int, fps: int):
    vf = (f"fps={fps},scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
          f"[b][p]paletteuse=dither=bayer:bayer_scale=4")
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp4), "-vf", vf, "-loop", "0", str(gif)],
                   check=True)


async def export_one(b, base, rel, html, fmt, args, overrides, out_dir: Path, name: str, ffmpeg: str, log, workers=1):
    page, errors, info = await _rise.open_motion(b, f"{base}/{rel}", overrides)
    # Extra pages render frames in parallel; render(t) is pure, so any page can draw any frame.
    pages = [page] + [(await _rise.open_motion(b, f"{base}/{rel}", overrides))[0] for _ in range(max(0, workers - 1))]
    try:
        w, h = _rise.size_for(fmt, info, args.size)
        if w % 2 or h % 2:
            raise _rise.RiseError(f"{w}x{h}: MP4 needs even width and height")
        fps = args.fps or info["FPS"]
        D = info["DURATION"]
        seconds = args.seconds or D * args.loops
        n = max(1, round(seconds * fps))
        out = out_dir / f"{name}-{_rise.fmt_slug(fmt)}.mp4"

        under, under_rect = None, None
        if args.under:
            under = Path(args.under).resolve()
        elif info.get("UNDER") and info["UNDER"].get("src"):
            under = (html.parent / info["UNDER"]["src"]).resolve()
        if under:
            if not under.exists():
                raise _rise.RiseError(f"--under clip not found: {under}")
            if args.under_rect:
                under_rect = [int(v) for v in args.under_rect.split(",")]
            elif info.get("UNDER") and info["UNDER"].get("rect"):
                under_rect = [int(v) for v in info["UNDER"]["rect"]]
        with tempfile.TemporaryDirectory() as tmp:
            audio = None
            if info["hasScore"] and not args.no_audio:
                a = await page.evaluate(AUDIO_JS, seconds)
                audio = Path(tmp) / "score.wav"
                audio.write_bytes(base64.b64decode(a["wav"]))
                if a["peak"] > 1.0:
                    log(f"  note: score peaks at {a['peak']:.2f} (> 1.0 clips); lower its gain")
            # JPEG q=0.95 frames are ~4× faster to capture than PNG and indistinguishable after H.264;
            # PNG keeps the alpha channel a clip underneath needs.
            lossless = bool(under) or args.lossless
            grab = ("([t, w, h]) => window.__rise.png(t, w, h)" if lossless
                    else "([t, w, h]) => window.__rise.jpeg(t, w, h, 0.95)")
            cmd = ffmpeg_cmd(ffmpeg, out, w, h, fps, seconds, args.crf, audio, under, under_rect,
                             under_audio=bool(under) and not args.no_audio and has_audio(ffmpeg, under),
                             codec="png" if lossless else "mjpeg")
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            loop = asyncio.get_running_loop()
            t0, shown = time.time(), -1
            poster = await page.evaluate("([t, w, h]) => window.__rise.png(t, w, h)", [0, w, h])
            (out_dir / f"{name}-{_rise.fmt_slug(fmt)}-poster.png").write_bytes(_rise.decode_data_url(poster))
            try:
                k = len(pages)
                for i in range(0, n, k):
                    batch = await asyncio.gather(*(pages[j].evaluate(grab, [((i + j) / fps) % D, w, h])
                                                   for j in range(min(k, n - i))))
                    for data in batch:
                        await loop.run_in_executor(None, proc.stdin.write, _rise.decode_data_url(data))
                    done_n = min(n, i + k)
                    pct = done_n * 100 // n
                    if pct // 25 != shown and args.verbose:
                        shown = pct // 25
                        log(f"  {name} {fmt}: {pct}% ({done_n}/{n} frames, {time.time() - t0:.0f}s)")
                proc.stdin.close()
            except BrokenPipeError:
                pass
            err = await loop.run_in_executor(None, proc.stderr.read)
            code = await loop.run_in_executor(None, proc.wait)
            if code != 0:
                raise _rise.RiseError(f"ffmpeg failed for {out.name}: {err.decode(errors='replace')[-800:]}")
        page_errs = [e for e in errors if e.startswith("uncaught")]
        if page_errs:
            log(f"  warning: the page threw while exporting: {page_errs[0][:200]}")
        gif = None
        if args.gif:
            gif = out.with_suffix(".gif")
            gw = args.gif_width or (720 if w >= h else 480)
            await loop.run_in_executor(None, make_gif, ffmpeg, out, gif, gw, min(fps, 20))
        took = time.time() - t0
        size = out.stat().st_size / 1e6
        log(f"✔ {out}  {w}×{h} · {seconds:.2f}s · {fps} fps · {n} frames · {size:.1f} MB · {took:.0f}s"
            + (" · with audio" if audio or (under and has_audio(ffmpeg, under) and not args.no_audio) else "")
            + (f"\n  {gif} ({gif.stat().st_size / 1e6:.1f} MB)" if gif else ""))
        return out
    finally:
        for p in pages:
            await p.context.close()


async def main_async(args):
    html = Path(args.file).resolve()
    if not html.exists():
        raise _rise.RiseError(f"no such file: {html}")
    ffmpeg = _rise.ffmpeg_or_die()
    if not _rise.ffmpeg_has(ffmpeg, "libx264"):
        raise _rise.RiseError("this ffmpeg has no libx264; pip install imageio-ffmpeg")
    root, rel = _rise.motion_url_parts(html, Path(args.root) if args.root else None)
    out_dir = Path(args.out).resolve() if args.out else html.parent / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    params = _rise.parse_params(args.param)

    jobs = []  # (name, overrides)
    if args.brands:
        folder = Path(args.brands)
        brand_files = sorted(p for p in folder.glob("*/brand.json"))
        if args.limit:
            brand_files = brand_files[: args.limit]
        if not brand_files:
            raise _rise.RiseError(f"no */brand.json under {folder}; run brand_scrape.py --out {folder} first")
        for bf in brand_files:
            jobs.append((bf.parent.name, _rise.build_overrides(bf, args.theme, params)))
    else:
        name = args.name or (html.parent.name if html.name == "index.html" else html.stem)
        jobs.append((name, _rise.build_overrides(args.brand, args.theme, params)))

    started = time.time()
    done, failed = [], []
    with _rise.serve(root) as base:
        async with _rise.browser() as b:
            probe_page, _, info = await _rise.open_motion(b, f"{base}/{rel}")
            await probe_page.context.close()
            formats = [f.strip() for f in args.formats.split(",")] if args.formats else list(info["FORMATS"])
            jobs_n = max(1, min(args.jobs, len(jobs) * len(formats)))
            workers = args.workers or max(1, min(4, (os.cpu_count() or 2) // jobs_n))
            sem = asyncio.Semaphore(jobs_n)

            async def run(name, ov, fmt):
                async with sem:
                    try:
                        done.append(await export_one(b, base, rel, html, fmt, args, ov, out_dir, name, ffmpeg, print, workers))
                    except Exception as e:
                        failed.append((name, fmt, str(e)))
                        print(f"✘ {name} {fmt}: {e}")
            await asyncio.gather(*(run(n, ov, f) for n, ov in jobs for f in formats))
    print(f"{len(done)} file(s) in {time.time() - started:.0f}s → {out_dir}")
    if failed:
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="Export a motion file to MP4/GIF through its render(t).")
    ap.add_argument("file", help="the motion HTML file")
    ap.add_argument("--formats", help="comma list, e.g. 16:9,9:16 (default: the file's FORMATS)")
    ap.add_argument("--size", help="WxH override for every format")
    ap.add_argument("--fps", type=int, help="frames per second (default: the file's FPS)")
    ap.add_argument("--loops", type=int, default=1, help="how many loops to render (default 1)")
    ap.add_argument("--seconds", type=float, help="exact length in seconds (overrides --loops)")
    ap.add_argument("--crf", type=int, default=20,
                    help="x264 quality, lower = better and bigger (default 20; 18 for masters, 23 for previews)")
    ap.add_argument("--gif", action="store_true", help="also write a GIF next to each MP4")
    ap.add_argument("--gif-width", type=int, help="GIF width in px (default 720 landscape, 480 portrait)")
    ap.add_argument("--out", help="output folder (default: exports/ next to the file)")
    ap.add_argument("--name", help="file name stem (default: the piece's folder name)")
    ap.add_argument("--root", help="folder to serve (default: the file's folder)")
    ap.add_argument("--brand", help="brand.json (or folder) to inject: theme, name, logo")
    ap.add_argument("--brands", help="folder of <slug>/brand.json: one export per brand (Level 7)")
    ap.add_argument("--limit", type=int, help="with --brands: only the first N (test on 5 first)")
    ap.add_argument("--jobs", type=int, default=2, help="exports in parallel (default 2)")
    ap.add_argument("--workers", type=int, help="browser pages rendering frames per export (default: CPU cores / jobs, max 4)")
    ap.add_argument("--lossless", action="store_true", help="PNG frames into the encoder instead of JPEG q=0.95 (slower)")
    ap.add_argument("--theme", help='JSON merged into THEME, e.g. \'{"accent": "#ff3b1f"}\'')
    ap.add_argument("--param", action="append", help="KEY=VALUE merged into PARAMS (repeatable)")
    ap.add_argument("--under", help="video to place beneath the canvas (Level 3 reels)")
    ap.add_argument("--under-rect", help="x,y,w,h of the clip in canvas pixels (default: RISE.UNDER.rect or full frame)")
    ap.add_argument("--no-audio", action="store_true", help="skip score() audio and the clip's sound")
    ap.add_argument("--quiet", dest="verbose", action="store_false", help="no progress lines")
    args = ap.parse_args()
    sys.exit(_rise.run(main_async(args)))


if __name__ == "__main__":
    main()
