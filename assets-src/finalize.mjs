// Assemble a baked model (lod.glb + albedo/mr/emit PNGs) into one web-ready GLB with a single atlas material,
// and record its size and emission scale in a manifest the game imports.
// usage: node assets-src/finalize.mjs <outDir> <manifest.json> name...
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS, EXTMeshoptCompression } from '@gltf-transform/extensions';
import { dedup, prune, reorder, quantize, textureCompress } from '@gltf-transform/functions';
import { MeshoptEncoder } from 'meshoptimizer';
import sharp from 'sharp';
import { readFileSync, writeFileSync, existsSync, mkdirSync, statSync } from 'node:fs';
const args = process.argv.slice(2);
const flags = new Set(args.filter((a) => a.startsWith('--')));
const [outDir, manifestPath, ...names] = args.filter((a) => !a.startsWith('--'));
await MeshoptEncoder.ready;
mkdirSync(outDir, { recursive: true });
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder });
const manifest = existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, 'utf8')) : {};
for (const name of names) {
  const dir = `assets-src/baked/${name}`;
  const doc = await io.read(`${dir}/lod.glb`);
  const root = doc.getRoot();
  const tex = (f, mime = 'image/png') => doc.createTexture(f).setImage(readFileSync(`${dir}/${f}`)).setMimeType(mime).setURI(f);
  const mat = doc.createMaterial('atlas')
    .setBaseColorTexture(tex('albedo.png'))
    .setMetallicRoughnessTexture(tex('mr.png'))
    .setEmissiveTexture(tex('emit.png'))
    .setEmissiveFactor([1, 1, 1]).setMetallicFactor(1).setRoughnessFactor(1);
  for (const m of root.listMeshes()) for (const p of m.listPrimitives()) p.setMaterial(mat);
  const info = JSON.parse(readFileSync(`${dir}/info.json`, 'utf8'));
  await doc.transform(dedup(), prune(), textureCompress({ encoder: sharp, targetFormat: 'webp', quality: 88 }));
  if (!flags.has('--noquant')) await doc.transform(reorder({ encoder: MeshoptEncoder }), quantize());
  if (!flags.has('--nomeshopt')) doc.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({ method: EXTMeshoptCompression.EncoderMethod.FILTER });
  const out = `${outDir}/${name}.glb`;
  await io.write(out, doc);
  manifest[name] = { size: info.size, emax: +info.emax.toFixed(3), lod0: info.lod0, lod1: info.lod1 };
  console.log(name, (statSync(out).size / 1e3).toFixed(0), 'KB', JSON.stringify(manifest[name]));
}
writeFileSync(manifestPath, JSON.stringify(manifest, null, 1));
