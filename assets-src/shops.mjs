// Shopfront strip: Hong Kong fronts from the Asian Shop Pack (abhayexe) captured by facade_ortho.py, cut
// side by side into one 3 m tall street the shop planes slide along. Korean-signed and real-brand fronts
// are left out. Writes public/tex/shop_albedo.webp (sRGB) and shop_mask.webp (R lit interior, G signage).
// node assets-src/shops.mjs
import sharp from 'sharp';
import fs from 'node:fs';

const PX_PER_M = 200; // capture scale
const CUTS = [
  ['shop_top', 3808, 4866], // BLOSSOM TIME florist, noodle shop, ginseng hall
  ['shop_bot', 1326, 2202], // tenement door, travel agent, two shutters
  ['shop_bot', 3260, 4002], // dessert house, pawn shop
];
const W = 2048, H = 512;

async function cut(dir, pass, x0, x1, ch) {
  let s = sharp(`assets-src/facade/raw/${dir}/${pass}.png`).extract({ left: x0, top: 0, width: x1 - x0, height: 600 }).flatten({ background: '#000' });
  s = ch === 1 ? s.greyscale() : s.removeAlpha();
  return s.raw().toBuffer({ resolveWithObject: true });
}

async function join(pass, ch) {
  const parts = await Promise.all(CUTS.map(([d, a, b]) => cut(d, pass, a, b, ch)));
  const total = parts.reduce((a, p) => a + p.info.width, 0);
  const out = Buffer.alloc(total * 600 * ch);
  let x = 0;
  for (const p of parts) {
    for (let y = 0; y < 600; y++) p.data.copy(out, (y * total + x) * ch, y * p.info.width * ch, (y + 1) * p.info.width * ch);
    x += p.info.width;
  }
  return { data: out, width: total };
}

// signboards and vertical signs, strip pixels [x0, y0, x1, y1] (y down from the top of the 3 m front)
const SIGNS = [
  [0, 168, 274, 276], [285, 186, 595, 264], [532, 288, 589, 510], [602, 50, 1044, 228],
  [1077, 134, 1305, 228], [1291, 314, 1318, 462], [1378, 124, 1790, 254],
  [1944, 78, 2355, 224], [2415, 18, 2649, 168], [2379, 182, 2676, 226],
];

const A = await join('albedo', 3);
const G = await join('glass', 1), F = await join('frame', 1);
const M = Buffer.alloc(A.width * 600 * 3);
for (let y = 0; y < 600; y++) for (let x = 0; x < A.width; x++) {
  const i = y * A.width + x;
  // the pack's emissive parts are shop windows too: both are lit from inside
  M[i * 3] = G.data[i] > 127 || F.data[i] > 127 ? 255 : 0;
  M[i * 3 + 1] = SIGNS.some(([x0, y0, x1, y1]) => x >= x0 && x < x1 && y >= y0 && y < y1) ? 255 : 0;
  M[i * 3 + 2] = 0;
}
await sharp(A.data, { raw: { width: A.width, height: 600, channels: 3 } }).resize(W, H, { fit: 'fill', kernel: 'lanczos3' }).webp({ quality: 88, effort: 6 }).toFile('public/tex/shop_albedo.webp');
await sharp(M, { raw: { width: A.width, height: 600, channels: 3 } }).resize(W, H, { fit: 'fill' }).webp({ lossless: true, effort: 6 }).toFile('public/tex/shop_mask.webp');
const len = A.width / PX_PER_M;
fs.writeFileSync('src/city/shops.json', JSON.stringify({ length: +len.toFixed(3), height: 3 }) + '\n');
console.log('strip', len.toFixed(2), 'm', ['albedo', 'mask'].map((f) => `${f} ${(fs.statSync(`public/tex/shop_${f}.webp`).size / 1024).toFixed(0)} KB`).join(', '));
