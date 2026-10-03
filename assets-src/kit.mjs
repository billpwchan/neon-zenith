// Facade kit packer: turns kit_slice.py's cells into what the game instances. Every cell becomes one indexed
// primitive with per-vertex material data, so a whole kit draws from three texture arrays:
//   _MAT = (albedo layer, pbr layer or -1, kind 0 wall / 1 glass / 2 prop, roughness factor)
//   _COL = (base colour factor rgb, metalness factor)
// Writes public/models/kit_<name>.glb, public/tex/kit_<name>_{albedo,pbr,normal}.webp, src/city/kit_<name>.json.
// node assets-src/kit.mjs <name> <layer> <glassRegex> [propRegex]
import { NodeIO, Document } from '@gltf-transform/core';
import { ALL_EXTENSIONS, EXTMeshoptCompression } from '@gltf-transform/extensions';
import { meshopt, quantize, weld } from '@gltf-transform/functions';
import { MeshoptEncoder, MeshoptDecoder } from 'meshoptimizer';
import sharp from 'sharp';
import crypto from 'node:crypto';
import fs from 'node:fs';
import FAC from '../src/city/facades.json' with { type: 'json' };

const [name, layerName, glassRx, propRx] = process.argv.slice(2);
const GLASS = new RegExp(glassRx);
const PROP = new RegExp(propRx || '^(Korkuluk|cable|Material\\.|actexture|building\\.005|material$|rusty)');
const S = 1024;
await MeshoptEncoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });
const src = await io.read(`assets-src/kit/raw/${name}.glb`);

// texture layers, deduplicated by content
const albedo = [], pbr = [];
const seen = new Map();
function layerOf(list, tex, key) {
  if (!tex) return -1;
  const h = key + crypto.createHash('sha1').update(tex.getImage()).digest('hex');
  if (!seen.has(h)) { seen.set(h, list.length); list.push(tex.getImage()); }
  return seen.get(h);
}
const pbrNormal = [];

const out = new Document();
const buf = out.createBuffer();
const scene = out.createScene();
let tris0 = 0, tris1 = 0, cols1 = 0;
for (const node of src.getRoot().listNodes()) {
  const mesh = node.getMesh();
  if (!mesh) continue;
  const pos = [], nrm = [], uv = [], mat = [], col = [], idx = [];
  for (const p of mesh.listPrimitives()) {
    const m = p.getMaterial();
    const mn = m?.getName() || '';
    const kind = GLASS.test(mn) ? 1 : PROP.test(mn) ? 2 : 0;
    const aL = layerOf(albedo, m?.getBaseColorTexture(), 'a');
    // detail maps on a second or third UV set are left out: cells carry one UV set
    const mrTex = m?.getMetallicRoughnessTextureInfo()?.getTexCoord() === 0 ? m.getMetallicRoughnessTexture() : null;
    let pL = -1;
    if (mrTex) {
      pL = layerOf(pbr, mrTex, 'p');
      pbrNormal[pL] = m.getNormalTextureInfo()?.getTexCoord() === 0 ? m.getNormalTexture().getImage() : null;
    }
    const bc = m ? m.getBaseColorFactor() : [1, 1, 1, 1];
    const rough = kind === 0 && !mrTex ? 0.82 : m ? m.getRoughnessFactor() : 1, metal = m ? m.getMetallicFactor() : 0;
    const P = p.getAttribute('POSITION'), N = p.getAttribute('NORMAL'), T = p.getAttribute('TEXCOORD_0');
    const base = pos.length / 3;
    for (let i = 0; i < P.getCount(); i++) {
      pos.push(...P.getElement(i, [0, 0, 0]));
      nrm.push(...(N ? N.getElement(i, [0, 0, 0]) : [0, 0, 1]));
      uv.push(...(T ? T.getElement(i, [0, 0]) : [0, 0]));
      mat.push(aL, pL, kind, rough);
      col.push(bc[0], bc[1], bc[2], metal);
    }
    const I = p.getIndices();
    for (let i = 0; i < I.getCount(); i++) idx.push(base + I.getScalar(i));
  }
  const acc = (arr, type, T = Float32Array) => out.createAccessor().setType(type).setArray(new T(arr)).setBuffer(buf);
  const prim = out.createPrimitive()
    .setAttribute('POSITION', acc(pos, 'VEC3'))
    .setAttribute('NORMAL', acc(nrm, 'VEC3'))
    .setAttribute('TEXCOORD_0', acc(uv, 'VEC2'))
    .setAttribute('_MAT', acc(mat, 'VEC4'))
    .setAttribute('_COL', acc(col, 'VEC4'))
    .setIndices(acc(idx, 'SCALAR', Uint32Array));
  const nm = node.getName();
  (nm.startsWith('L0') ? (tris0 += idx.length / 3) : (tris1 += idx.length / 3));
  if (nm.startsWith('L1')) cols1 = Math.max(cols1, +nm.split('_')[1] + 1);
  scene.addChild(out.createNode(nm).setMesh(out.createMesh(nm).addPrimitive(prim)));
}
await out.transform(weld(), quantize({ pattern: /^(POSITION|NORMAL)$/ }), meshopt({ encoder: MeshoptEncoder, level: 'medium' }));
await io.write(`public/models/kit_${name}.glb`, out);

async function strip(list, file, opts, flat) {
  const parts = await Promise.all(list.map((img) => (img ? sharp(img) : sharp({ create: { width: S, height: S, channels: 3, background: flat } }))
    .resize(S, S, { fit: 'fill' }).removeAlpha().raw().toBuffer()));
  await sharp(Buffer.concat(parts), { raw: { width: S, height: S * list.length, channels: 3 } }).webp(opts).toFile(file);
}
await strip(albedo, `public/tex/kit_${name}_albedo.webp`, { quality: 90, effort: 6 });
await strip(pbr, `public/tex/kit_${name}_pbr.webp`, { quality: 92, effort: 6 });
await strip(pbr.map((_, i) => pbrNormal[i]), `public/tex/kit_${name}_normal.webp`, { quality: 92, effort: 6 }, { r: 128, g: 128, b: 255 });

const L = FAC.layers.find((l) => l.name === layerName);
const cfg = JSON.parse(fs.readFileSync(`assets-src/kit/cfg/${name}.json`, 'utf8'));
// geoBay: the cells' own width in metres; the game stretches them to the facade's fitted bay
const meta = { layer: layerName, cols: L.bays, rows: L.floors, geoBay: +(cfg.grid.bay * cfg.scale).toFixed(5), pitch: +(L.h / L.floors).toFixed(4), cols1, albedo: albedo.length, pbr: pbr.length };
fs.writeFileSync(`src/city/kit_${name}.json`, JSON.stringify(meta) + '\n');
const kb = (f) => (fs.statSync(f).size / 1024).toFixed(0) + ' KB';
console.log(meta, 'tris L0', tris0, 'L1', tris1, kb(`public/models/kit_${name}.glb`), ['albedo', 'pbr', 'normal'].map((k) => kb(`public/tex/kit_${name}_${k}.webp`)).join(' '));
