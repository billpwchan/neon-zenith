// node sheet.mjs out.png cols size file...
import sharp from 'sharp';
const [out, cols, size, ...files] = process.argv.slice(2);
const c = +cols, s = +size, rows = Math.ceil(files.length / c);
const tiles = await Promise.all(files.map((f) => sharp(f).resize(s, s, { fit: 'fill' }).removeAlpha().toBuffer()));
await sharp({ create: { width: c * s, height: rows * s, channels: 3, background: '#000' } })
  .composite(tiles.map((t, i) => ({ input: t, left: (i % c) * s, top: Math.floor(i / c) * s }))).png().toFile(out);
