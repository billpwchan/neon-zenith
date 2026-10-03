// Pack a prepared glTF for the web: welded, reordered, meshopt-compressed geometry and WebP textures.
// usage: node assets-src/pack.mjs in.glb out.glb [maxTex=1024] [simplifyRatio=1]
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS, EXTMeshoptCompression } from '@gltf-transform/extensions';
import { dedup, weld, prune, reorder, quantize, textureCompress, simplify, resample } from '@gltf-transform/functions';
import { MeshoptEncoder, MeshoptSimplifier } from 'meshoptimizer';
import sharp from 'sharp';
const [src, out, maxTex = '1024', ratio = '1'] = process.argv.slice(2);
await MeshoptEncoder.ready;
await MeshoptSimplifier.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder });
const doc = await io.read(src);
const steps = [dedup(), weld()];
if (+ratio < 1) steps.push(simplify({ simplifier: MeshoptSimplifier, ratio: +ratio, error: 0.002 }));
steps.push(prune(), textureCompress({ encoder: sharp, targetFormat: 'webp', quality: 86, resize: [+maxTex, +maxTex] }), reorder({ encoder: MeshoptEncoder }), quantize());
await doc.transform(...steps);
doc.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({ method: EXTMeshoptCompression.EncoderMethod.FILTER });
await io.write(out, doc);
const { statSync } = await import('node:fs');
console.log(out, (statSync(out).size / 1e6).toFixed(2), 'MB');
