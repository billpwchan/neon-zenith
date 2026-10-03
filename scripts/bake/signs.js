// Bakes the street-sign atlas: 32 vertical blade signs (256x1024) and 32 horizontal signs (1024x256)
// on one 4096 canvas. RGB = emitted light, A = solid area (board or tube). Runtime alpha-tests A.
const C = {
  red: '#ff2a3c', pink: '#ff4fa3', magenta: '#ff3df2', violet: '#a35bff', blue: '#3d7bff',
  cyan: '#2de2ff', green: '#3dff8b', amber: '#ffb03a', gold: '#ffd34d', white: '#eaf6ff', orange: '#ff7a1f',
};
const F = {
  sung: '"Chiron Sung HK Variable"', hei: '"Chiron Hei HK Variable"', kai: '"LXGW WenKai TC"',
  serif: '"Noto Serif TC"', tilt: '"Tilt Neon"', mono: '"Monoton"', script: '"Neonderthaw"',
};

// style: neon (tube fill on board), outline (contour tubes on board), box (lit acrylic panel), bare (tubes only)
const VERT = [
  { t: '大押', f: F.serif, w: 900, s: 'outline', c: C.red, c2: C.gold, sym: 'pawn' },
  { t: '茶餐廳', f: F.serif, w: 900, s: 'box', bg: '#f4f1e8', c: '#c8102e' },
  { t: '金龍酒家', f: F.sung, w: 900, s: 'neon', c: C.gold, c2: C.red },
  { t: '麻雀耍樂', f: F.kai, w: 700, s: 'outline', c: C.magenta, c2: C.cyan },
  { t: '時鐘酒店', f: F.hei, w: 800, s: 'neon', c: C.pink, c2: C.violet },
  { t: '涼茶', f: F.serif, w: 900, s: 'box', bg: '#ffd21f', c: '#111' },
  { t: '跌打醫館', f: F.kai, w: 700, s: 'box', bg: '#eef3ff', c: '#1235a8' },
  { t: '找換', f: F.hei, w: 900, s: 'neon', c: C.green, c2: C.green, sub: 'EXCHANGE' },
  { t: '粥麵', f: F.serif, w: 900, s: 'neon', c: C.amber, c2: C.red },
  { t: '燒味', f: F.serif, w: 900, s: 'box', bg: '#b3121f', c: '#fff4d8' },
  { t: '夜總會', f: F.sung, w: 900, s: 'outline', c: C.violet, c2: C.pink },
  { t: '桑拿浴室', f: F.hei, w: 700, s: 'outline', c: C.cyan, c2: C.blue },
  { t: '中醫診所', f: F.kai, w: 700, s: 'box', bg: '#f3fff6', c: '#0b7a3b' },
  { t: '金行', f: F.serif, w: 900, s: 'neon', c: C.gold, c2: C.gold },
  { t: '遊戲機中心', f: F.hei, w: 900, s: 'neon', multi: [C.cyan, C.magenta, C.gold, C.green, C.pink], c2: C.blue },
  { t: '網吧', f: F.hei, w: 900, s: 'neon', c: C.cyan, c2: C.blue, sub: 'NET 24H' },
  { t: '義體診所', f: F.hei, w: 900, s: 'neon', c: C.cyan, c2: C.magenta },
  { t: '神經接駁', f: F.sung, w: 800, s: 'outline', c: C.blue, c2: C.cyan },
  { t: '記憶回收', f: F.kai, w: 700, s: 'neon', c: C.violet, c2: C.magenta },
  { t: '晶片改裝', f: F.hei, w: 900, s: 'neon', c: C.green, c2: C.cyan },
  { t: '冰室', f: F.serif, w: 900, s: 'box', bg: '#bff5df', c: '#d0112b' },
  { t: '糖水', f: F.kai, w: 700, s: 'neon', c: C.pink, c2: C.pink },
  { t: '鐘錶眼鏡', f: F.hei, w: 800, s: 'box', bg: '#1d4fd8', c: '#ffffff' },
  { t: '樓上旅館', f: F.sung, w: 800, s: 'outline', c: C.amber, c2: C.orange },
  { t: '雲吞麵', f: F.serif, w: 900, s: 'neon', c: C.orange, c2: C.gold },
  { t: '天頂', f: F.sung, w: 900, s: 'neon', c: C.white, c2: C.cyan, sub: 'ZENITH' },
  { t: '鴻運', f: F.serif, w: 900, s: 'outline', c: C.red, c2: C.red },
  { t: '卡拉OK', f: F.hei, w: 900, s: 'neon', c: C.magenta, c2: C.violet },
  { t: '按摩', f: F.kai, w: 700, s: 'outline', c: C.pink, c2: C.violet },
  { t: '藥房', f: F.hei, w: 900, s: 'box', bg: '#0e8f4a', c: '#ffffff' },
  { t: '紋身', f: F.kai, w: 700, s: 'neon', c: C.red, c2: C.red, sub: 'TATTOO' },
  { t: '夜市', f: F.serif, w: 900, s: 'neon', c: C.gold, c2: C.orange },
];

const HORZ = [
  { t: 'HOTEL', t2: '酒店', f: F.tilt, s: 'neon', c: C.pink, c2: C.pink },
  { t: 'KARAOKE', f: F.mono, s: 'bare', c: C.magenta },
  { t: 'NOODLES', t2: '麵', f: F.tilt, s: 'neon', c: C.amber, c2: C.orange },
  { t: 'Bar', f: F.script, s: 'bare', c: C.cyan, big: 1.25 },
  { t: 'OPEN 24H', f: F.tilt, s: 'neon', c: C.red, c2: C.red },
  { t: 'CYBERWARE', t2: '義體', f: F.tilt, s: 'neon', c: C.cyan, c2: C.magenta },
  { t: 'NEURO·LINK', f: F.tilt, s: 'outline', c: C.blue, c2: C.cyan },
  { t: 'PAWN', t2: '大押', f: F.serif, w: 900, s: 'box', bg: '#f6efe0', c: '#b3121f' },
  { t: 'MAHJONG', t2: '麻雀', f: F.tilt, s: 'neon', c: C.green, c2: C.green },
  { t: 'Massage', f: F.script, s: 'bare', c: C.pink, big: 1.2 },
  { t: 'ARCADE', t2: '機舖', f: F.mono, s: 'neon', multi: [C.cyan, C.magenta, C.gold, C.green, C.pink, C.blue], c2: C.violet },
  { t: 'Tattoo', f: F.script, s: 'bare', c: C.red, big: 1.25 },
  { t: 'EXCHANGE', t2: '找換', f: F.hei, w: 900, s: 'box', bg: '#0d1b14', c: '#4dff9a', glowText: 1 },
  { t: 'GOLD', t2: '金行', f: F.serif, w: 900, s: 'box', bg: '#c99a1d', c: '#2a1200' },
  { t: 'KAIZEN-DYNE', f: F.hei, w: 900, s: 'box', bg: '#f2f2f2', c: '#d0112b' },
  { t: 'SYNAPSE', f: F.tilt, s: 'outline', c: C.cyan, c2: C.white },
  { t: 'HELIX BIO', f: F.hei, w: 800, s: 'neon', c: C.green, c2: C.cyan },
  { t: 'ZENITH', t2: '天頂', f: F.sung, w: 900, s: 'neon', c: C.white, c2: C.cyan },
  { t: 'NOVA', f: F.mono, s: 'bare', c: C.orange },
  { t: '鴻運茶餐廳', f: F.serif, w: 900, s: 'box', bg: '#f7f4ea', c: '#c8102e' },
  { t: '金鳳凰夜總會', f: F.sung, w: 900, s: 'neon', c: C.gold, c2: C.violet },
  { t: '龍城冰室', f: F.serif, w: 900, s: 'box', bg: '#a8f0d5', c: '#c8102e' },
  { t: '新記粥麵', f: F.kai, w: 700, s: 'neon', c: C.amber, c2: C.red },
  { t: '永利押', f: F.serif, w: 900, s: 'outline', c: C.red, c2: C.gold, sym: 'pawn' },
  { t: 'ORBIT AIR', f: F.tilt, s: 'neon', c: C.blue, c2: C.white },
  { t: 'BLUE MOON', t2: '藍月酒吧', f: F.tilt, s: 'neon', c: C.blue, c2: C.violet },
  { t: 'ELECTRONICS', t2: '電子', f: F.hei, w: 900, s: 'box', bg: '#1d4fd8', c: '#ffffff' },
  { t: 'CLINIC', t2: '診所', f: F.hei, w: 900, s: 'box', bg: '#f3fff6', c: '#0b7a3b' },
  { t: 'GUEST HOUSE', t2: '旅館', f: F.tilt, s: 'outline', c: C.amber, c2: C.orange },
  { t: '雀館', f: F.serif, w: 900, s: 'neon', c: C.red, c2: C.magenta },
  { t: 'LIVE', t2: '現場', f: F.mono, s: 'neon', c: C.violet, c2: C.pink },
  { t: 'VACANCY', f: F.tilt, s: 'neon', c: C.red, c2: C.red },
];

const cv = document.getElementById('c');
const g = cv.getContext('2d');

function mixHex(a, b, t) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
  const ch = (p, s) => (p >> s) & 255;
  const m = (s) => Math.round(ch(pa, s) * (1 - t) + ch(pb, s) * t);
  return `rgb(${m(16)},${m(8)},${m(0)})`;
}

function roundRect(x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

// a lit glass tube: wide soft glow, saturated body, near-white core
function tube(drawPath, color, width, glow = 1) {
  g.save();
  g.lineJoin = 'round';
  g.lineCap = 'round';
  g.shadowColor = color;
  g.shadowBlur = 26 * glow;
  g.strokeStyle = color;
  g.globalAlpha = 0.55;
  g.lineWidth = width * 2.2;
  drawPath('stroke');
  g.globalAlpha = 1;
  g.shadowBlur = 10 * glow;
  g.lineWidth = width;
  drawPath('stroke');
  g.shadowBlur = 0;
  g.strokeStyle = mixHex(color.startsWith('#') ? color : '#ffffff', '#ffffff', 0.72);
  g.lineWidth = Math.max(1, width * 0.34);
  drawPath('stroke');
  g.restore();
}

function board(x, y, w, h, spec) {
  const r = Math.min(w, h) * 0.06;
  g.save();
  if (spec.s === 'box') {
    const grd = g.createLinearGradient(x, y, x + w, y + h);
    grd.addColorStop(0, spec.bg);
    grd.addColorStop(0.5, mixHex(spec.bg, '#ffffff', 0.18));
    grd.addColorStop(1, spec.bg);
    roundRect(x, y, w, h, r);
    g.fillStyle = grd;
    g.fill();
    g.lineWidth = Math.min(w, h) * 0.035;
    g.strokeStyle = '#1a1a1f';
    g.stroke();
  } else {
    roundRect(x, y, w, h, r);
    g.fillStyle = '#07070b';
    g.fill();
    g.lineWidth = 3;
    g.strokeStyle = '#1b1b24';
    g.stroke();
    const inset = Math.min(w, h) * 0.07;
    tube((m) => { roundRect(x + inset, y + inset, w - inset * 2, h - inset * 2, r * 0.8); if (m !== 'core') g.stroke(); else g.stroke(); }, spec.c2 || spec.c, 5, 0.8);
  }
  g.restore();
}

function glyph(ch, cx, cy, size, spec, color) {
  g.font = `${spec.w || 400} ${size}px ${spec.f}`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  const draw = (mode) => {
    if (mode === 'stroke') g.strokeText(ch, cx, cy);
    else if (mode === 'fill') g.fillText(ch, cx, cy);
    else if (mode === 'core') {
      g.save();
      g.lineWidth = size * 0.05;
      g.strokeStyle = 'rgba(0,0,0,0)';
      g.fillText(ch, cx, cy);
      g.restore();
    }
  };
  if (spec.s === 'box') {
    g.save();
    g.fillStyle = color;
    if (spec.glowText) { g.shadowColor = color; g.shadowBlur = 18; }
    g.fillText(ch, cx, cy);
    g.restore();
  } else if (spec.s === 'outline') {
    tube(draw, color, Math.max(3, size * 0.03), 1);
  } else {
    g.save();
    g.shadowColor = color;
    g.shadowBlur = 36;
    g.fillStyle = color;
    g.globalAlpha = 0.9;
    g.fillText(ch, cx, cy);
    g.globalAlpha = 1;
    g.shadowBlur = 10;
    g.fillText(ch, cx, cy);
    g.shadowBlur = 0;
    g.fillStyle = mixHex(color, '#ffffff', 0.62);
    g.globalAlpha = 0.85;
    // thinner core by clipping to the glyph and drawing a heavy inner stroke in the body color
    g.save();
    g.beginPath();
    g.rect(cx - size, cy - size, size * 2, size * 2);
    g.clip();
    g.fillText(ch, cx, cy);
    g.globalAlpha = 1;
    g.lineJoin = 'round';
    g.lineWidth = size * 0.07;
    g.strokeStyle = color;
    g.strokeText(ch, cx, cy);
    g.restore();
    g.restore();
  }
}

function pawnSymbol(cx, cy, s, spec) {
  // bat over a coin with a square hole: the old Hong Kong pawnshop emblem
  const col = spec.c, gold = spec.c2 || C.gold;
  tube((m) => {
    g.beginPath();
    g.arc(cx, cy + s * 0.22, s * 0.32, 0, Math.PI * 2);
    g.stroke();
    g.beginPath();
    g.rect(cx - s * 0.09, cy + s * 0.13, s * 0.18, s * 0.18);
    g.stroke();
  }, gold, Math.max(3, s * 0.035));
  tube((m) => {
    g.beginPath();
    g.moveTo(cx, cy - s * 0.18);
    g.bezierCurveTo(cx - s * 0.2, cy - s * 0.42, cx - s * 0.42, cy - s * 0.32, cx - s * 0.52, cy - s * 0.12);
    g.quadraticCurveTo(cx - s * 0.4, cy - s * 0.2, cx - s * 0.34, cy - s * 0.08);
    g.quadraticCurveTo(cx - s * 0.24, cy - s * 0.18, cx - s * 0.16, cy - s * 0.06);
    g.quadraticCurveTo(cx - s * 0.08, cy - s * 0.14, cx, cy - s * 0.04);
    g.quadraticCurveTo(cx + s * 0.08, cy - s * 0.14, cx + s * 0.16, cy - s * 0.06);
    g.quadraticCurveTo(cx + s * 0.24, cy - s * 0.18, cx + s * 0.34, cy - s * 0.08);
    g.quadraticCurveTo(cx + s * 0.4, cy - s * 0.2, cx + s * 0.52, cy - s * 0.12);
    g.bezierCurveTo(cx + s * 0.42, cy - s * 0.32, cx + s * 0.2, cy - s * 0.42, cx, cy - s * 0.18);
    g.stroke();
  }, col, Math.max(3, s * 0.035));
}

function vertical(spec, x, y, w, h) {
  const pad = 18;
  const bx = x + pad, by = y + pad, bw = w - pad * 2, bh = h - pad * 2;
  if (spec.s !== 'bare') board(bx, by, bw, bh, spec);
  let top = by + bh * 0.07, bottom = by + bh * 0.93;
  if (spec.sym === 'pawn') { pawnSymbol(x + w / 2, by + bw * 0.6, bw * 0.78, spec); top = by + bw * 1.08; }
  if (spec.sub) bottom -= bh * 0.1;
  const chars = [...spec.t.replace('OK', '\u0000')].map((c) => (c === '\u0000' ? 'OK' : c));
  const n = chars.length;
  const step = (bottom - top) / n;
  const size = Math.min(bw * 0.72, step * 0.86);
  chars.forEach((ch, i) => {
    const col = spec.multi ? spec.multi[i % spec.multi.length] : spec.c;
    const sz = ch === 'OK' ? size * 0.62 : size;
    glyph(ch, x + w / 2, top + step * (i + 0.5), sz, spec, col);
  });
  if (spec.sub) {
    const sub = { ...spec, f: F.tilt, w: 400 };
    g.save();
    g.font = `400 ${bw * 0.2}px ${F.tilt}`;
    const tw = g.measureText(spec.sub).width;
    const fs = Math.min(bw * 0.2, (bw * 0.82) / (tw / (bw * 0.2)));
    glyph(spec.sub, x + w / 2, bottom + bh * 0.05, fs, { ...sub, s: spec.s === 'box' ? 'box' : 'neon' }, spec.c2 || spec.c);
    g.restore();
  }
}

function horizontal(spec, x, y, w, h) {
  const pad = 16;
  const bx = x + pad, by = y + pad, bw = w - pad * 2, bh = h - pad * 2;
  if (spec.s !== 'bare') board(bx, by, bw, bh, spec);
  const hasSecond = !!spec.t2;
  const mainW = hasSecond ? bw * 0.58 : bw * 0.86;
  let size = bh * 0.62 * (spec.big || 1);
  g.font = `${spec.w || 400} ${size}px ${spec.f}`;
  const tw = g.measureText(spec.t).width;
  if (tw > mainW) size *= mainW / tw;
  const cx = hasSecond ? bx + bw * 0.06 + mainW / 2 : x + w / 2;
  if (spec.multi) {
    g.font = `${spec.w || 400} ${size}px ${spec.f}`;
    const total = g.measureText(spec.t).width;
    let px = cx - total / 2;
    [...spec.t].forEach((ch, i) => {
      const cw = g.measureText(ch).width;
      glyph(ch, px + cw / 2, y + h / 2, size, spec, spec.multi[i % spec.multi.length]);
      px += cw;
    });
  } else {
    glyph(spec.t, cx, y + h / 2 + size * 0.04, size, spec, spec.c);
  }
  if (hasSecond) {
    const s2 = { ...spec, f: /[一-鿿]/.test(spec.t2) && spec.f !== F.serif && spec.f !== F.sung ? F.hei : spec.f, w: 900 };
    const n = [...spec.t2].length;
    const sz = Math.min(bh * 0.6, (bw * 0.25) / n);
    const sx = bx + bw * 0.835;
    if (spec.s !== 'box') tube((m) => { g.beginPath(); g.moveTo(bx + bw * 0.685, by + bh * 0.22); g.lineTo(bx + bw * 0.685, by + bh * 0.78); g.stroke(); }, spec.c2 || spec.c, 4, 0.6);
    glyph(spec.t2, sx, y + h / 2, sz, s2, spec.c2 || spec.c);
  }
  if (spec.sym === 'pawn') pawnSymbol(bx + bw * 0.115, y + h / 2 + bh * 0.02, bh * 0.7, spec);
}

async function bake() {
  const all = [...VERT.map((s) => s.t), ...HORZ.map((s) => s.t + (s.t2 || '') + (s.sub || ''))].join('') + 'OK';
  const fams = Object.values(F);
  for (const f of fams) for (const w of [400, 700, 800, 900]) await document.fonts.load(`${w} 64px ${f}`, all);
  await document.fonts.ready;
  g.clearRect(0, 0, 4096, 4096);
  const cells = [];
  VERT.forEach((spec, i) => {
    const x = (i % 16) * 256, y = Math.floor(i / 16) * 1024;
    vertical(spec, x, y, 256, 1024);
    cells.push({ k: 'v', u: x / 4096, v: y / 4096, w: 256 / 4096, h: 1024 / 4096, box: spec.s === 'box' ? 1 : 0, bare: spec.s === 'bare' ? 1 : 0, col: spec.multi ? spec.multi[0] : spec.s === 'box' ? spec.bg : spec.c, label: spec.t });
  });
  HORZ.forEach((spec, i) => {
    const x = (i % 4) * 1024, y = 2048 + Math.floor(i / 4) * 256;
    horizontal(spec, x, y, 1024, 256);
    cells.push({ k: 'h', u: x / 4096, v: y / 4096, w: 1024 / 4096, h: 256 / 4096, box: spec.s === 'box' ? 1 : 0, bare: spec.s === 'bare' ? 1 : 0, col: spec.multi ? spec.multi[0] : spec.s === 'box' ? spec.bg : spec.c, label: spec.t + (spec.t2 ? ' ' + spec.t2 : '') });
  });
  window.__cells = cells;
  window.__done = true;
}
bake();
