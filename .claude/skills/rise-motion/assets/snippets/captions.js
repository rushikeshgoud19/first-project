/* ── Word-timed captions (Level 3) ─────────────────────────────────────────
   Paste into the helpers section of a motion file. Pure: the caption on screen
   is a function of t, so it scrubs, loops and exports exactly.

   WORDS comes from the user's transcript tool (CapCut, Descript, Premiere, or Whisper
   with word timestamps): seconds from the start of the clip.
     const WORDS = [{ w: 'Stop', s: 0.12, e: 0.38 }, { w: 'using', s: 0.38, e: 0.61 }, …];
     const GROUPS = captionGroups(WORDS);            // once, outside render
   Then inside render():
     captions(ctx, t, GROUPS, { x: S.cx, y: h * 0.86, maxWidth: S.safe.w, size: 96 * u,
                                look: 'boxed', theme });
   Looks: 'serif'  editorial italic serif, the spoken word in the accent
          'boxed'  heavy sans on ink boxes, the spoken word's box in the accent
          'clean'  bold sans with a soft shadow, the spoken word underlined and lifted
   Load the fonts the look uses (FONTS + the Google Fonts <link>):
     serif → THEME.font (e.g. Newsreader, italic 500) · boxed/clean → THEME.fontBody (e.g. Inter 800)
   check.py skips the 1.2 s hold rule for captions (they follow speech), via ctx.riseRole. */

function captionGroups(words, maxWords = 3, pause = 0.35) {
  const groups = [];
  let cur = [];
  words.forEach((wd, i) => {
    cur.push(wd);
    const next = words[i + 1];
    if (cur.length >= maxWords || /[.,!?;:]$/.test(wd.w) || !next || next.s - wd.e > pause) { groups.push(cur); cur = []; }
  });
  // Each group stays up until the next one starts, or 0.4 s after its last word.
  return groups.map((g, i) => ({ words: g, s: g[0].s, e: groups[i + 1] ? groups[i + 1][0].s : g[g.length - 1].e + 0.4 }));
}

function captions(ctx, t, groups, { x, y, maxWidth, size, look = 'serif', theme = THEME } = {}) {
  const g = groups.find(gr => t >= gr.s && t < gr.e);
  if (!g) return;
  const styles = {
    serif: { weight: 500, style: 'italic', family: theme.font, fill: theme.ink, hi: theme.accent, pad: 0 },
    boxed: { weight: 800, style: '', family: theme.fontBody || theme.font, fill: theme.bg, hi: theme.bg, box: theme.ink, hiBox: theme.accent, pad: 0.22 },
    clean: { weight: 800, style: '', family: theme.fontBody || theme.font, fill: '#ffffff', hi: '#ffffff', shadow: 'rgba(0,0,0,0.55)', pad: 0 },
  };
  const st = styles[look] || styles.serif;
  ctx.save();
  ctx.riseRole = 'caption';
  let px = size;
  const gap = () => px * (st.box ? 0.5 : 0.28);
  const widthAt = p => { ctx.font = fontOf(st.weight, p, st.family, st.style); return g.words.reduce((s, wd) => s + ctx.measureText(wd.w).width, 0) + gap() * (g.words.length - 1) + (st.box ? p * st.pad * 2 * g.words.length : 0); };
  while (widthAt(px) > maxWidth && px > 12) px *= 0.94;
  const pop = ease.outBack(seg(t, g.s, g.s + 0.14));             // the group pops in
  ctx.translate(x, y); ctx.scale(0.92 + 0.08 * pop, 0.92 + 0.08 * pop); ctx.translate(-x, -y);
  ctx.globalAlpha = clamp(pop * 1.4);
  ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
  let cx = x - widthAt(px) / 2;
  ctx.font = fontOf(st.weight, px, st.family, st.style);
  for (const wd of g.words) {
    const on = t >= wd.s && t < wd.e, ww = ctx.measureText(wd.w).width, padX = px * st.pad;
    if (st.box) {
      ctx.fillStyle = on ? st.hiBox : st.box;
      const bx = cx, by = y - px * 0.92, bw = ww + padX * 2, bh = px * 1.24;
      ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, px * 0.14); ctx.fill();
      cx += padX;
    }
    if (st.shadow) { ctx.shadowColor = st.shadow; ctx.shadowBlur = px * 0.25; ctx.shadowOffsetY = px * 0.05; }
    ctx.fillStyle = on ? st.hi : st.fill;
    const lift = look === 'clean' && on ? px * 0.06 : 0;
    ctx.fillText(wd.w, cx, y - lift);
    ctx.shadowColor = 'transparent';
    if (look === 'clean' && on) { ctx.fillStyle = theme.accent; ctx.fillRect(cx, y + px * 0.12, ww, px * 0.08); }
    cx += ww + (st.box ? padX : 0) + gap();
  }
  ctx.riseRole = '';
  ctx.restore();
}
