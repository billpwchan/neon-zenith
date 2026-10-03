// Shop module packer: turns shop_slice.py's modules into one instanced kit, like kit.mjs for facades.
// Every module is one primitive with per-vertex material data, so all of them draw from three texture arrays:
//   _MAT = (albedo layer, normal layer or -1, metal-rough layer or -1, kind 0 surface / 1 lit interior / 2 sign)
//   _COL = (roughness factor, metalness factor, 0, 0)
//   _UV2 = (metal-rough uv, normal uv): those maps are tiling detail on their own UV sets
// Kinds follow the street strip's capture masks (facade/cfg/shop_*.json), so a module glows as its strip does.
// Writes public/models/shops.glb, public/tex/shopkit_{albedo,normal,mr}.webp, src/city/shopkit.json.
// node assets-src/shopkit.mjs
import { NodeIO, Document } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { meshopt, quantize, weld } from '@gltf-transform/functions';
import { MeshoptEncoder, MeshoptDecoder } from 'meshoptimizer';
import sharp from 'sharp';
import crypto from 'node:crypto';
import fs from 'node:fs';

const CFG = JSON.parse(fs.readFileSync('assets-src/facade/cfg/shop_bot.json', 'utf8'));
const GLASS = new RegExp(CFG.glass), SIGN = new RegExp(CFG.frame);
const KIT = JSON.parse(fs.readFileSync('assets-src/shopkit/cfg.json', 'utf8'));
const S = 1024;
await MeshoptEncoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });
const src = await io.read('assets-src/shopkit/raw.glb');

const strips = { albedo: [], normal: [], mr: [] };
const seen = new Map();
function layerOf(list, tex) {
  if (!tex) return -1;
  const h = crypto.createHash('sha1').update(tex.getImage()).digest('hex');
  const key = list === strips.albedo ? 'a' + h : list === strips.normal ? 'n' + h : 'm' + h;
  if (!seen.has(key)) { seen.set(key, list.length); list.push(tex.getImage()); }
  return seen.get(key);
}

const out = new Document();
const buf = out.createBuffer();
const scene = out.createScene();
const modules = [];
for (const node of src.getRoot().listNodes()) {
  const mesh = node.getMesh();
  if (!mesh) continue;
  const pos = [], nrm = [], uv = [], uv2 = [], mat = [], col = [], idx = [];
  for (const p of mesh.listPrimitives()) {
    const m = p.getMaterial();
    const mn = m?.getName() || '';
    const kind = GLASS.test(mn) ? 1 : SIGN.test(mn) ? 2 : 0;
    const aL = layerOf(strips.albedo, m?.getBaseColorTexture());
    const nL = layerOf(strips.normal, m?.getNormalTexture());
    const mL = layerOf(strips.mr, m?.getMetallicRoughnessTexture());
    const set = (info) => p.getAttribute(`TEXCOORD_${info?.getTexCoord() ?? 0}`) || p.getAttribute('TEXCOORD_0');
    const TM = set(m?.getMetallicRoughnessTextureInfo()), TN = set(m?.getNormalTextureInfo());
    const rough = m ? m.getRoughnessFactor() : 1, metal = m ? m.getMetallicFactor() : 0;
    const P = p.getAttribute('POSITION'), N = p.getAttribute('NORMAL'), T = p.getAttribute('TEXCOORD_0');
    const base = pos.length / 3;
    for (let i = 0; i < P.getCount(); i++) {
      pos.push(...P.getElement(i, [0, 0, 0]));
      nrm.push(...(N ? N.getElement(i, [0, 0, 0]) : [0, 0, 1]));
      uv.push(...(T ? T.getElement(i, [0, 0]) : [0, 0]));
      uv2.push(...(TM ? TM.getElement(i, [0, 0]) : [0, 0]), ...(TN ? TN.getElement(i, [0, 0]) : [0, 0]));
      mat.push(aL, nL, mL, kind);
      col.push(rough, metal, 0, 0);
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
    .setAttribute('_UV2', acc(uv2, 'VEC4'))
    .setIndices(acc(idx, 'SCALAR', Uint32Array));
  const name = node.getName();
  scene.addChild(out.createNode(name).setMesh(out.createMesh(name).addPrimitive(prim)));
  modules.push({ name: name.replace(/^S_/, ''), tris: idx.length / 3 });
}
await out.transform(weld(), quantize({ pattern: /^(POSITION|NORMAL)$/ }), meshopt({ encoder: MeshoptEncoder, level: 'medium' }));
await io.write('public/models/shops.glb', out);

async function strip(list, file, opts, flat) {
  const parts = await Promise.all((list.length ? list : [null]).map((img) => (img ? sharp(img) : sharp({ create: { width: S, height: S, channels: 3, background: flat } }))
    .resize(S, S, { fit: 'fill' }).removeAlpha().raw().toBuffer()));
  await sharp(Buffer.concat(parts), { raw: { width: S, height: S * parts.length, channels: 3 } }).webp(opts).toFile(file);
  return parts.length;
}
const layers = {
  albedo: await strip(strips.albedo, 'public/tex/shopkit_albedo.webp', { quality: 90, effort: 6 }),
  normal: await strip(strips.normal, 'public/tex/shopkit_normal.webp', { quality: 92, effort: 6 }, { r: 128, g: 128, b: 255 }),
  mr: await strip(strips.mr, 'public/tex/shopkit_mr.webp', { quality: 92, effort: 6 }, { r: 255, g: 255, b: 0 }),
};
// modules in strip order with their widths: the street strip (shops.mjs) is these fronts side by side
const order = KIT.modules.map((m) => ({ name: m.name, w: +(m.x1 - m.x0).toFixed(4) }));
fs.writeFileSync('src/city/shopkit.json', JSON.stringify({ modules: order, layers }) + '\n');
const kb = (f) => (fs.statSync(f).size / 1024).toFixed(0) + ' KB';
console.log(modules.map((m) => `${m.name} ${m.tris}`).join(', '), layers, kb('public/models/shops.glb'), ['albedo', 'normal', 'mr'].map((k) => kb(`public/tex/shopkit_${k}.webp`)).join(' '));
