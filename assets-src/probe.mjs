// probe world-space geometry of a glTF: per-material bounds, and a histogram of verts matching a filter
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';
import { mat4, vec3 } from 'gl-matrix';
await MeshoptDecoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder });
const [f, expr = 'false', key = 'p[1]', bin = '0.05'] = process.argv.slice(2);
const doc = await io.read(f);
const test = new Function('p', 'n', 'mat', 'return ' + expr);
const keyf = new Function('p', 'n', 'return ' + key);
const H = {}, B = {};
for (const node of doc.getRoot().listNodes()) {
  const mesh = node.getMesh(); if (!mesh) continue;
  const M = node.getWorldMatrix();
  const NM = mat4.transpose(mat4.create(), mat4.invert(mat4.create(), M));
  for (const prim of mesh.listPrimitives()) {
    const mat = prim.getMaterial()?.getName();
    const P = prim.getAttribute('POSITION'), N = prim.getAttribute('NORMAL');
    const a = [0, 0, 0], b = [0, 0, 0];
    const bb = B[mat] || (B[mat] = { min: [1e9, 1e9, 1e9], max: [-1e9, -1e9, -1e9], n: 0 });
    for (let i = 0; i < P.getCount(); i++) {
      P.getElement(i, a); const p = vec3.transformMat4([], a, M);
      let n = [0, 1, 0];
      if (N) { N.getElement(i, b); n = vec3.normalize([], vec3.transformMat4([], [...b], [...NM.slice(0, 12), 0, 0, 0, 1])); }
      for (let k = 0; k < 3; k++) { bb.min[k] = Math.min(bb.min[k], p[k]); bb.max[k] = Math.max(bb.max[k], p[k]); }
      bb.n++;
      if (test(p, n, mat)) { const k = (Math.round(keyf(p, n) / +bin) * +bin).toFixed(2); H[k] = (H[k] || 0) + 1; }
    }
  }
}
for (const [m, b] of Object.entries(B)) console.log(m, 'min', b.min.map((v) => v.toFixed(2)).join(','), 'max', b.max.map((v) => v.toFixed(2)).join(','), 'verts', b.n);
console.log('hist', JSON.stringify(Object.fromEntries(Object.entries(H).sort((a, b) => +a[0] - +b[0]))));
