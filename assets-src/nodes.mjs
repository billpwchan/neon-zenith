import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { getBounds } from '@gltf-transform/functions';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(process.argv[2]);
const rows = [];
for (const n of doc.getRoot().listNodes()) {
  const m = n.getMesh(); if (!m) continue;
  const b = getBounds(n);
  let tris = 0; for (const p of m.listPrimitives()) tris += (p.getIndices()?.getCount() ?? p.getAttribute('POSITION').getCount()) / 3;
  rows.push([n.getName().slice(0, 28), m.listPrimitives().map((p) => p.getMaterial()?.getName()).join('/').slice(0, 40), tris, b.min.map((v) => v.toFixed(2)).join(','), b.max.map((v) => v.toFixed(2)).join(',')]);
}
rows.sort((a, b) => b[2] - a[2]);
for (const r of rows.slice(0, +process.argv[3] || 40)) console.log(r.join('  '));
console.log('nodes with mesh', rows.length);
