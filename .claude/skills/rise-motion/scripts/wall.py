#!/usr/bin/env python3
"""Tile many clips into one wall video (Level 7: a hundred films in, one 10×10 wall out).

  python scripts/wall.py motion/films/exports/*-1x1.mp4 --cols 10 --out motion/films/wall.mp4
  python scripts/wall.py motion/films/exports --cols 5 --tile 384 --gap 4 --seconds 8

Clips shorter than the wall loop; empty cells are filled with --bg. Default tile size fits the
wall into 1920 px wide.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _rise  # noqa: E402


def duration(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def main():
    ap = argparse.ArgumentParser(description="Tile clips into a grid video.")
    ap.add_argument("clips", nargs="+", help="video files, or folders of .mp4")
    ap.add_argument("--cols", type=int, help="columns (default: square-ish grid)")
    ap.add_argument("--tile", help="tile size: 216 (square) or 384x216 (default: fit 1920 px wide)")
    ap.add_argument("--gap", type=int, default=0, help="px between tiles (default 0)")
    ap.add_argument("--bg", default="#000000", help="background / empty-cell colour (default #000000)")
    ap.add_argument("--seconds", type=float, help="wall length (default: the longest clip)")
    ap.add_argument("--stagger", type=float, default=0.0,
                    help="seconds each tile starts after the previous one, so reveals ripple across the wall "
                         "instead of all blanking at once (e.g. 0.08 for a 10×10 wall)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--out", default="wall.mp4")
    args = ap.parse_args()

    try:
        ffmpeg = _rise.ffmpeg_or_die()
    except _rise.RiseError as e:
        sys.exit(f"error: {e}")
    files = []
    for c in args.clips:
        p = Path(c)
        files += sorted(p.glob("*.mp4")) if p.is_dir() else [p]
    files = [f for f in files if f.exists() and f.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")]
    if not files:
        sys.exit("error: no clips found")
    n = len(files)
    cols = args.cols or math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    if args.tile:
        m = re.fullmatch(r"(\d+)(?:x(\d+))?", args.tile)
        if not m:
            sys.exit("error: --tile must look like 216 or 384x216")
        tw, th = int(m.group(1)), int(m.group(2) or m.group(1))
    else:
        tw = (1920 - args.gap * (cols - 1)) // cols
        th = tw
    tw, th = tw - tw % 2, th - th % 2
    W, H = cols * tw + (cols - 1) * args.gap, rows * th + (rows - 1) * args.gap
    W, H = W + W % 2, H + H % 2
    durations = [duration(ffmpeg, f) or 0.0 for f in files]
    seconds = args.seconds or max(durations) or 8.0

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for i, f in enumerate(files):
        offset = (i * args.stagger) % durations[i] if args.stagger and durations[i] else 0.0
        cmd += ["-stream_loop", "-1"] + (["-ss", f"{offset:.3f}"] if offset else []) + ["-i", str(f)]
    color = args.bg.lstrip("#")
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]fps={args.fps},scale={tw}:{th}:force_original_aspect_ratio=increase,"
                     f"crop={tw}:{th},setsar=1,trim=duration={seconds:.3f},setpts=PTS-STARTPTS[v{i}]")
    if n == 1:
        parts.append(f"[v0]pad={W}:{H}:0:0:color=0x{color}[out]")
    else:
        layout = "|".join(f"{(i % cols) * (tw + args.gap)}_{(i // cols) * (th + args.gap)}" for i in range(n))
        parts.append("".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={layout}:fill=0x{color}[grid]")
        parts.append(f"[grid]pad={W}:{H}:0:0:color=0x{color}[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
            "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(args.out)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: ffmpeg failed: {r.stderr[-800:]}")
    out = Path(args.out)
    print(f"✔ {out}  {cols}×{rows} grid of {n} clips · {W}×{H} · {seconds:.2f}s · "
          f"{out.stat().st_size / 1e6:.1f} MB · {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
