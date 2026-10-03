// Packs facade tiles into three vertical strips the game loads as texture arrays (RGB only: browsers
// premultiply alpha on decode, which would wipe colour wherever a mask is zero).
//   albedo.webp  1024/layer  sRGB colour
//   mask.webp     512/layer  R glass (res) or lit fraction (lit), G window id, B roughness (lossless: channels are data)
//   normal.webp   512/layer  R,G tangent normal xy, B metalness
// Layer kinds: 'res' comes from facade_ortho.py captures (rooms are lit in the shader, one id per window);
// 'lit' is an ambientCG night photo whose emission map says which windows already glow.
// node assets-src/facades.mjs
import sharp from 'sharp';
import fs from 'node:fs';

const S = 1024, SN = 512, SM = 512;
const LAYERS = [
  // crops are in capture pixels and start mid-spandrel / mid-pier so cell edges fall on wall
  // hk3 (abhayexe, CC BY): xs are the pier centres; uneven bays are stretched to equal width, and kit_slice.py
  // cuts the kit on the same piers, so photo and model stay on one grid
  { name: 'hk-brown', kind: 'res', raw: 'assets-src/facade/raw/hk3c', crop: [110, 1340, 1050, 1991], xs: [110, 410, 610, 840, 1050], floors: 3, bays: 4, floorH: 3.1, close: 14 },
  { name: 'hk-white', kind: 'res', raw: 'assets-src/facade/raw/hk3a', crop: [53, 921, 1076, 1921], xs: [53, 383, 753, 1076], floors: 5, bays: 3, floorH: 2.9, close: 12 },
  { name: 'hk-office', kind: 'res', raw: 'assets-src/facade/raw/hk3d', crop: [13, 664, 880, 1192], floors: 2, bays: 2, floorH: 3.7, close: 12 },
  { name: 'hk-pink', kind: 'res', raw: 'assets-src/facade/raw/hk3e', crop: [45, 236, 1291, 1436], xs: [45, 470, 880, 1291], floors: 5, bays: 3, floorH: 3.3, close: 14 },
  { name: 'hk-tower', kind: 'res', raw: 'assets-src/facade/raw/hk3f', crop: [17, 1859, 1918, 3779], xs: [17, 349, 650, 968, 1283, 1600, 1918], floors: 5, bays: 6, floorH: 3.0, close: 12 },
  { name: 'tonglau', kind: 'res', raw: 'assets-src/facade/raw/proc', crop: [129, 533, 1856, 1767], floors: 5, bays: 7, floorH: 3.1, close: 14 },
  { name: 'office-c', kind: 'lit', acg: 'Facade009', floorH: 3.8 },
  { name: 'piers', kind: 'lit', acg: 'Facade019B', floorH: 3.4, floors: 6 },
];

const lum = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
async function raw(src, w, h, crop, ch = 3) {
  let s = sharp(src);
  if (crop) s = s.extract({ left: crop[0], top: crop[1], width: crop[2] - crop[0], height: crop[3] - crop[1] });
  if (w) s = s.resize(w, h, { fit: 'fill', kernel: 'lanczos3' });
  s = ch === 1 ? s.greyscale() : s.removeAlpha();
  const { data, info } = await s.raw().toBuffer({ resolveWithObject: true });
  return { data, w: info.width, h: info.height, c: info.channels };
}

// separable box min/max on a binary image
function morph(src, w, h, rx, ry, op) {
  const tmp = new Uint8Array(w * h), out = new Uint8Array(w * h);
  const f = op === 'min' ? Math.min : Math.max, init = op === 'min' ? 1 : 0;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let v = init;
    for (let k = -rx; k <= rx; k++) { const xx = Math.min(w - 1, Math.max(0, x + k)); v = f(v, src[y * w + xx]); }
    tmp[y * w + x] = v;
  }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let v = init;
    for (let k = -ry; k <= ry; k++) { const yy = Math.min(h - 1, Math.max(0, y + k)); v = f(v, tmp[yy * w + x]); }
    out[y * w + x] = v;
  }
  return out;
}

// label 4-connected regions, then hand every pixel the id of its nearest region (so filtering never
// blends a window's id with the wall's)
function windowIds(bin, w, h) {
  const id = new Int32Array(w * h).fill(-1);
  let n = 0;
  const q = new Int32Array(w * h);
  for (let i = 0; i < w * h; i++) {
    if (!bin[i] || id[i] >= 0) continue;
    let qh = 0, qt = 0; q[qt++] = i; id[i] = n;
    while (qh < qt) {
      const p = q[qh++], x = p % w, y = (p - x) / w;
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const xx = x + dx, yy = y + dy;
        if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
        const j = yy * w + xx;
        if (bin[j] && id[j] < 0) { id[j] = n; q[qt++] = j; }
      }
    }
    n++;
  }
  let qh = 0, qt = 0;
  for (let i = 0; i < w * h; i++) if (id[i] >= 0) q[qt++] = i;
  while (qh < qt) {
    const p = q[qh++], x = p % w, y = (p - x) / w;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const xx = x + dx, yy = y + dy;
      if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
      const j = yy * w + xx;
      if (id[j] < 0) { id[j] = id[p]; q[qt++] = j; }
    }
  }
  return { id, n };
}

// strongest vertical period of a luminance image: floors per tile for the photo layers
function period(img) {
  const { data, w, h, c } = img;
  const row = new Float64Array(h);
  for (let y = 0; y < h; y++) { let s = 0; for (let x = 0; x < w; x++) s += lum(data[(y * w + x) * c], data[(y * w + x) * c + 1], data[(y * w + x) * c + 2]); row[y] = s / w; }
  const mean = row.reduce((a, b) => a + b) / h;
  for (let y = 0; y < h; y++) row[y] -= mean;
  let best = 0, bestLag = 0;
  const ac = (lag) => { let s = 0; for (let y = 0; y < h; y++) s += row[y] * row[(y + lag) % h]; return s; };
  const a0 = ac(0);
  for (let lag = Math.round(h / 60); lag < h / 3; lag++) {
    const v = ac(lag) / a0;
    // first lag that is a local peak and clearly correlated
    if (v > 0.25 && v > ac(lag - 1) / a0 && v >= ac(lag + 1) / a0) { best = v; bestLag = lag; break; }
  }
  return { lag: bestLag, corr: best };
}

// stretch each bay of the crop to the mean bay width; writes <raw>_w and points the layer at it
async function warp(L) {
  const [, y0, , y1] = L.crop, xs = L.xs, n = xs.length - 1;
  const bw = Math.round((xs[n] - xs[0]) / n);
  const dir = `${L.raw}_w`;
  fs.mkdirSync(dir, { recursive: true });
  for (const f of ['albedo', 'glass', 'frame', 'normal']) {
    const parts = [];
    for (let k = 0; k < n; k++) {
      parts.push({ input: await sharp(`${L.raw}/${f}.png`).extract({ left: xs[k], top: y0, width: xs[k + 1] - xs[k], height: y1 - y0 })
        .resize(bw, y1 - y0, { fit: 'fill', kernel: 'lanczos3' }).png().toBuffer(), left: k * bw, top: 0 });
    }
    await sharp({ create: { width: bw * n, height: y1 - y0, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } } }).composite(parts).png().toFile(`${dir}/${f}.png`);
  }
  return { ...L, raw: dir, crop: [0, 0, bw * n, y1 - y0] };
}

const albedo = [], mask = [], normal = [], meta = [];
for (let L of LAYERS) {
  if (L.xs) L = await warp(L);
  if (L.kind === 'res') {
    const [x0, y0, x1, y1] = L.crop, cw = x1 - x0, chh = y1 - y0;
    const A = await raw(`${L.raw}/albedo.png`, S, S, L.crop);
    const G0 = await raw(`${L.raw}/glass.png`, 0, 0, L.crop, 1);
    const F0 = await raw(`${L.raw}/frame.png`, 0, 0, L.crop, 1);
    // binary glass at capture resolution: modelled frames punched out, thin head/sill strips opened away
    let gb = new Uint8Array(cw * chh);
    for (let i = 0; i < gb.length; i++) gb[i] = G0.data[i] > 127 && F0.data[i] < 128 ? 1 : 0;
    gb = morph(morph(gb, cw, chh, 0, 6, 'min'), cw, chh, 0, 6, 'max');
    // windows: panes closed together into one region each
    const win = morph(morph(gb, cw, chh, L.close, L.close, 'max'), cw, chh, L.close, L.close, 'min');
    const { id, n } = windowIds(win, cw, chh);
    const gImg = Buffer.alloc(cw * chh * 3);
    for (let i = 0; i < cw * chh; i++) {
      const g = gb[i] * 255;
      gImg[i * 3] = g; gImg[i * 3 + 1] = (id[i] * 37) % 251 + 1; gImg[i * 3 + 2] = g ? 15 : 215;
    }
    // glass and roughness resample smoothly; ids must stay exact
    const M = await raw(await sharp(gImg, { raw: { width: cw, height: chh, channels: 3 } }).png().toBuffer(), SM, SM);
    const ID = await sharp(gImg, { raw: { width: cw, height: chh, channels: 3 } }).resize(SM, SM, { fit: 'fill', kernel: 'nearest' }).raw().toBuffer();
    for (let i = 0; i < SM * SM; i++) M.data[i * 3 + 1] = ID[i * 3 + 1];
    const As = await raw(`${L.raw}/albedo.png`, SM, SM, L.crop);
    // wall roughness follows the grime a little
    for (let i = 0; i < SM * SM; i++) {
      if (M.data[i * 3] > 127) continue;
      const l = lum(As.data[i * 3], As.data[i * 3 + 1], As.data[i * 3 + 2]) / 255;
      M.data[i * 3 + 2] = Math.round(255 * Math.min(0.95, 0.72 + (0.5 - l) * 0.3)) & 0xf0;
    }
    const N = await raw(`${L.raw}/normal.png`, SN, SN, [x0, y0, x1, y1].map((v, k) => Math.round(v * 1)));
    for (let i = 0; i < SN * SN; i++) N.data[i * 3 + 2] = 0;
    albedo.push(A.data); mask.push(M.data); normal.push(N.data);
    const h = L.floors * L.floorH, w = h * cw / chh;
    meta.push({ name: L.name, kind: 'res', w: +w.toFixed(3), h: +h.toFixed(3), bays: L.bays, floors: L.floors, windows: n });
    console.log(L.name, 'windows', n, 'tile', w.toFixed(2), 'x', h.toFixed(2), 'm');
  } else {
    const dir = `assets-src/acg/${L.acg}/${L.acg}_2K-JPG_`;
    const A = await raw(`${dir}Color.jpg`, S, S);
    const As = await raw(`${dir}Color.jpg`, SM, SM);
    const E = await raw(`${dir}Emission.jpg`, SM, SM);
    const R = await raw(`${dir}Roughness.jpg`, SM, SM, null, 1);
    const M = { data: Buffer.alloc(SM * SM * 3) };
    for (let i = 0; i < SM * SM; i++) {
      const lc = lum(As.data[i * 3], As.data[i * 3 + 1], As.data[i * 3 + 2]);
      const le = lum(E.data[i * 3], E.data[i * 3 + 1], E.data[i * 3 + 2]);
      M.data[i * 3] = Math.round(255 * Math.min(1, le / Math.max(lc, 6))) & 0xfc;
      M.data[i * 3 + 1] = 0;
      M.data[i * 3 + 2] = R.data[i] & 0xf0;
    }
    const N = await raw(`${dir}NormalGL.jpg`, SN, SN);
    const metal = fs.existsSync(`${dir}Metalness.jpg`) ? (await raw(`${dir}Metalness.jpg`, SN, SN, null, 1)).data : null;
    for (let i = 0; i < SN * SN; i++) N.data[i * 3 + 2] = metal ? metal[i] : 0;
    const p = period(await raw(`${dir}Emission.jpg`, 0, 0));
    const floors = L.floors || Math.round(2048 / p.lag);
    const h = floors * L.floorH;
    albedo.push(A.data); mask.push(M.data); normal.push(N.data);
    meta.push({ name: L.name, kind: 'lit', w: +h.toFixed(3), h: +h.toFixed(3), bays: 0, floors });
    console.log(L.name, L.acg, 'period', p.lag, 'corr', p.corr.toFixed(2), 'floors', floors, 'tile', h.toFixed(1), 'm');
  }
}

const strip = (bufs, size) => sharp(Buffer.concat(bufs), { raw: { width: size, height: size * bufs.length, channels: 3 } });

await strip(albedo, S).webp({ quality: 86, effort: 6 }).toFile('public/tex/facade_albedo.webp');
await strip(mask, SM).webp({ lossless: true, effort: 6 }).toFile('public/tex/facade_mask.webp');
await strip(normal, SN).webp({ quality: 90, effort: 6 }).toFile('public/tex/facade_normal.webp');
fs.writeFileSync('src/city/facades.json', JSON.stringify({ size: S, maskSize: SM, normalSize: SN, layers: meta }, null, 1) + '\n');
for (const f of ['albedo', 'mask', 'normal']) console.log(f, (fs.statSync(`public/tex/facade_${f}.webp`).size / 1024).toFixed(0), 'KB');
