/* ── Animate a REAL logo from its SVG (Level 5) ────────────────────────────
   Paste into the helpers section. Never redraw a logo from memory: load the file the
   brand scraper saved (brand/logo.svg) or the one the user gave you.

     let LOGO = null;
     const PRELOAD = [async () => { LOGO = await loadLogoParts('brand/logo.svg'); }];
   Then in render():
     drawLogo(ctx, LOGO, x, y, w, h, (i, part) => ({
       alpha: 1,        // 0–1
       dx: 0, dy: 0,    // offset in canvas px
       scale: 1,        // around the part's own centre
       draw: 1,         // < 1 strokes the outline on progressively (draw-on), 1 = filled
     }));
   Parts come in document order; LOGO.parts[i].box is the part's box in logo units, so you can
   stagger by position (left to right: sort indices by box.x). If a brand's file is a PNG only,
   animate the image as a whole (mask wipes, scale, blur) instead of splitting it. */

function svgPathData(el) {
  const n = k => parseFloat(el.getAttribute(k)) || 0;
  switch (el.tagName.toLowerCase()) {
    case 'path': return el.getAttribute('d');
    case 'rect': {
      const x = n('x'), y = n('y'), w = n('width'), h = n('height');
      let rx = n('rx') || n('ry'), ry = n('ry') || n('rx');
      if (!rx) return `M${x} ${y}h${w}v${h}h${-w}Z`;
      rx = Math.min(rx, w / 2); ry = Math.min(ry, h / 2);
      return `M${x + rx} ${y}h${w - 2 * rx}a${rx} ${ry} 0 0 1 ${rx} ${ry}v${h - 2 * ry}a${rx} ${ry} 0 0 1 ${-rx} ${ry}` +
             `h${2 * rx - w}a${rx} ${ry} 0 0 1 ${-rx} ${-ry}v${2 * ry - h}a${rx} ${ry} 0 0 1 ${rx} ${-ry}Z`;
    }
    case 'circle': { const cx = n('cx'), cy = n('cy'), r = n('r'); return `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z`; }
    case 'ellipse': { const cx = n('cx'), cy = n('cy'), rx = n('rx'), ry = n('ry'); return `M${cx - rx} ${cy}a${rx} ${ry} 0 1 0 ${2 * rx} 0a${rx} ${ry} 0 1 0 ${-2 * rx} 0Z`; }
    case 'polygon': case 'polyline': {
      const p = (el.getAttribute('points') || '').trim().split(/[\s,]+/).map(Number);
      if (p.length < 4) return null;
      let d = `M${p[0]} ${p[1]}`;
      for (let i = 2; i + 1 < p.length; i += 2) d += `L${p[i]} ${p[i + 1]}`;
      return el.tagName.toLowerCase() === 'polygon' ? d + 'Z' : d;
    }
    case 'line': return `M${n('x1')} ${n('y1')}L${n('x2')} ${n('y2')}`;
  }
  return null;
}

async function loadLogoParts(src) {
  const text = await (await fetch(src)).text();
  const host = document.createElement('div');
  // Off-screen and transparent, not visibility:hidden: children would inherit it and be skipped below.
  host.style.cssText = 'position:absolute;left:-99999px;top:0;opacity:0;pointer-events:none';
  host.innerHTML = text;
  document.body.appendChild(host);
  const svg = host.querySelector('svg');
  if (!svg) { host.remove(); throw new Error('no <svg> in ' + src); }
  const vbb = svg.viewBox && svg.viewBox.baseVal;
  const bb = svg.getBBox();
  const viewBox = vbb && vbb.width ? [vbb.x, vbb.y, vbb.width, vbb.height] : [bb.x, bb.y, bb.width, bb.height];
  const rootInv = svg.getScreenCTM().inverse();
  const parts = [];
  for (const el of svg.querySelectorAll('path, rect, circle, ellipse, polygon, polyline, line')) {
    if (el.closest('defs, clipPath, mask, symbol, pattern, marker')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const d = svgPathData(el);
    if (!d) continue;
    const m = rootInv.multiply(el.getScreenCTM());               // element → logo units
    let fill = cs.fill;
    if (fill.startsWith('url(')) {                                 // gradients: use the first stop's colour
      const id = (fill.match(/#([^")]+)/) || [])[1], stop = id && svg.querySelector('#' + CSS.escape(id) + ' stop');
      fill = stop ? getComputedStyle(stop).stopColor : '#000000';
    }
    const b = el.getBBox(), pts = [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]]
      .map(([x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]);
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    parts.push({
      d, path: new Path2D(d), m: [m.a, m.b, m.c, m.d, m.e, m.f],
      fill: fill === 'none' ? null : fill, rule: cs.fillRule === 'evenodd' ? 'evenodd' : 'nonzero',
      stroke: cs.stroke === 'none' ? null : cs.stroke, strokeWidth: parseFloat(cs.strokeWidth) || 0,
      opacity: (+cs.opacity || 1) * (+cs.fillOpacity || 1),
      length: el.getTotalLength ? el.getTotalLength() : 0,
      box: { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) },
    });
  }
  host.remove();
  return { parts, viewBox, aspect: viewBox[2] / viewBox[3] };
}

function drawLogo(ctx, logo, x, y, w, h, style = () => ({})) {
  if (!logo) return;
  const [vx, vy, vw, vh] = logo.viewBox, s = Math.min(w / vw, h / vh);
  const ox = x + (w - vw * s) / 2 - vx * s, oy = y + (h - vh * s) / 2 - vy * s;
  logo.parts.forEach((p, i) => {
    const st = { alpha: 1, dx: 0, dy: 0, scale: 1, draw: 1, ...style(i, p) };
    if (st.alpha <= 0.001) return;
    ctx.save();
    ctx.globalAlpha *= clamp(st.alpha) * p.opacity;
    const cx = ox + (p.box.x + p.box.w / 2) * s, cy = oy + (p.box.y + p.box.h / 2) * s;
    ctx.translate(cx + st.dx, cy + st.dy); ctx.scale(st.scale, st.scale); ctx.translate(-cx, -cy);
    ctx.translate(ox, oy); ctx.scale(s, s); ctx.transform(...p.m);
    if (st.draw < 1) {
      ctx.lineWidth = Math.max(p.strokeWidth, 2 / s); ctx.lineJoin = 'round';
      ctx.strokeStyle = p.fill || p.stroke || '#000';
      ctx.setLineDash([p.length, p.length]); ctx.lineDashOffset = p.length * (1 - clamp(st.draw));
      ctx.stroke(p.path);
    } else {
      if (p.fill) { ctx.fillStyle = p.fill; ctx.fill(p.path, p.rule); }
      if (p.stroke && p.strokeWidth) { ctx.strokeStyle = p.stroke; ctx.lineWidth = p.strokeWidth; ctx.stroke(p.path); }
    }
    ctx.restore();
  });
}
