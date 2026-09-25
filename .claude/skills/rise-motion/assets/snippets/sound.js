/* ── Sound written in code (Level 5 jingles) ───────────────────────────────
   Paste into the helpers section and replace `const score = null;` with a score.
   score(ac, when, out) schedules ONE loop of audio starting at audio time `when`
   (seconds). Put every event at the same t where render() shows it, so sound and
   picture stay locked. The player starts muted (a Sound button appears); export.py
   renders the score offline and muxes it into the MP4. Deterministic: noise uses
   hash(), never Math.random. Keep peaks under 1.0 (export.py warns if they clip). */

const note = name => {                                   // 'A4' → 440 Hz, 'C#5', 'Eb3' …
  const m = /^([A-G])(#|b)?(-?\d)$/.exec(name);
  const semis = { C: -9, D: -7, E: -5, F: -4, G: -2, A: 0, B: 2 }[m[1]] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0) + (m[3] - 4) * 12;
  return 440 * 2 ** (semis / 12);
};

// One enveloped oscillator note. type: sine | triangle | square | sawtooth.
function tone(ac, out, { at, f, dur = 0.25, type = 'sine', gain = 0.2, attack = 0.006, release = 0.18, glideTo = null, pan = 0 }) {
  const o = ac.createOscillator(), g = ac.createGain(), p = ac.createStereoPanner();
  o.type = type;
  o.frequency.setValueAtTime(f, at);
  if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, at + dur);
  g.gain.setValueAtTime(0, at);
  g.gain.linearRampToValueAtTime(gain, at + attack);
  g.gain.setTargetAtTime(0, at + Math.max(attack, dur - release), release / 3);
  p.pan.value = pan;
  o.connect(g).connect(p).connect(out);
  o.start(at); o.stop(at + dur + release * 3);
}

// A filtered noise burst: hats, swooshes, paper hits. type: highpass | bandpass | lowpass.
function noiseHit(ac, out, { at, dur = 0.12, gain = 0.2, freq = 3000, type = 'bandpass', seed = 7 }) {
  const n = Math.ceil(ac.sampleRate * dur), buf = ac.createBuffer(1, n, ac.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = (hash(i, seed) * 2 - 1) * (1 - i / n) ** 2;
  const src = ac.createBufferSource(), f = ac.createBiquadFilter(), g = ac.createGain();
  src.buffer = buf; f.type = type; f.frequency.value = freq; g.gain.value = gain;
  src.connect(f).connect(g).connect(out); src.start(at);
}

// A soft kick: a sine that drops in pitch.
function kick(ac, out, { at, gain = 0.5 }) {
  tone(ac, out, { at, f: 140, glideTo: 45, dur: 0.22, gain, attack: 0.002, release: 0.12 });
}

// Example: a 3-second jingle locked to a logo reveal that lands at 1.2 s.
// Rising pair while the mark assembles, a bright chord on the land, a shimmer as it settles.
const score = (ac, when, out) => {
  const bus = ac.createGain(); bus.gain.value = 0.9; bus.connect(out);
  tone(ac, bus, { at: when + 0.55, f: note('E5'), dur: 0.16, gain: 0.16, pan: -0.3 });
  tone(ac, bus, { at: when + 0.8, f: note('G5'), dur: 0.16, gain: 0.16, pan: 0.3 });
  kick(ac, bus, { at: when + 1.2, gain: 0.45 });
  for (const [n, p] of [['C5', -0.2], ['E5', 0], ['G5', 0.2], ['C6', 0]]) tone(ac, bus, { at: when + 1.2, f: note(n), type: 'triangle', dur: 0.9, gain: 0.08, release: 0.5, pan: p });
  noiseHit(ac, bus, { at: when + 1.2, dur: 0.3, gain: 0.05, freq: 7000, type: 'highpass' });
  tone(ac, bus, { at: when + 2.2, f: note('C7'), dur: 0.5, gain: 0.03, release: 0.4 });
};
