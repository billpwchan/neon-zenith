// mean linear luminance of each baked albedo under its paint mask, so the game can recolour and keep the shading
import sharp from 'sharp';
import { readFileSync, writeFileSync } from 'node:fs';
const [manifestPath, ...names] = process.argv.slice(2);
const man = JSON.parse(readFileSync(manifestPath, 'utf8'));
const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
for (const n of names) {
  const a = await sharp(`assets-src/baked/${n}/albedo.png`).raw().toBuffer({ resolveWithObject: true });
  const m = await sharp(`assets-src/baked/${n}/mr.png`).raw().toBuffer({ resolveWithObject: true });
  let s = 0, c = 0;
  const ca = a.info.channels, cm = m.info.channels;
  for (let i = 0; i < a.info.width * a.info.height; i++) {
    if (m.data[i * cm] < 128) continue;
    s += 0.2126 * lin(a.data[i * ca]) + 0.7152 * lin(a.data[i * ca + 1]) + 0.0722 * lin(a.data[i * ca + 2]);
    c++;
  }
  man[n].paintLum = c ? +(s / c).toFixed(4) : 0;
  console.log(n, man[n].paintLum, c);
}
writeFileSync(manifestPath, JSON.stringify(man, null, 1));
