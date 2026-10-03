import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { getBounds } from '@gltf-transform/functions';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
for (const f of process.argv.slice(2)) {
  const doc = await io.read(f);
  const root = doc.getRoot();
  const b = getBounds(root.listScenes()[0]);
  let tris = 0;
  for (const m of root.listMeshes()) for (const p of m.listPrimitives()) tris += (p.getIndices() ? p.getIndices().getCount() : p.getAttribute('POSITION').getCount()) / 3;
  const tex = root.listTextures().map((t) => { const s = t.getSize(); return `${s?.[0]}x${s?.[1]}:${(t.getImage()?.byteLength / 1e6).toFixed(1)}MB`; });
  console.log(`\n## ${f} tris=${tris} meshes=${root.listMeshes().length} nodes=${root.listNodes().length} anims=${root.listAnimations().length} size=[${b.max.map((v, i) => (v - b.min[i]).toFixed(2))}] min=[${b.min.map((v) => v.toFixed(2))}] ext=${root.listExtensionsUsed().map((e) => e.extensionName).join(',')}`);
  console.log('  mats:', root.listMaterials().map((m) => m.getName()).join(' | ').slice(0, 600));
  console.log('  tex:', tex.length, tex.slice(0, 12).join(' '));
}
